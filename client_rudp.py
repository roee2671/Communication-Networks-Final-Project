import socket
import struct
import json

# Constants
DHCP_SERVER_IP = '127.0.0.1'
DHCP_SERVER_PORT = 6767
DNS_SERVER_IP = '127.0.0.1'
DNS_SERVER_PORT = 5353
APP_PORT_RUDP = 2122
BUFFER_SIZE = 2048    # Must fit header(11) + CHUNK_SIZE(500) with margin
TIMEOUT_SECONDS = 5.0
TARGET_DOMAIN = "my-app-server.local"

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
# RUDP connection — Stop-and-Wait ARQ receiver
# -----------------------------------------------------------------------
def connect_to_app_server_rudp(server_ip):
    print(f"\n[Client] 3. Starting RUDP connection to {server_ip}:{APP_PORT_RUDP}...")
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(TIMEOUT_SECONDS)
    server_address = (server_ip, APP_PORT_RUDP)

    try:
        # -------------------------------------------------------------------
        # Step A: SYN handshake — prove the channel is reachable
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
        print(f"[Client] Command ACKed (Ack={ack_num}). Server is now fetching the URL...")

        # -------------------------------------------------------------------
        # Step C: Stop-and-Wait ARQ receive loop
        #
        # The server sends one DATA chunk at a time and waits for our ACK
        # before sending the next.  We must:
        #   1. Receive the DATA packet.
        #   2. Append its payload to our buffer.
        #   3. Send an ACK immediately (Ack = Seq of the chunk we just got).
        #   4. Repeat until we receive a FIN packet.
        #
        # Duplicate detection: if the server does not receive our ACK in
        # time it retransmits the same chunk.  We detect this by comparing
        # the arriving Seq with `expected_seq`.  If Seq < expected_seq the
        # chunk is a duplicate — re-ACK it but do NOT add it to the buffer.
        # -------------------------------------------------------------------
        file_buffer = b''   # All received chunk payloads will be assembled here
        expected_seq = 1    # The Seq number of the next chunk we are waiting for

        print("[Client] Entering Stop-and-Wait receive loop...")

        while True:
            try:
                packet, _ = client_socket.recvfrom(BUFFER_SIZE)
            except socket.timeout:
                # No packet arrived for TIMEOUT_SECONDS — something went wrong
                print("[Client] Timeout waiting for data from server. Ending receive loop.")
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
                if seq_num == expected_seq:
                    # This is the chunk we were waiting for — accept it
                    chunk = payload_bytes[:data_len]
                    file_buffer += chunk
                    print(f"[Client] Received chunk Seq={seq_num} "
                          f"({data_len} bytes). Buffer total: {len(file_buffer)} bytes.")
                    expected_seq += 1
                else:
                    # Duplicate chunk (server retransmitted because our ACK was lost)
                    # Do NOT add to buffer — just re-send the ACK so server can proceed
                    print(f"[Client] Duplicate chunk Seq={seq_num} "
                          f"(expected {expected_seq}). Re-sending ACK.")

                # Always ACK the chunk we just received, whether new or duplicate
                client_socket.sendto(build_packet(0, seq_num, b'A'), server_address)

            # ---------------------------------------------------------------
            # FIN packet received — all chunks have arrived
            # ---------------------------------------------------------------
            elif flag == 'F':
                print(f"[Client] FIN received (Seq={seq_num}). "
                      f"Transfer complete! Total bytes: {len(file_buffer)}.")
                # ACK the FIN so the server knows we are done
                client_socket.sendto(build_packet(0, seq_num, b'A'), server_address)
                break

        # -------------------------------------------------------------------
        # Step D: Save the assembled data to disk
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
