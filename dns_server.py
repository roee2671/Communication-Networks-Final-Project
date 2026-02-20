import socket
import json

# Constants - No magic numbers [cite: 3]
DNS_SERVER_IP = '127.0.0.1'
DNS_SERVER_PORT = 5353 # Standard DNS is 53, we use 5353 for local testing without admin rights [cite: 76]

# Our "Phonebook" - mapping domain names to IP addresses
DNS_RECORDS = {
    "my-ftp-server.local": "127.0.0.3", # This will be our future FTP server
    "google.com": "8.8.8.8"             # Just for testing
}

def start_dns_server():
    # 1. Create a UDP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Fix: SO_REUSEADDR lets us restart the server without "Address already in use" errors
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # 2. Bind the socket
    server_socket.bind((DNS_SERVER_IP, DNS_SERVER_PORT))
    
    print(f"[DNS Server] Listening on {DNS_SERVER_IP}:{DNS_SERVER_PORT}...")
    
    while True:
        # 3. Wait for a DNS query from a client
        data, client_address = server_socket.recvfrom(1024)
        
        try:
            # Parse the incoming JSON request
            request = json.loads(data.decode('utf-8'))
            domain_requested = request.get("domain")

            # Fix: Guard against requests that are missing the "domain" key entirely
            if domain_requested is None:
                print("[DNS Server] Request missing 'domain' field, ignoring.")
                response = {"status": "ERROR", "ip": None}
                server_socket.sendto(json.dumps(response).encode('utf-8'), client_address)
                continue

            print(f"[DNS Server] Client {client_address} is asking for: {domain_requested}")
            
            # 4. Look up the domain in our records
            if domain_requested in DNS_RECORDS:
                resolved_ip = DNS_RECORDS[domain_requested]
                response = {"status": "SUCCESS", "ip": resolved_ip}
                print(f"[DNS Server] Found! Sending IP: {resolved_ip}")
            else:
                response = {"status": "NOT_FOUND", "ip": None}
                print(f"[DNS Server] Domain '{domain_requested}' not found.")
                
            # 5. Send the answer back to the client
            server_socket.sendto(json.dumps(response).encode('utf-8'), client_address)
            
        except json.JSONDecodeError:
            print("[DNS Server] Received invalid data format.")

if __name__ == "__main__":
    start_dns_server()