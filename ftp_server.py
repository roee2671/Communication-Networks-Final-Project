import socket

# Constants for the FTP server
FTP_SERVER_IP = '127.0.0.1'
FTP_PORT_TCP = 2121 # Standard FTP is 21, we use 2121 for local dev
BUFFER_SIZE = 1024

# Dummy list of files for now (we will change this to read from a real folder later)
AVAILABLE_FILES = ["test_file.txt", "network_summary.pdf", "image1.png"]

def start_ftp_tcp_server():
    # 1. Create a TCP socket (SOCK_STREAM means TCP)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # 2. Bind and listen for incoming connections
    server_socket.bind((FTP_SERVER_IP, FTP_PORT_TCP))
    server_socket.listen(1) # Listen for 1 connection at a time
    
    print(f"[FTP Server] Started. Listening on TCP {FTP_SERVER_IP}:{FTP_PORT_TCP}...")
    
    while True:
        try:
            # 3. Accept a client connection
            client_socket, client_address = server_socket.accept()
            print(f"\n[FTP Server] Client connected from {client_address}")
            
            # 4. Receive the command from the client
            data = client_socket.recv(BUFFER_SIZE).decode('utf-8')
            print(f"[FTP Server] Received command: {data}")
            
            # 5. Handle the "LIST" command
            if data == "LIST":
                # Convert our list of files to a single string separated by commas
                files_string = ",".join(AVAILABLE_FILES)
                client_socket.send(files_string.encode('utf-8'))
                print("[FTP Server] Sent file list to client.")
            else:
                error_msg = "ERROR: Unknown command."
                client_socket.send(error_msg.encode('utf-8'))
                
            # Close the connection for this client (for now, simple one-off connection)
            client_socket.close()
            
        except Exception as e:
            print(f"[FTP Server] An error occurred: {e}")

if __name__ == "__main__":
    start_ftp_tcp_server()