import socket
import struct
import json
import random
import time

# RUDP Client - Phase 3
# Performs the full DHCP -> DNS -> RUDP initialization sequence.
#
# RUDP receive logic (Go-Back-N receiver):
#   In-order packet (seq == expected_seq): buffer it, ACK it, advance expected_seq.
#   Out-of-order packet (seq != expected_seq): discard it, send a cumulative ACK
#     for the last successfully received sequence number. This signals the server
#     to retransmit from the gap position.
#   FIN packet: ACK it and exit the receive loop.
#
# Simulation flags:
#   SIMULATE_PACKET_LOSS: randomly drops ~30% of incoming DATA packets without
#     sending an ACK, forcing the server's 1-second timeout to fire and proving
#     retransmission works.
#   SIMULATE_LATENCY: adds a random delay before processing each packet to
#     simulate network latency, as required by the assignment.
#
# The '!IIcH' header format must match app_server_rudp.py exactly.

DHCP_SERVER_IP   = '127.0.0.1'
DHCP_SERVER_PORT = 6767
DNS_SERVER_IP    = '127.0.0.1'
DNS_SERVER_PORT  = 5353
APP_PORT_RUDP    = 2122   # Must match APP_PORT_RUDP in app_server_rudp.py.
BUFFER_SIZE      = 2048   # Large enough for header (11) + max chunk (500).
TIMEOUT          = 5.0
TARGET_DOMAIN    = "my-app-server.local"

SIMULATE_PACKET_LOSS = True   # Drop ~30% of incoming DATA chunks to test retransmission.
SIMULATE_LATENCY     = True   # Using time.sleep to simulate network latency as required by the assignment.

# RUDP header format: 4+4+1+2 = 11 bytes total. DO NOT CHANGE.
# Must be identical to HEADER_FORMAT in app_server_rudp.py.
# '!' = network byte order
# 'I' = unsigned int  (4 bytes) = Sequence Number
# 'I' = unsigned int  (4 bytes) = Acknowledgement Number
# 'c' = char          (1 byte)  = Flag byte (b'S', b'A', b'D', or b'F')
# 'H' = unsigned short(2 bytes) = Payload length
HEADER_FORMAT = '!IIcH'
HEADER_SIZE   = struct.calcsize(HEADER_FORMAT)  # = 11


def build_packet(seq_num, ack_num, flag, payload=b''):
    # Pack the 4 fields into an 11-byte header and append the payload.
    header = struct.pack(HEADER_FORMAT, seq_num, ack_num, flag, len(payload))
    return header + payload


# -------------------------------------------------------
# Step 1: Request an IP address from the DHCP server.
# -------------------------------------------------------
def request_ip_from_dhcp():
    print("\n--- step 1: DHCP ---")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)

    print(f"sending DISCOVER to {DHCP_SERVER_IP}:{DHCP_SERVER_PORT}...")
    sock.sendto(b"DISCOVER", (DHCP_SERVER_IP, DHCP_SERVER_PORT))

    reply_bytes = None
    try:
        reply_bytes, _ = sock.recvfrom(BUFFER_SIZE)
    except Exception as e:
        print(f"DHCP timeout or error: {e}")

    sock.close()

    if reply_bytes is None:
        print("no reply from DHCP server.")
        return None

    reply = json.loads(reply_bytes.decode('utf-8'))

    if reply.get("type") == "OFFER":
        assigned_ip = reply.get("assigned_ip")
        print(f"DHCP OFFER received. assigned IP: {assigned_ip}")
        return assigned_ip

    print("reply was not a valid OFFER.")
    return None


# -------------------------------------------------------
# Step 2: Resolve the target domain name using DNS.
# -------------------------------------------------------
def resolve_domain_with_dns(domain):
    print(f"\n--- step 2: DNS ---")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)

    query_bytes = json.dumps({"domain": domain}).encode('utf-8')
    print(f"querying DNS for '{domain}'...")
    sock.sendto(query_bytes, (DNS_SERVER_IP, DNS_SERVER_PORT))

    reply_bytes = None
    try:
        reply_bytes, _ = sock.recvfrom(BUFFER_SIZE)
    except Exception as e:
        print(f"DNS timeout or error: {e}")

    sock.close()

    if reply_bytes is None:
        print("no reply from DNS server.")
        return None

    reply = json.loads(reply_bytes.decode('utf-8'))
    print(f"DNS reply: {reply}")

    if reply.get("status") == "SUCCESS":
        server_ip = reply.get("ip")
        print(f"resolved: {domain} -> {server_ip}")
        return server_ip

    print(f"DNS lookup failed. status: {reply.get('status')}")
    return None


# -------------------------------------------------------
# Step 3: RUDP handshake, send FETCH, receive file data.
# -------------------------------------------------------
def connect_to_app_server_rudp(server_ip):
    print(f"\n--- step 3: RUDP ---")

    sock        = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)
    server_addr = (server_ip, APP_PORT_RUDP)

    # Step A: SYN handshake.
    # Send SYN with seq=100. The server replies with ACK and ack_num=101.
    print("sending SYN (seq=100)...")
    sock.sendto(build_packet(100, 0, b'S'), server_addr)

    syn_ack = None
    try:
        syn_ack, _ = sock.recvfrom(BUFFER_SIZE)
    except Exception as e:
        print(f"no SYN-ACK received: {e}")

    if syn_ack is None:
        print("handshake failed. closing.")
        sock.close()
        return

    _, ack_num, flag_byte, _ = struct.unpack(HEADER_FORMAT, syn_ack[:HEADER_SIZE])
    flag = flag_byte.decode('utf-8')
    print(f"SYN-ACK received: flag='{flag}', ack={ack_num}")

    if flag != 'A' or ack_num != 101:
        print(f"invalid SYN-ACK (expected flag='A', ack=101). closing.")
        sock.close()
        return

    print("handshake complete.")

    # Step B: Send the FETCH command as a DATA packet (seq=101).
    command    = "FETCH http://127.0.0.1:8080/test_file.txt"
    cmd_bytes  = command.encode('utf-8')
    cmd_packet = build_packet(101, 0, b'D', cmd_bytes)

    print(f"sending command: '{command}'")
    sock.sendto(cmd_packet, server_addr)

    cmd_ack = None
    try:
        cmd_ack, _ = sock.recvfrom(BUFFER_SIZE)
    except Exception as e:
        print(f"no ACK for command: {e}")

    if cmd_ack is None:
        print("command not acknowledged. closing.")
        sock.close()
        return

    _, ack_num, flag_byte, _ = struct.unpack(HEADER_FORMAT, cmd_ack[:HEADER_SIZE])
    flag = flag_byte.decode('utf-8')
    print(f"command ACK: flag='{flag}', ack={ack_num}")

    if flag != 'A':
        print("expected ACK flag for command. closing.")
        sock.close()
        return

    print("command acknowledged. server is fetching the URL.")

    # Step C: Receive file chunks using Go-Back-N receiver logic.
    # In-order: buffer and ACK. Out-of-order: discard, send cumulative ACK.
    file_buffer  = b''
    expected_seq = 1

    print("starting receive loop...")

    while True:
        print("waiting for next packet...")

        packet = None
        try:
            packet, _ = sock.recvfrom(BUFFER_SIZE)
        except Exception as e:
            print(f"receive timeout or error: {e}")
            print("timeout. looping back.")
            break

        if packet is None:
            break

        print(f"received {len(packet)} bytes.")

        if len(packet) < HEADER_SIZE:
            print(f"packet too small ({len(packet)} bytes). ignoring.")
            continue

        # Unpack the 11-byte RUDP header. DO NOT change '!IIcH'.
        seq_num, _, flag_byte, data_len = struct.unpack(
            HEADER_FORMAT, packet[:HEADER_SIZE]
        )
        payload = packet[HEADER_SIZE:]
        flag    = flag_byte.decode('utf-8')

        print(f"  seq={seq_num}, flag='{flag}', data_len={data_len}")

        if flag == 'D':
            # Using time.sleep to simulate network latency as required by the assignment.
            # Applied before the loss check because even dropped packets have travel time.
            if SIMULATE_LATENCY:
                delay = random.uniform(0.1, 0.4)
                print(f"  latency sim: sleeping {delay:.2f}s (seq={seq_num})")
                time.sleep(delay)

            # Randomly drop ~30% of DATA packets to demonstrate Go-Back-N retransmission.
            # Skipping the ACK causes the server's 1-second timeout to fire.
            rand_val = random.random()
            if SIMULATE_PACKET_LOSS and rand_val < 0.3:
                print(f"  loss sim: dropping seq={seq_num}. no ACK sent.")
                continue

            if seq_num == expected_seq:
                # In-order: accept the chunk, buffer it, advance expected_seq, and ACK.
                chunk_data   = payload[:data_len]
                file_buffer  = file_buffer + chunk_data
                expected_seq = expected_seq + 1
                print(f"  in-order seq={seq_num}. buffering and sending ACK. buffer={len(file_buffer)} bytes.")
                sock.sendto(build_packet(0, seq_num, b'A'), server_addr)

            else:
                # Out-of-order: discard and send a cumulative ACK for the last good seq.
                # This tells the server exactly where the gap is.
                last_good_seq = expected_seq - 1
                print(f"  out-of-order seq={seq_num} (expected {expected_seq}). sending cumulative ACK={last_good_seq}.")
                sock.sendto(build_packet(0, last_good_seq, b'A'), server_addr)

        elif flag == 'F':
            print(f"FIN received (seq={seq_num}). transfer complete. buffer={len(file_buffer)} bytes.")
            sock.sendto(build_packet(0, seq_num, b'A'), server_addr)
            print("ACK sent for FIN.")
            break

        else:
            print(f"unknown flag '{flag}'. ignoring.")

    # Step D: Save the assembled data to disk.
    if len(file_buffer) > 0:
        out_file = "downloaded_rudp.html"
        with open(out_file, 'wb') as f:
            f.write(file_buffer)
        print(f"file saved: '{out_file}' ({len(file_buffer)} bytes)")
    else:
        print("buffer empty. nothing to save.")

    sock.close()
    print("socket closed.")


if __name__ == "__main__":
    print("=== RUDP client starting ===")

    assigned_ip = request_ip_from_dhcp()
    if assigned_ip is None:
        print("DHCP failed. exiting.")
    else:
        server_ip = resolve_domain_with_dns(TARGET_DOMAIN)
        if server_ip is None:
            print("DNS failed. exiting.")
        else:
            print(f"\ninitialization complete. my IP: {assigned_ip}, server: {server_ip}")
            connect_to_app_server_rudp(server_ip)
