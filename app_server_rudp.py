import socket
import struct
import urllib.request

# Constants
APP_SERVER_IP = '127.0.0.3'
APP_PORT_RUDP = 2122
BUFFER_SIZE = 2048    # Must fit header(11) + CHUNK_SIZE(500) with margin
HEADER_FORMAT = '!IIcH'  # ! = network byte order | I=uint32 seq | I=uint32 ack | c=char flag | H=uint16 len
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 11 bytes
CHUNK_SIZE = 500      # Split the downloaded file into 500-byte pieces for Stop-and-Wait ARQ

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

            # Unpack the fixed 11-byte header
            seq_num, ack_num, flag_byte, data_len = struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])
            payload_bytes = packet[HEADER_SIZE:]
            flag = flag_byte.decode('utf-8')

            print(f"\n[RUDP Server] Packet from {client_address} | Seq={seq_num} Ack={ack_num} Flag='{flag}' Len={data_len}")

            # ---------------------------------------------------------------
            # Handshake: SYN → SYN-ACK
            # ---------------------------------------------------------------
            if flag == 'S':
                print("[RUDP Server] SYN received. Sending SYN-ACK...")
                # Ack = seq_num + 1, matching what the client expects (ack_num == 101)
                server_socket.sendto(build_packet(0, seq_num + 1, b'A'), client_address)

            # ---------------------------------------------------------------
            # Command packet: FETCH <url>
            # ---------------------------------------------------------------
            elif flag == 'D':
                command = payload_bytes[:data_len].decode('utf-8')
                print(f"[RUDP Server] Command: '{command}'")

                # ACK the command packet — Ack = seq_num of the command packet
                server_socket.sendto(build_packet(0, seq_num, b'A'), client_address)
                print("[RUDP Server] ACK sent for command.")

                if not command.startswith("FETCH "):
                    print("[RUDP Server] Unknown command. Ignoring.")
                    continue

                url = command[len("FETCH "):]
                print(f"[RUDP Server] Fetching from internet: {url}")

                # Use Python's built-in HTTP client to download the URL
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    file_data = urllib.request.urlopen(req, timeout=10).read()
                    print(f"[RUDP Server] Downloaded {len(file_data)} bytes. Starting Stop-and-Wait transfer...")
                except Exception as fetch_err:
                    print(f"[RUDP Server] Fetch failed: {fetch_err}")
                    # Don't send a silent FIN — deliver the error as a real DATA chunk first
                    # so the client receives readable text instead of an empty file.
                    # Use Stop-and-Wait for this single error chunk just like normal data.
                    error_payload = f"ERROR: Could not fetch URL '{url}'. Reason: {fetch_err}".encode('utf-8')
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
                            print("[RUDP Server] Timeout waiting for ACK of error chunk. Retransmitting...")
                    server_socket.settimeout(None)
                    server_socket.sendto(build_packet(2, 0, b'F'), client_address)
                    continue

                # ---------------------------------------------------------------
                # Split the downloaded bytes into fixed-size chunks
                # ---------------------------------------------------------------
                chunks = [file_data[i:i + CHUNK_SIZE] for i in range(0, len(file_data), CHUNK_SIZE)]
                total_chunks = len(chunks)
                print(f"[RUDP Server] {total_chunks} chunk(s) to send ({CHUNK_SIZE} bytes max each).")

                # ---------------------------------------------------------------
                # Stop-and-Wait ARQ — send one chunk at a time, do NOT advance
                # to the next chunk until the correct ACK has been received.
                # ---------------------------------------------------------------
                for chunk_seq in range(1, total_chunks + 1):
                    chunk = chunks[chunk_seq - 1]
                    # Build the DATA packet once; reuse it for every retransmit attempt
                    data_packet = build_packet(chunk_seq, 0, b'D', chunk)

                    while True:
                        # Send this chunk to the client
                        server_socket.sendto(data_packet, client_address)
                        print(f"[RUDP Server] Sent chunk {chunk_seq}/{total_chunks} "
                              f"(Seq={chunk_seq}, {len(chunk)} bytes). Waiting for ACK...")

                        # Wait up to 1 second for the ACK before retransmitting
                        server_socket.settimeout(1.0)
                        try:
                            ack_raw, _ = server_socket.recvfrom(BUFFER_SIZE)
                            _, ack_num_recv, ack_flag_byte, _ = struct.unpack(
                                HEADER_FORMAT, ack_raw[:HEADER_SIZE]
                            )
                            ack_flag = ack_flag_byte.decode('utf-8')

                            if ack_flag == 'A' and ack_num_recv == chunk_seq:
                                # Correct ACK — this chunk is delivered; move to next
                                print(f"[RUDP Server] ACK={ack_num_recv} confirmed. "
                                      f"Chunk {chunk_seq} delivered.")
                                break
                            else:
                                # Stale or duplicate ACK — retransmit the current chunk
                                print(f"[RUDP Server] Wrong ACK "
                                      f"(got {ack_num_recv}, expected {chunk_seq}). "
                                      f"Retransmitting chunk {chunk_seq}...")

                        except socket.timeout:
                            # No ACK arrived within 1 s — the packet or ACK was lost
                            print(f"[RUDP Server] Timeout! No ACK for chunk {chunk_seq}. "
                                  f"Retransmitting...")

                # ---------------------------------------------------------------
                # FIN — signal end of transmission after all chunks are ACKed
                # ---------------------------------------------------------------
                print("[RUDP Server] All chunks delivered. Sending FIN...")
                server_socket.settimeout(None)
                # Seq = total_chunks + 1 continues the sequence naturally
                server_socket.sendto(build_packet(total_chunks + 1, 0, b'F'), client_address)
                print("[RUDP Server] FIN sent. File transfer complete.")

        except Exception as e:
            print(f"[RUDP Server] Unexpected error: {e}")

if __name__ == "__main__":
    start_rudp_server()
