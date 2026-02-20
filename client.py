# import socket
# import json

# # Constants - No magic numbers
# DHCP_SERVER_IP = '127.0.0.1'
# DHCP_SERVER_PORT = 6767
# BUFFER_SIZE = 1024
# TIMEOUT_SECONDS = 5.0

# def request_ip_from_dhcp():
#     # 1. Create UDP socket for the client
#     client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
#     # 2. Set timeout so we don't wait forever if the server is down
#     client_socket.settimeout(TIMEOUT_SECONDS)
    
#     try:
#         # 3. Send DISCOVER message to the server
#         message = "DISCOVER"
#         print(f"[Client] Sending '{message}' to DHCP server ({DHCP_SERVER_IP}:{DHCP_SERVER_PORT})...")
        
#         # We must encode strings to bytes before sending over the network
#         client_socket.sendto(message.encode('utf-8'), (DHCP_SERVER_IP, DHCP_SERVER_PORT))
        
#         # 4. Wait for the OFFER response from the server
#         data, server_address = client_socket.recvfrom(BUFFER_SIZE)
        
#         # Decode bytes back to string, then parse the JSON
#         response = json.loads(data.decode('utf-8'))
        
#         # 5. Extract the assigned IP from the JSON response
#         if response.get("type") == "OFFER":
#             assigned_ip = response.get("assigned_ip")
#             print(f"[Client] Success! Received IP: {assigned_ip} from {server_address}")
#             return assigned_ip
            
#     except socket.timeout:
#         print("[Client] Error: DHCP Server didn't respond in time.")
#         return None
#     except Exception as e:
#         print(f"[Client] An unexpected error occurred: {e}")
#         return None
#     finally:
#         # 6. Always close the socket to free up resources
#         client_socket.close()

# if __name__ == "__main__":
#     print("[Client] Starting network initialization...")
#     my_new_ip = request_ip_from_dhcp()


import socket
import json

# Constants - No magic numbers
DHCP_SERVER_IP = '127.0.0.1'
DHCP_SERVER_PORT = 6767
DNS_SERVER_IP = '127.0.0.1'
DNS_SERVER_PORT = 5353
BUFFER_SIZE = 1024
TIMEOUT_SECONDS = 5.0
TARGET_DOMAIN = "my-ftp-server.local"
FTP_PORT = 2121          # Must match FTP_PORT_TCP in ftp_server.py
LENGTH_HEADER_SIZE = 10  # Must match LENGTH_HEADER_SIZE in ftp_server.py

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

def connect_to_ftp_tcp(server_ip):
    """Step 3: Connect to the FTP server via TCP, list files, then download one."""

    # --- Connection 1: LIST ---
    # Each command uses its own TCP connection (server closes after one command)
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(f"\n[Client] 3a. Connecting to FTP Server at {server_ip}:{FTP_PORT} for LIST...")
        client_socket.connect((server_ip, FTP_PORT))

        # Send the LIST command framed with a 10-byte length header
        send_command(client_socket, "LIST")

        # Receive the file list using the same framing
        data = receive_all(client_socket)

        print("\n=== Available Files on Server ===")
        files = data.decode('utf-8').split(",")
        for i, file_name in enumerate(files):
            print(f"{i + 1}. {file_name}")
        print("=================================")

    except Exception as e:
        print(f"[Client] Failed to get file list: {e}")
        return  # No point continuing to DOWNLOAD if LIST already failed
    finally:
        client_socket.close()

    # --- Connection 2: DOWNLOAD ---
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(f"\n[Client] 3b. Connecting to FTP Server at {server_ip}:{FTP_PORT} for DOWNLOAD...")
        client_socket.connect((server_ip, FTP_PORT))

        # Frame the DOWNLOAD command with a 10-byte length header before sending
        command = "DOWNLOAD test_file.txt"
        print(f"[Client] Sending command: '{command}'")
        send_command(client_socket, command)

        # Receive the server's response (file bytes, or an ERROR string)
        file_data = receive_all(client_socket)

        # If the response starts with "ERROR", the file was not found on the server
        if file_data.startswith(b"ERROR"):
            print(f"[Client] -> Server error: {file_data.decode('utf-8')}")
        else:
            # Save the raw bytes to disk in binary write mode
            output_filename = "downloaded_test_file.txt"
            with open(output_filename, 'wb') as f:
                f.write(file_data)
            print(f"[Client] -> Success! Saved '{output_filename}' ({len(file_data)} bytes)")

    except Exception as e:
        print(f"[Client] Failed to download file: {e}")
    finally:
        client_socket.close()

if __name__ == "__main__":
    print("=== Starting Network Initialization ===")

    # Step 1: DHCP
    my_ip = request_ip_from_dhcp()

    if my_ip:
        # Step 2: DNS
        ftp_server_ip = resolve_domain_with_dns(TARGET_DOMAIN)

        if ftp_server_ip:
            print("\n=== Network Initialization Complete ===")
            print(f"My IP: {my_ip}")
            print(f"Target FTP Server IP: {ftp_server_ip}")

            # Step 3: Connect to FTP server (list files + download)
            connect_to_ftp_tcp(ftp_server_ip)
