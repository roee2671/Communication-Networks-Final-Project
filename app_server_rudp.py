import socket
import struct
import urllib.request

# Constants
APP_SERVER_IP = '127.0.0.3'
APP_PORT_RUDP = 2122
BUFFER_SIZE = 2048    # Must fit header(11) + CHUNK_SIZE(500) with margin
HEADER_FORMAT = '!IIcH'  # ! = network byte order | I=uint32 seq | I=uint32 ack | c=char flag | H=uint16 len
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 11 bytes
CHUNK_SIZE = 500      # Each DATA packet carries at most this many bytes of payload
MAX_WINDOW = 5        # Maximum number of unACKed chunks allowed in flight at once (AIMD ceiling)

def build_packet(seq, ack, flag_byte, payload=b''):
    """Assemble a full RUDP packet: 11-byte header followed by the optional payload bytes."""
    header = struct.pack(HEADER_FORMAT, seq, ack, flag_byte, len(payload))
    return header + payload

def start_rudp_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((APP_SERVER_IP, APP_PORT_RUDP))

    print(f"[RUDP Server] Listening on UDP {APP_SERVER_IP}:{APP_PORT_RUDP}...")

    while True:
        try:
            # Block indefinitely waiting for the next command from any client
            server_socket.settimeout(None)
            packet, client_address = server_socket.recvfrom(BUFFER_SIZE)

            if len(packet) < HEADER_SIZE:
                print("[RUDP Server] Packet too small to contain header. Ignoring.")
                continue

            # Unpack the fixed 11-byte header — format never changes
            seq_num, ack_num, flag_byte, data_len = struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])
            payload_bytes = packet[HEADER_SIZE:]
            flag = flag_byte.decode('utf-8')

            print(f"\n[RUDP Server] Packet from {client_address} | "
                  f"Seq={seq_num} Ack={ack_num} Flag='{flag}' Len={data_len}")

            # -------------------------------------------------------------------
            # Handshake: SYN → SYN-ACK
            # -------------------------------------------------------------------
            if flag == 'S':
                print("[RUDP Server] SYN received. Sending SYN-ACK...")
                # Ack = seq_num + 1 so the client can verify with ack_num == 101
                server_socket.sendto(build_packet(0, seq_num + 1, b'A'), client_address)

            # -------------------------------------------------------------------
            # Command packet: FETCH <url>
            # -------------------------------------------------------------------
            elif flag == 'D':
                command = payload_bytes[:data_len].decode('utf-8')
                print(f"[RUDP Server] Command: '{command}'")

                # ACK the command packet before doing any work
                server_socket.sendto(build_packet(0, seq_num, b'A'), client_address)
                print("[RUDP Server] ACK sent for command.")

                if not command.startswith("FETCH "):
                    print("[RUDP Server] Unknown command. Ignoring.")
                    continue

                url = command[len("FETCH "):]
                print(f"[RUDP Server] Fetching from internet: {url}")

                # Fetch the URL using Python's built-in HTTP client
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    file_data = urllib.request.urlopen(req, timeout=10).read()
                    print(f"[RUDP Server] Downloaded {len(file_data)} bytes. "
                          f"Starting Go-Back-N transfer (MAX_WINDOW={MAX_WINDOW})...")
                except Exception as fetch_err:
                    print(f"[RUDP Server] Fetch failed: {fetch_err}")
                    # Deliver the error as a real DATA chunk using Stop-and-Wait so the
                    # client gets readable text instead of a silent empty file.
                    error_payload = (
                        f"ERROR: Could not fetch URL '{url}'. Reason: {fetch_err}"
                    ).encode('utf-8')
                    error_packet = build_packet(1, 0, b'D', error_payload)
                    while True:
                        server_socket.sendto(error_packet, client_address)
                        print("[RUDP Server] Sent error chunk (Seq=1). Waiting for ACK...")
                        server_socket.settimeout(1.0)
                        try:
                            ack_raw, _ = server_socket.recvfrom(BUFFER_SIZE)
                            _, ack_num_recv, ack_flag_byte, _ = struct.unpack(
                                HEADER_FORMAT, ack_raw[:HEADER_SIZE]
                            )
                            if ack_flag_byte.decode('utf-8') == 'A' and ack_num_recv == 1:
                                print("[RUDP Server] Error chunk ACKed. Sending FIN.")
                                break
                        except socket.timeout:
                            print("[RUDP Server] Timeout on error chunk. Retransmitting...")
                    server_socket.settimeout(None)
                    server_socket.sendto(build_packet(2, 0, b'F'), client_address)
                    continue

                # -------------------------------------------------------------------
                # Split the downloaded bytes into CHUNK_SIZE-byte pieces
                # -------------------------------------------------------------------
                chunks = [file_data[i:i + CHUNK_SIZE] for i in range(0, len(file_data), CHUNK_SIZE)]
                total_chunks = len(chunks)
                print(f"[RUDP Server] {total_chunks} chunk(s) to send.")

                # -------------------------------------------------------------------
                # Go-Back-N Sliding Window with AIMD Congestion Control
                #
                # Key variables:
                #   window_size — how many unACKed packets may be in-flight at once.
                #                 Starts at 1 (like TCP slow-start) and grows/shrinks.
                #   base_seq    — sequence number of the oldest unACKed chunk
                #                 (left edge of the window). Advances on each ACK.
                #   next_seq    — sequence number of the next chunk to SEND
                #                 (right edge + 1). Can be ahead of base_seq by
                #                 up to window_size - 1.
                #
                # AIMD rules:
                #   Additive Increase  — every successful ACK: window_size += 1
                #   Multiplicative Dec — every timeout:        window_size //= 2
                #
                # Go-Back-N retransmit — on timeout, reset next_seq = base_seq so
                #   the entire unACKed window is retransmitted from the beginning.
                # -------------------------------------------------------------------
                window_size = 1   # Start conservatively (like TCP slow-start)
                base_seq    = 1   # Oldest unACKed chunk
                next_seq    = 1   # Next chunk to be transmitted

                while base_seq <= total_chunks:

                    # --- Phase 1: Fill the window -----------------------------------
                    # Send every chunk from next_seq up to the window's right edge,
                    # but never go past the last chunk.
                    window_end = min(base_seq + window_size - 1, total_chunks)
                    while next_seq <= window_end:
                        chunk = chunks[next_seq - 1]
                        data_packet = build_packet(next_seq, 0, b'D', chunk)
                        server_socket.sendto(data_packet, client_address)
                        print(f"[RUDP Server] Sent Seq={next_seq} ({len(chunk)}B) "
                              f"| window=[{base_seq}..{window_end}] size={window_size}")
                        next_seq += 1

                    # --- Phase 2: Wait for one ACK ----------------------------------
                    # We wait up to 1 second. If an ACK arrives in time and is useful
                    # (ack_num >= base_seq), we advance the window and grow it.
                    # If we time out, the packet or its ACK was lost: shrink the window
                    # and trigger Go-Back-N by rewinding next_seq to base_seq.
                    server_socket.settimeout(1.0)
                    try:
                        ack_raw, _ = server_socket.recvfrom(BUFFER_SIZE)
                        _, ack_num_recv, ack_flag_byte, _ = struct.unpack(
                            HEADER_FORMAT, ack_raw[:HEADER_SIZE]
                        )
                        ack_flag = ack_flag_byte.decode('utf-8')

                        if ack_flag == 'A' and ack_num_recv >= base_seq:
                            # Useful cumulative ACK — slide the window forward
                            print(f"[RUDP Server] ACK={ack_num_recv} received. "
                                  f"Advancing base from {base_seq} to {ack_num_recv + 1}.")
                            base_seq = ack_num_recv + 1

                            # AIMD Additive Increase: reward successful delivery
                            window_size = min(window_size + 1, MAX_WINDOW)
                            print(f"[Congestion Control] Window increased to {window_size}.")

                        else:
                            # Stale/duplicate ACK (ack_num < base_seq) —
                            # the client is still waiting for base_seq, do nothing.
                            print(f"[RUDP Server] Stale ACK={ack_num_recv} "
                                  f"(base={base_seq}). Ignoring.")

                    except socket.timeout:
                        # No ACK within 1 second — assume chunk or ACK was lost.
                        # AIMD Multiplicative Decrease: halve the window size.
                        window_size = max(1, window_size // 2)
                        print(f"[Congestion Control] Timeout! Window shrunk to {window_size}.")
                        # Go-Back-N: rewind next_seq so we retransmit all unACKed
                        # chunks starting from base_seq on the next loop iteration.
                        next_seq = base_seq
                        print(f"[RUDP Server] Go-Back-N: retransmitting from Seq={base_seq}.")

                # -------------------------------------------------------------------
                # FIN — all chunks have been ACKed; signal end of transfer
                # -------------------------------------------------------------------
                print("[RUDP Server] All chunks delivered. Sending FIN...")
                server_socket.settimeout(None)
                server_socket.sendto(build_packet(total_chunks + 1, 0, b'F'), client_address)
                print("[RUDP Server] FIN sent. File transfer complete.")

        except Exception as e:
            print(f"[RUDP Server] Unexpected error: {e}")

if __name__ == "__main__":
    start_rudp_server()
