import socket
import struct
import json
import random
import time

# Constants
DHCP_SERVER_IP = '127.0.0.1'
DHCP_SERVER_PORT = 6767
DNS_SERVER_IP = '127.0.0.1'
DNS_SERVER_PORT = 5353
APP_PORT_RUDP = 2122
BUFFER_SIZE = 2048    # Must fit header(11) + CHUNK_SIZE(500) with margin
TIMEOUT_SECONDS = 5.0
TARGET_DOMAIN = "my-app-server.local"

# --- Simulation toggles ---
# SIMULATE_PACKET_LOSS: randomly drop ~30% of incoming DATA packets without ACKing them.
#   This forces the server's 1-second timeout to fire, proving Go-Back-N retransmission.
SIMULATE_PACKET_LOSS = True

# SIMULATE_LATENCY: sleep 0.1–0.4 s before processing each DATA packet.
#   This mimics a slow network link and makes congestion control effects visible
#   in Wireshark (delayed ACKs → window fluctuation).
SIMULATE_LATENCY = True

# RUDP Header: 4-byte Seq | 4-byte Ack | 1-byte Flag | 2-byte DataLen  = 11 bytes total
HEADER_FORMAT = '!IIcH'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

def build_packet(seq, ack, flag_byte, payload=b''):
    """Assemble a full RUDP packet: 11-byte header followed by the optional payload bytes."""
    header = struct.pack(HEADER_FORMAT, seq, ack, flag_byte, len(payload))
    return header + payload

# -----------------------------------------------------------------------
# DHCP and DNS helpers — identical to TCP phase, no changes needed
# -----------------------------------------------------------------------
def request_ip_from_dhcp():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(TIMEOUT_SECONDS)
    try:
        print("\n[Client] 1. Sending 'DISCOVER' to DHCP server...")
        client_socket.sendto(b"DISCOVER", (DHCP_SERVER_IP, DHCP_SERVER_PORT))
        data, _ = client_socket.recvfrom(BUFFER_SIZE)
        response = json.loads(data.decode('utf-8'))
        if response.get("type") == "OFFER":
            assigned_ip = response.get("assigned_ip")
            print(f"[Client] -> My new IP: {assigned_ip}")
            return assigned_ip
    except socket.timeout:
        print("[Client] -> DHCP timeout.")
    finally:
        client_socket.close()
    return None

def resolve_domain_with_dns(domain_name):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(TIMEOUT_SECONDS)
    try:
        print(f"\n[Client] 2. DNS lookup for: {domain_name}...")
        client_socket.sendto(
            json.dumps({"domain": domain_name}).encode('utf-8'),
            (DNS_SERVER_IP, DNS_SERVER_PORT)
        )
        data, _ = client_socket.recvfrom(BUFFER_SIZE)
        response = json.loads(data.decode('utf-8'))
        if response.get("status") == "SUCCESS":
            resolved_ip = response.get("ip")
            print(f"[Client] -> {domain_name} = {resolved_ip}")
            return resolved_ip
    except socket.timeout:
        print("[Client] -> DNS timeout.")
    finally:
        client_socket.close()
    return None

# -----------------------------------------------------------------------
# RUDP connection — Go-Back-N sliding window receiver with cumulative ACK
# -----------------------------------------------------------------------
def connect_to_app_server_rudp(server_ip):
    print(f"\n[Client] 3. Starting RUDP connection to {server_ip}:{APP_PORT_RUDP}...")
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(TIMEOUT_SECONDS)
    server_address = (server_ip, APP_PORT_RUDP)

    try:
        # -------------------------------------------------------------------
        # Step A: SYN handshake
        # -------------------------------------------------------------------
        print("[Client] Sending SYN (Seq=100)...")
        client_socket.sendto(build_packet(100, 0, b'S'), server_address)

        packet, _ = client_socket.recvfrom(BUFFER_SIZE)
        _, ack_num, flag_byte, _ = struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])

        if not (flag_byte.decode('utf-8') == 'A' and ack_num == 101):
            print("[Client] Bad SYN-ACK. Aborting.")
            return
        print("[Client] SYN-ACK received (Ack=101). Connection established.")

        # -------------------------------------------------------------------
        # Step B: Send the FETCH command as a DATA packet (Seq=101)
        # -------------------------------------------------------------------
        command = "FETCH http://127.0.0.1:8080/test_file.txt"  # Local proxy serves this file
        print(f"[Client] Sending command: '{command}'")
        payload = command.encode('utf-8')
        client_socket.sendto(build_packet(101, 0, b'D', payload), server_address)

        # Wait for the server's ACK of our command
        packet, _ = client_socket.recvfrom(BUFFER_SIZE)
        _, ack_num, flag_byte, _ = struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])
        if flag_byte.decode('utf-8') != 'A':
            print("[Client] Did not receive ACK for command. Aborting.")
            return
        print(f"[Client] Command ACKed (Ack={ack_num}). Server is fetching the URL...")

        # -------------------------------------------------------------------
        # Step C: Go-Back-N sliding window receive loop
        #
        # The server may send multiple chunks in flight (window_size > 1).
        # Our job as the receiver is straightforward:
        #
        #   IN-ORDER packet (seq_num == expected_seq):
        #     Accept → append to buffer → increment expected_seq → ACK(seq_num).
        #
        #   OUT-OF-ORDER packet (seq_num != expected_seq):
        #     Discard the payload — we cannot use it yet because there is a gap.
        #     Send a CUMULATIVE ACK for the last in-order chunk we accepted:
        #       ACK(expected_seq - 1)
        #     This tells the server "I've received everything up to expected_seq-1;
        #     please retransmit from expected_seq (Go-Back-N)."
        #
        #   FIN packet:
        #     ACK it and break the loop.
        #
        # The two simulation flags are applied here:
        #   SIMULATE_LATENCY     — sleep before processing, making ACKs arrive late.
        #   SIMULATE_PACKET_LOSS — skip processing entirely (no ACK sent at all),
        #                          which will trigger the server's 1-second timeout.
        # -------------------------------------------------------------------
        file_buffer  = b''  # Assembled payload from all accepted in-order chunks
        expected_seq = 1    # Seq number of the next in-order chunk we are waiting for

        print("[Client] Entering Go-Back-N receive loop...")

        while True:
            try:
                packet, _ = client_socket.recvfrom(BUFFER_SIZE)
            except socket.timeout:
                print("[Client] Timeout waiting for data. Ending receive loop.")
                break

            if len(packet) < HEADER_SIZE:
                print("[Client] Undersized packet. Ignoring.")
                continue

            seq_num, _, flag_byte, data_len = struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])
            payload_bytes = packet[HEADER_SIZE:]
            flag = flag_byte.decode('utf-8')

            # ---------------------------------------------------------------
            # DATA packet received
            # ---------------------------------------------------------------
            if flag == 'D':

                # -- Latency simulation ------------------------------------------
                # Sleep BEFORE the loss check so that even dropped packets consume
                # time, which is the realistic behaviour of a slow network card.
                if SIMULATE_LATENCY:
                    delay = random.uniform(0.1, 0.4)
                    print(f"[Client] SIMULATING LATENCY: {delay:.2f}s delay on Seq={seq_num}.")
                    time.sleep(delay)

                # -- Packet-loss simulation ---------------------------------------
                # Drop the packet without sending any ACK. The server's 1-second
                # settimeout will expire and it will retransmit (Go-Back-N).
                if SIMULATE_PACKET_LOSS and random.random() < 0.3:
                    print(f"[Client] SIMULATING PACKET LOSS! "
                          f"Dropping Seq={seq_num} without sending ACK.")
                    continue  # Jump back to recvfrom — no ACK is sent

                # -- Normal processing -------------------------------------------
                if seq_num == expected_seq:
                    # In-order chunk: accept it and advance the expected pointer
                    chunk = payload_bytes[:data_len]
                    file_buffer += chunk
                    print(f"[Client] Accepted Seq={seq_num} ({data_len}B). "
                          f"Buffer total: {len(file_buffer)}B.")
                    expected_seq += 1
                    # ACK exactly this chunk to let the server slide its window forward
                    client_socket.sendto(build_packet(0, seq_num, b'A'), server_address)

                else:
                    # Out-of-order chunk (gap detected — Go-Back-N retransmission from server)
                    # Discard the payload; do NOT add it to the buffer.
                    # Send a cumulative ACK for the last chunk we successfully received
                    # so the server knows where the gap is.
                    print(f"[Client] Out-of-order Seq={seq_num} "
                          f"(expected {expected_seq}). "
                          f"Sending cumulative ACK={expected_seq - 1}.")
                    client_socket.sendto(
                        build_packet(0, expected_seq - 1, b'A'), server_address
                    )

            # ---------------------------------------------------------------
            # FIN packet received — transfer is complete
            # ---------------------------------------------------------------
            elif flag == 'F':
                print(f"[Client] FIN received (Seq={seq_num}). "
                      f"Total bytes buffered: {len(file_buffer)}.")
                # ACK the FIN so the server can close cleanly
                client_socket.sendto(build_packet(0, seq_num, b'A'), server_address)
                break

        # -------------------------------------------------------------------
        # Step D: Save the assembled buffer to disk
        # -------------------------------------------------------------------
        if file_buffer:
            output_file = "downloaded_rudp.html"
            with open(output_file, 'wb') as f:
                f.write(file_buffer)
            print(f"[Client] -> Success! Saved '{output_file}' ({len(file_buffer)} bytes).")
        else:
            print("[Client] -> No data received. File not saved.")

    except socket.timeout:
        print("[Client] RUDP timeout during handshake or command phase.")
    except Exception as e:
        print(f"[Client] Unexpected error: {e}")
    finally:
        client_socket.close()

if __name__ == "__main__":
    my_ip = request_ip_from_dhcp()
    if my_ip:
        app_server_ip = resolve_domain_with_dns(TARGET_DOMAIN)
        if app_server_ip:
            connect_to_app_server_rudp(app_server_ip)
