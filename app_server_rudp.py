import socket
import struct

# Constants
APP_SERVER_IP = '127.0.0.3'
APP_PORT_RUDP = 2122  # New port for RUDP to avoid conflicts with TCP
BUFFER_SIZE = 1024
HEADER_FORMAT = '!IIcH'  # ! = Network byte order, I = Unsigned Int (4), c = char (1), H = Unsigned Short (2). Total = 11 bytes.
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

def start_rudp_server():
    # Notice we use SOCK_DGRAM for UDP
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((APP_SERVER_IP, APP_PORT_RUDP))
    
    print(f"[RUDP Server] Listening on UDP {APP_SERVER_IP}:{APP_PORT_RUDP}...")
    
    while True:
        try:
            # Receive data and the client's address
            packet, client_address = server_socket.recvfrom(BUFFER_SIZE)
            
            if len(packet) < HEADER_SIZE:
                print("[RUDP Server] Received packet too small to contain header. Ignoring.")
                continue
                
            # Extract header and payload
            header_bytes = packet[:HEADER_SIZE]
            payload_bytes = packet[HEADER_SIZE:]
            
            # Unpack the 11-byte header
            seq_num, ack_num, flag_byte, data_len = struct.unpack(HEADER_FORMAT, header_bytes)
            flag = flag_byte.decode('utf-8')
            
            print(f"\n[RUDP Server] Received packet from {client_address}:")
            print(f"  -> Seq: {seq_num}, Ack: {ack_num}, Flag: '{flag}', Payload Len: {data_len}")
            
            if flag == 'S':
                print("[RUDP Server] Received SYN packet. Client wants to connect.")
                # Respond with SYN-ACK (Flag 'A')
                response_header = struct.pack(HEADER_FORMAT, 0, seq_num + 1, b'A', 0)
                server_socket.sendto(response_header, client_address)
                print("[RUDP Server] Sent SYN-ACK response.")
                
            elif flag == 'D':
                # This is a data packet (e.g., the FETCH command)
                command = payload_bytes[:data_len].decode('utf-8')
                print(f"[RUDP Server] Received DATA command: {command}")
                
                # Acknowledge the data
                ack_header = struct.pack(HEADER_FORMAT, 0, seq_num + data_len, b'A', 0)
                server_socket.sendto(ack_header, client_address)
                print("[RUDP Server] Sent ACK for DATA.")
                
                # TODO: Later we will implement the actual HTTP Fetching logic here and send it back via RUDP
                
        except Exception as e:
            print(f"[RUDP Server] Error: {e}")

if __name__ == "__main__":
    start_rudp_server()