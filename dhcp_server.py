import socket
import json

# Constants - No magic numbers
DHCP_SERVER_IP = '127.0.0.1'
DHCP_SERVER_PORT = 6767 # Standard DHCP uses 67, we use 6767 to avoid needing admin rights
OFFERED_IP = '127.0.0.2' # The fake IP we will give to our client

def start_dhcp_server():
    # 1. Create a UDP socket (SOCK_DGRAM means UDP)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # 2. Bind the socket to the IP and Port
    server_socket.bind((DHCP_SERVER_IP, DHCP_SERVER_PORT))
    
    print(f"[DHCP Server] Listening on {DHCP_SERVER_IP}:{DHCP_SERVER_PORT}...")
    
    while True:
        # 3. Wait to receive a message from a client
        # 1024 is the maximum buffer size in bytes
        data, client_address = server_socket.recvfrom(1024)
        
        # Decode the bytes into a string
        message = data.decode('utf-8')
        print(f"[DHCP Server] Received: '{message}' from {client_address}")
        
        # 4. Check if the client is asking for an IP
        if message == "DISCOVER":
            # 5. Prepare the OFFER response using JSON
            response = {
                "type": "OFFER",
                "assigned_ip": OFFERED_IP
            }
            
            # Convert JSON back to bytes
            response_bytes = json.dumps(response).encode('utf-8')
            
            # 6. Send the offer back to the client
            server_socket.sendto(response_bytes, client_address)
            print(f"[DHCP Server] Sent OFFER ({OFFERED_IP}) to {client_address}")

if __name__ == "__main__":
    start_dhcp_server()