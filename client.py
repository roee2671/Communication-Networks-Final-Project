import socket
import json

# Constants - No magic numbers
DHCP_SERVER_IP = '127.0.0.1'
DHCP_SERVER_PORT = 6767
BUFFER_SIZE = 1024
TIMEOUT_SECONDS = 5.0

def request_ip_from_dhcp():
    # 1. Create UDP socket for the client
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # 2. Set timeout so we don't wait forever if the server is down
    client_socket.settimeout(TIMEOUT_SECONDS)
    
    try:
        # 3. Send DISCOVER message to the server
        message = "DISCOVER"
        print(f"[Client] Sending '{message}' to DHCP server ({DHCP_SERVER_IP}:{DHCP_SERVER_PORT})...")
        
        # We must encode strings to bytes before sending over the network
        client_socket.sendto(message.encode('utf-8'), (DHCP_SERVER_IP, DHCP_SERVER_PORT))
        
        # 4. Wait for the OFFER response from the server
        data, server_address = client_socket.recvfrom(BUFFER_SIZE)
        
        # Decode bytes back to string, then parse the JSON
        response = json.loads(data.decode('utf-8'))
        
        # 5. Extract the assigned IP from the JSON response
        if response.get("type") == "OFFER":
            assigned_ip = response.get("assigned_ip")
            print(f"[Client] Success! Received IP: {assigned_ip} from {server_address}")
            return assigned_ip
            
    except socket.timeout:
        print("[Client] Error: DHCP Server didn't respond in time.")
        return None
    except Exception as e:
        print(f"[Client] An unexpected error occurred: {e}")
        return None
    finally:
        # 6. Always close the socket to free up resources
        client_socket.close()

if __name__ == "__main__":
    print("[Client] Starting network initialization...")
    my_new_ip = request_ip_from_dhcp()