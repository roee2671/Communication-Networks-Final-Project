import socket

# Constants for the FTP server
FTP_SERVER_IP = '127.0.0.3'  # Fix: Changed to match the "my-ftp-server.local" record in dns_server.py
FTP_PORT_TCP = 2121           # Standard FTP is 21, we use 2121 for local dev
BUFFER_SIZE = 1024
LENGTH_HEADER_SIZE = 10       # Fix: Number of bytes reserved for the message length prefix

# Dummy list of files for now (we will change this to read from a real folder later)
AVAILABLE_FILES = ["test_file.txt", "network_summary.pdf", "image1.png"]

def start_ftp_tcp_server():
    # 1. Create a TCP socket (SOCK_STREAM means TCP)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Fix: SO_REUSEADDR lets us restart the server without "Address already in use" errors
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # 2. Bind and listen for incoming connections
    server_socket.bind((FTP_SERVER_IP, FTP_PORT_TCP))
    server_socket.listen(1)  # Listen for 1 connection at a time

    print(f"[FTP Server] Started. Listening on TCP {FTP_SERVER_IP}:{FTP_PORT_TCP}...")

    while True:
        # 3. Accept a client connection
        client_socket, client_address = server_socket.accept()
        print(f"\n[FTP Server] Client connected from {client_address}")

        # Fix: Use try/finally so client_socket is always closed, even if an error occurs mid-session
        try:
            # 4. Receive the command from the client
            data = client_socket.recv(BUFFER_SIZE).decode('utf-8')
            print(f"[FTP Server] Received command: {data}")

            # 5. Handle the "LIST" command
            if data == "LIST":
                # Convert our list of files to a single string separated by commas
                files_string = ",".join(AVAILABLE_FILES)
                payload = files_string.encode('utf-8')
                # Fix: Prepend a 10-byte length header so the client knows exactly how many bytes to read
                length_header = str(len(payload)).zfill(LENGTH_HEADER_SIZE).encode('utf-8')
                client_socket.send(length_header + payload)
                print("[FTP Server] Sent file list to client.")
            else:
                error_msg = "ERROR: Unknown command."
                payload = error_msg.encode('utf-8')
                length_header = str(len(payload)).zfill(LENGTH_HEADER_SIZE).encode('utf-8')
                client_socket.send(length_header + payload)

        except Exception as e:
            print(f"[FTP Server] An error occurred: {e}")
        finally:
            # Fix: Always close the client socket to free up the connection
            client_socket.close()

if __name__ == "__main__":
    start_ftp_tcp_server()
