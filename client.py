import socket
import json

# Constants - No magic numbers
DHCP_SERVER_IP = '127.0.0.1'
DHCP_SERVER_PORT = 6767
DNS_SERVER_IP = '127.0.0.1'
DNS_SERVER_PORT = 5353
BUFFER_SIZE = 1024
TIMEOUT_SECONDS = 5.0
TARGET_DOMAIN = "my-app-server.local"  # Pivot: updated from my-ftp-server.local
APP_SERVER_PORT = 2121                 # Must match APP_SERVER_PORT in app_server.py
LENGTH_HEADER_SIZE = 10                # Must match LENGTH_HEADER_SIZE in app_server.py

def request_ip_from_dhcp():
    """Step 1: Get an IP address for the client."""
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(TIMEOUT_SECONDS)

    try:
        message = "DISCOVER"
        print(f"\n[Client] 1. Sending '{message}' to DHCP server...")
        client_socket.sendto(message.encode('utf-8'), (DHCP_SERVER_IP, DHCP_SERVER_PORT))

        data, _ = client_socket.recvfrom(BUFFER_SIZE)
        response = json.loads(data.decode('utf-8'))

        if response.get("type") == "OFFER":
            assigned_ip = response.get("assigned_ip")
            print(f"[Client] -> Success! My new IP is: {assigned_ip}")
            return assigned_ip
    except socket.timeout:
        print("[Client] -> Error: DHCP Server timeout.")
    finally:
        client_socket.close()
    return None

def resolve_domain_with_dns(domain_name):
    """Step 2: Ask DNS server for the IP of our target domain."""
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(TIMEOUT_SECONDS)

    try:
        request = {"domain": domain_name}
        print(f"\n[Client] 2. Asking DNS server for IP of: {domain_name}...")

        client_socket.sendto(json.dumps(request).encode('utf-8'), (DNS_SERVER_IP, DNS_SERVER_PORT))

        data, _ = client_socket.recvfrom(BUFFER_SIZE)
        response = json.loads(data.decode('utf-8'))

        if response.get("status") == "SUCCESS":
            resolved_ip = response.get("ip")
            print(f"[Client] -> Success! The IP for {domain_name} is: {resolved_ip}")
            return resolved_ip
        else:
            print(f"[Client] -> Error: Domain {domain_name} not found in DNS.")
    except socket.timeout:
        print("[Client] -> Error: DNS Server timeout.")
    finally:
        client_socket.close()
    return None

def send_command(sock, command_str):
    """Frame a command string with a 10-byte length header and send it."""
    payload = command_str.encode('utf-8')
    length_header = str(len(payload)).zfill(LENGTH_HEADER_SIZE).encode('utf-8')
    sock.send(length_header + payload)

def receive_all(sock):
    """Read the 10-byte length header, then read exactly that many bytes and return them."""
    raw_header = sock.recv(LENGTH_HEADER_SIZE)
    msg_length = int(raw_header.decode('utf-8'))

    # Loop until every byte has arrived (TCP may split data across multiple recv calls)
    data = b''
    while len(data) < msg_length:
        chunk = sock.recv(min(BUFFER_SIZE, msg_length - len(data)))
        if not chunk:
            break  # Server closed the connection unexpectedly
        data += chunk
    return data

def connect_to_app_server(server_ip):
    """Step 3: Connect to the HTTP proxy server and ask it to fetch a URL for us."""
    # Pivot: replaced two-step LIST+DOWNLOAD with a single FETCH command
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(f"\n[Client] 3. Connecting to App Server at {server_ip}:{APP_SERVER_PORT}...")
        client_socket.connect((server_ip, APP_SERVER_PORT))

        # Send a FETCH command — the server will make the real HTTP request on our behalf
        command = "FETCH http://127.0.0.1:8080/test_file.txt"
        print(f"[Client] Sending command: '{command}'")
        send_command(client_socket, command)

        # Receive the full response (HTML bytes, or an ERROR string) using framing
        response_data = receive_all(client_socket)

        # If the server returned an error, print it instead of saving garbage to disk
        if response_data.startswith(b"ERROR"):
            print(f"[Client] -> Server error: {response_data.decode('utf-8')}")
        else:
            # Save the downloaded HTML bytes to disk
            output_filename = "downloaded_from_web.html"
            with open(output_filename, 'wb') as f:
                f.write(response_data)
            print(f"[Client] -> Success! Saved '{output_filename}' ({len(response_data)} bytes)")

    except Exception as e:
        print(f"[Client] Failed to communicate with app server: {e}")
    finally:
        client_socket.close()

if __name__ == "__main__":
    print("=== Starting Network Initialization ===")

    # Step 1: DHCP
    my_ip = request_ip_from_dhcp()

    if my_ip:
        # Step 2: DNS
        app_server_ip = resolve_domain_with_dns(TARGET_DOMAIN)

        if app_server_ip:
            print("\n=== Network Initialization Complete ===")
            print(f"My IP: {my_ip}")
            print(f"Target App Server IP: {app_server_ip}")

            # Step 3: Connect to the HTTP proxy server and fetch a URL
            connect_to_app_server(app_server_ip)
