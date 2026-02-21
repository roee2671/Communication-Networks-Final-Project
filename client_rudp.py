import socket
import struct
import json
import time

# Constants
DHCP_SERVER_IP = '127.0.0.1'
DHCP_SERVER_PORT = 6767
DNS_SERVER_IP = '127.0.0.1'
DNS_SERVER_PORT = 5353
APP_PORT_RUDP = 2122 # Match the new RUDP port
BUFFER_SIZE = 1024
TIMEOUT_SECONDS = 5.0
TARGET_DOMAIN = "my-app-server.local"

# RUDP Header Format: 4 byte Seq, 4 byte Ack, 1 byte Flag, 2 byte Length = 11 bytes
HEADER_FORMAT = '!IIcH' 
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# --- DHCP and DNS functions remain identical to our TCP phase ---
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
            print(f"[Client] -> Success! My new IP is: {assigned_ip}")
            return assigned_ip
    except socket.timeout:
        print("[Client] -> Error: DHCP Server timeout.")
    finally:
        client_socket.close()
    return None

def resolve_domain_with_dns(domain_name):
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
    except socket.timeout:
        print("[Client] -> Error: DNS Server timeout.")
    finally:
        client_socket.close()
    return None

# --- New RUDP Connection Logic ---
def connect_to_app_server_rudp(server_ip):
    print(f"\n[Client] 3. Starting RUDP Connection to {server_ip}:{APP_PORT_RUDP}...")
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(TIMEOUT_SECONDS)
    server_address = (server_ip, APP_PORT_RUDP)
    
    try:
        # Step A: Send SYN packet to test connection (Seq=100, Ack=0, Flag='S', Len=0)
        print("[Client] Sending SYN packet...")
        syn_header = struct.pack(HEADER_FORMAT, 100, 0, b'S', 0)
        client_socket.sendto(syn_header, server_address)
        
        # Wait for SYN-ACK
        packet, _ = client_socket.recvfrom(BUFFER_SIZE)
        seq_num, ack_num, flag_byte, data_len = struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])
        
        if flag_byte.decode('utf-8') == 'A' and ack_num == 101:
            print("[Client] Received SYN-ACK! Connection established.")
            
            # Step B: Send a DATA packet with our FETCH command
            command = "FETCH http://127.0.0.1:8080/test_file.txt"
            payload = command.encode('utf-8')
            print(f"[Client] Sending DATA command: '{command}'")
            
            # Seq=101, Ack=0, Flag='D', Len=len(payload)
            data_header = struct.pack(HEADER_FORMAT, 101, 0, b'D', len(payload))
            client_socket.sendto(data_header + payload, server_address)
            
            # Wait for ACK for our data
            packet, _ = client_socket.recvfrom(BUFFER_SIZE)
            seq_num, ack_num, flag_byte, data_len = struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])
            if flag_byte.decode('utf-8') == 'A':
                print(f"[Client] Server acknowledged our command (ACK={ack_num}).")
                print("[Client] RUDP Foundation test successful!")
                
    except socket.timeout:
        print("[Client] RUDP Timeout. Packet lost!")
    except Exception as e:
        print(f"[Client] Error: {e}")
    finally:
        client_socket.close()

if __name__ == "__main__":
    my_ip = request_ip_from_dhcp()
    if my_ip:
        app_server_ip = resolve_domain_with_dns(TARGET_DOMAIN)
        if app_server_ip:
            connect_to_app_server_rudp(app_server_ip)