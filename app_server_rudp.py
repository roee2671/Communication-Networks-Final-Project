import socket
import struct
import urllib.request

# RUDP App Server - Phase 3
# This server implements reliable file transfer over UDP using:
#   1. A custom 11-byte RUDP header per packet (Seq, Ack, Flag, DataLen).
#   2. Go-Back-N sliding window: multiple unACKed packets allowed in flight.
#      On timeout, retransmit from the oldest unACKed sequence number.
#   3. AIMD congestion control:
#      Additive Increase - window_size += 1 on each successful ACK.
#      Multiplicative Decrease - window_size //= 2 on timeout.
#
# The '!IIcH' header format must not be changed - it is shared with client_rudp.py.

APP_SERVER_IP = '127.0.0.3'  # Must match the DNS record for "my-app-server.local".
APP_PORT_RUDP = 2122          # Must match APP_PORT_RUDP in client_rudp.py.
BUFFER_SIZE   = 2048          # Large enough for header (11) + max chunk (500).
CHUNK_SIZE    = 500           # Maximum payload bytes per DATA packet.
MAX_WINDOW    = 5             # AIMD cap - window_size never exceeds this value.

# RUDP header format: 4+4+1+2 = 11 bytes total. DO NOT CHANGE.
# '!' = network byte order (big-endian)
# 'I' = unsigned int  (4 bytes) = Sequence Number
# 'I' = unsigned int  (4 bytes) = Acknowledgement Number
# 'c' = char          (1 byte)  = Flag byte (b'S', b'A', b'D', or b'F')
# 'H' = unsigned short(2 bytes) = Payload length in bytes
# Must be identical in client_rudp.py.
HEADER_FORMAT = '!IIcH'
HEADER_SIZE   = struct.calcsize(HEADER_FORMAT)  # = 11


def build_packet(seq_num, ack_num, flag, payload=b''):
    # Pack the 4 fields into an 11-byte header and append the payload.
    # flag must be a single bytes object: b'S', b'A', b'D', or b'F'.
    header = struct.pack(HEADER_FORMAT, seq_num, ack_num, flag, len(payload))
    return header + payload


def start_rudp_server():
    print("starting RUDP server...")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((APP_SERVER_IP, APP_PORT_RUDP))
    print(f"RUDP server listening on UDP {APP_SERVER_IP}:{APP_PORT_RUDP}")

    while True:
        print("\nwaiting for packet (blocking)...")
        # No timeout here - block indefinitely until a new client packet arrives.
        server_sock.settimeout(None)

        raw_packet  = None
        client_addr = None
        try:
            raw_packet, client_addr = server_sock.recvfrom(BUFFER_SIZE)
        except Exception as e:
            print(f"error receiving packet: {e}")
            continue

        if raw_packet is None:
            continue

        print(f"received {len(raw_packet)} bytes from {client_addr}")

        # Validate packet size before attempting to unpack the header.
        if len(raw_packet) < HEADER_SIZE:
            print(f"packet too small ({len(raw_packet)} bytes). ignoring.")
            continue

        # Unpack the 11-byte RUDP header. DO NOT change '!IIcH'.
        seq_num, ack_num, flag_byte, data_len = struct.unpack(
            HEADER_FORMAT, raw_packet[:HEADER_SIZE]
        )
        payload = raw_packet[HEADER_SIZE:]
        flag    = flag_byte.decode('utf-8')

        print(f"header: seq={seq_num}, ack={ack_num}, flag='{flag}', data_len={data_len}")

        # ----------------------------------------
        # SYN - connection handshake
        # ----------------------------------------
        if flag == 'S':
            print("SYN received. sending SYN-ACK...")
            # ACK number = client's seq + 1. The client checks for ack_num == 101.
            server_sock.sendto(build_packet(0, seq_num + 1, b'A'), client_addr)
            print(f"SYN-ACK sent (ack={seq_num + 1})")

        # ----------------------------------------
        # DATA - command from client (FETCH <url>)
        # ----------------------------------------
        elif flag == 'D':
            command = payload[:data_len].decode('utf-8')
            print(f"DATA received. command: '{command}'")

            # ACK the command packet before doing any work.
            server_sock.sendto(build_packet(0, seq_num, b'A'), client_addr)
            print(f"command ACKed (ack={seq_num})")

            if not command.startswith("FETCH "):
                print(f"unknown command. ignoring.")
                continue

            url = command[len("FETCH "):]
            print(f"fetching: {url}")

            file_data = None
            error_msg = ""
            try:
                req       = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                file_data = urllib.request.urlopen(req, timeout=10).read()
                print(f"download complete: {len(file_data)} bytes")
            except Exception as e:
                error_msg = str(e)
                print(f"download failed: {e}")

            # If the download failed, send an error message as a DATA chunk
            # using Stop-and-Wait, then send FIN.
            if file_data is None:
                print("sending error message to client (stop-and-wait)...")
                error_text   = f"ERROR: Could not fetch '{url}'. Reason: {error_msg}"
                error_bytes  = error_text.encode('utf-8')
                error_packet = build_packet(1, 0, b'D', error_bytes)

                error_acked = False
                while not error_acked:
                    print("sending error chunk (seq=1)...")
                    server_sock.sendto(error_packet, client_addr)
                    server_sock.settimeout(1.0)

                    ack_packet = None
                    try:
                        ack_packet, _ = server_sock.recvfrom(BUFFER_SIZE)
                    except Exception as e:
                        print(f"timeout waiting for error ACK: {e}. retransmitting.")

                    if ack_packet is not None:
                        if len(ack_packet) >= HEADER_SIZE:
                            _, client_ack, ack_flag_byte, _ = struct.unpack(
                                HEADER_FORMAT, ack_packet[:HEADER_SIZE]
                            )
                            ack_flag = ack_flag_byte.decode('utf-8')
                            if ack_flag == 'A' and client_ack == 1:
                                print("error chunk ACKed.")
                                error_acked = True
                            else:
                                print(f"wrong ACK (ack={client_ack}). retransmitting.")
                        else:
                            print("ACK packet too small. retransmitting.")

                server_sock.settimeout(None)
                server_sock.sendto(build_packet(2, 0, b'F'), client_addr)
                print("FIN sent after error chunk.")
                continue

            # Split the downloaded data into fixed-size chunks.
            chunks = []
            pos    = 0
            while pos < len(file_data):
                chunk_data = file_data[pos : pos + CHUNK_SIZE]
                chunks.append(chunk_data)
                pos = pos + CHUNK_SIZE

            num_chunks = len(chunks)
            print(f"split into {num_chunks} chunk(s). starting Go-Back-N transfer.")

            # ============================================================
            # Go-Back-N sliding window with AIMD congestion control.
            #
            # window_size: number of unACKed packets allowed in flight.
            # base_seq:    sequence number of the oldest unACKed packet (window left edge).
            # next_seq:    sequence number of the next packet to transmit.
            #
            # AIMD rules:
            #   Additive Increase - window_size += 1 on each valid ACK.
            #   Multiplicative Decrease - window_size //= 2 on timeout.
            #
            # Go-Back-N on timeout: reset next_seq = base_seq to retransmit
            # all packets in the current window from the left edge.
            # ============================================================
            window_size = 1
            base_seq    = 1
            next_seq    = 1

            while base_seq <= num_chunks:

                # Phase 1: transmit all packets within the current window.
                window_end = base_seq + window_size - 1
                if window_end > num_chunks:
                    window_end = num_chunks

                print(f"window: [{base_seq}..{window_end}], size={window_size}, next_seq={next_seq}")

                while next_seq <= window_end:
                    # Chunks are 0-indexed; sequence numbers are 1-indexed.
                    chunk_data  = chunks[next_seq - 1]
                    data_packet = build_packet(next_seq, 0, b'D', chunk_data)
                    server_sock.sendto(data_packet, client_addr)
                    print(f"  sent seq={next_seq} ({len(chunk_data)} bytes)")
                    next_seq = next_seq + 1

                # Phase 2: wait for an ACK with a 1-second timeout.
                print("waiting for ACK (1s timeout)...")
                server_sock.settimeout(1.0)

                got_ack    = False
                ack_packet = None
                try:
                    ack_packet, _ = server_sock.recvfrom(BUFFER_SIZE)
                    got_ack = True
                except Exception as e:
                    print(f"timeout: {e}")

                if not got_ack:
                    # AIMD Multiplicative Decrease: halve window_size on timeout.
                    window_size = window_size // 2
                    if window_size < 1:
                        window_size = 1
                    print(f"timeout. window_size={window_size}.")

                    # Go-Back-N: retransmit from oldest unACKed packet.
                    next_seq = base_seq
                    print(f"going back to seq={base_seq}.")

                else:
                    if len(ack_packet) < HEADER_SIZE:
                        print(f"ACK packet too small ({len(ack_packet)} bytes). ignoring.")
                    else:
                        _, client_ack, ack_flag_byte, _ = struct.unpack(
                            HEADER_FORMAT, ack_packet[:HEADER_SIZE]
                        )
                        ack_flag = ack_flag_byte.decode('utf-8')
                        print(f"received: flag='{ack_flag}', ack={client_ack}")

                        if ack_flag == 'A' and client_ack >= base_seq:
                            print(f"got ACK for chunk {client_ack}. sliding window.")
                            base_seq = client_ack + 1

                            # AIMD Additive Increase: increment window_size on valid ACK.
                            window_size = window_size + 1
                            if window_size > MAX_WINDOW:
                                window_size = MAX_WINDOW
                            print(f"window_size now {window_size}.")

                        else:
                            print(f"stale ACK (ack={client_ack}, base={base_seq}). ignoring.")

            # All chunks delivered - send FIN to signal end of transfer.
            print("all chunks delivered. sending FIN.")
            server_sock.settimeout(None)
            server_sock.sendto(build_packet(num_chunks + 1, 0, b'F'), client_addr)
            print("FIN sent. transfer complete.")

        else:
            print(f"unknown flag '{flag}'. ignoring.")


if __name__ == "__main__":
    start_rudp_server()
