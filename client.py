import socket
import json

# TCP Client - Phase 1 and 2
# Performs the full network initialization sequence:
#   Step 1 - DHCP: request an IP address.
#   Step 2 - DNS:  resolve the app server's domain name to an IP.
#   Step 3 - App:  connect over TCP, send a FETCH command, receive the file.
#
# TCP Framing:
# TCP is a stream protocol, so we prepend a 10-byte length header to avoid
# fragmentation issues. The receiver reads 10 bytes first to determine message length.

DHCP_SERVER_IP     = '127.0.0.1'
DHCP_SERVER_PORT   = 6767
DNS_SERVER_IP      = '127.0.0.1'
DNS_SERVER_PORT    = 5353
BUFFER_SIZE        = 1024
TIMEOUT            = 5.0
TARGET_DOMAIN      = "my-app-server.local"
APP_SERVER_PORT    = 2121  # Must match APP_SERVER_PORT in app_server.py.
LENGTH_HEADER_SIZE = 10    # Must match LENGTH_HEADER_SIZE in app_server.py.


def send_framed(sock, text):
    # Encode the text to bytes and prepend a 10-byte zero-padded length header.
    cmd_bytes  = text.encode('utf-8')
    length_str = str(len(cmd_bytes)).zfill(LENGTH_HEADER_SIZE)
    header     = length_str.encode('utf-8')
    print(f"sending: '{text}' ({len(cmd_bytes)} bytes)")
    sock.send(header + cmd_bytes)


def receive_framed(sock):
    # Read the 10-byte length header, then loop until all expected bytes are received.
    # TCP may deliver data in fragments, so a single recv() call is not sufficient.
    print("reading length header...")
    header = sock.recv(LENGTH_HEADER_SIZE)

    if len(header) < LENGTH_HEADER_SIZE:
        print(f"header too short ({len(header)} bytes). returning empty.")
        return b''

    total_expected = int(header.decode('utf-8'))
    print(f"expecting {total_expected} bytes...")

    received_bytes = b''
    while len(received_bytes) < total_expected:
        remaining  = total_expected - len(received_bytes)

        if remaining > BUFFER_SIZE:
            to_receive = BUFFER_SIZE
        else:
            to_receive = remaining

        print(f"  received {len(received_bytes)}/{total_expected}. requesting {to_receive} more...")
        chunk = sock.recv(to_receive)

        if not chunk:
            print("connection closed by server before all data was received.")
            break

        received_bytes = received_bytes + chunk

    print(f"receive complete: {len(received_bytes)} bytes total.")
    return received_bytes


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
    print(f"DHCP reply: {reply}")

    if reply.get("type") == "OFFER":
        assigned_ip = reply.get("assigned_ip")
        print(f"assigned IP: {assigned_ip}")
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

    query = json.dumps({"domain": domain}).encode('utf-8')
    print(f"querying DNS for '{domain}'...")
    sock.sendto(query, (DNS_SERVER_IP, DNS_SERVER_PORT))

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
# Step 3: Connect to the app server and fetch the file.
# -------------------------------------------------------
def connect_to_app_server(server_ip):
    print(f"\n--- step 3: app server ---")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(f"connecting to {server_ip}:{APP_SERVER_PORT}...")
        sock.connect((server_ip, APP_SERVER_PORT))
        print("connected.")

        command = "FETCH http://127.0.0.1:8080/test_file.txt"
        send_framed(sock, command)

        print("waiting for response...")
        response_bytes = receive_framed(sock)
        print(f"response received: {len(response_bytes)} bytes")

        if response_bytes.startswith(b"ERROR"):
            print(f"server error: {response_bytes.decode('utf-8')}")
        else:
            out_file = "downloaded_from_web.html"
            with open(out_file, 'wb') as f:
                f.write(response_bytes)
            print(f"file saved: '{out_file}' ({len(response_bytes)} bytes)")

    except Exception as e:
        print(f"connection error: {e}")

    sock.close()
    print("socket closed.")


if __name__ == "__main__":
    print("=== starting network initialization ===")

    assigned_ip = request_ip_from_dhcp()
    if assigned_ip is None:
        print("DHCP failed. exiting.")
    else:
        server_ip = resolve_domain_with_dns(TARGET_DOMAIN)
        if server_ip is None:
            print("DNS failed. exiting.")
        else:
            print(f"\ninitialization complete. my IP: {assigned_ip}, server: {server_ip}")
            connect_to_app_server(server_ip)
