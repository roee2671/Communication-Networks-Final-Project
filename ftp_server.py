import socket
import os

# Constants for the FTP server
FTP_SERVER_IP = '127.0.0.3'  # Fix: Changed to match the "my-ftp-server.local" record in dns_server.py
FTP_PORT_TCP = 2121           # Standard FTP is 21, we use 2121 for local dev
BUFFER_SIZE = 1024
LENGTH_HEADER_SIZE = 10       # Number of bytes reserved for the message length prefix

# Dummy list of files for now (we will change this to read from a real folder later)
AVAILABLE_FILES = ["test_file.txt", "network_summary.pdf", "image1.png"]

def send_framed(sock, payload_bytes):
    """Prepend a 10-byte zero-padded length header, then send the full payload in one call."""
    length_header = str(len(payload_bytes)).zfill(LENGTH_HEADER_SIZE).encode('utf-8')
    sock.send(length_header + payload_bytes)

def start_ftp_tcp_server():
    # 1. Create a TCP socket (SOCK_STREAM means TCP)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # SO_REUSEADDR lets us restart the server without "Address already in use" errors
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # 2. Bind and listen for incoming connections
    server_socket.bind((FTP_SERVER_IP, FTP_PORT_TCP))
    server_socket.listen(1)  # Listen for 1 connection at a time

    print(f"[FTP Server] Started. Listening on TCP {FTP_SERVER_IP}:{FTP_PORT_TCP}...")

    while True:
        # 3. Accept a client connection
        client_socket, client_address = server_socket.accept()
        print(f"\n[FTP Server] Client connected from {client_address}")

        # Use try/finally so client_socket is always closed, even if an error occurs mid-session
        try:
            # 4. Read the 10-byte header to find out how long the incoming command is
            raw_header = client_socket.recv(LENGTH_HEADER_SIZE)
            cmd_length = int(raw_header.decode('utf-8'))

            # 5. Read exactly that many bytes to get the full command text
            data = client_socket.recv(cmd_length).decode('utf-8')
            print(f"[FTP Server] Received command: '{data}'")

            # 6. Handle the "LIST" command — return a comma-separated list of available files
            if data == "LIST":
                files_string = ",".join(AVAILABLE_FILES)
                send_framed(client_socket, files_string.encode('utf-8'))
                print("[FTP Server] Sent file list to client.")

            # 7. Handle the "DOWNLOAD <filename>" command — send the file contents
            elif data.startswith("DOWNLOAD "):
                # Extract the filename: everything after the "DOWNLOAD " prefix
                filename = data[len("DOWNLOAD "):]
                print(f"[FTP Server] Client requested file: '{filename}'")

                if os.path.exists(filename):
                    # Read the file in binary mode so it works for any file type (text, image, pdf...)
                    with open(filename, 'rb') as f:
                        file_data = f.read()
                    send_framed(client_socket, file_data)
                    print(f"[FTP Server] Sent '{filename}' ({len(file_data)} bytes) to client.")
                else:
                    # File not found — send an error string using the same framing so client can read it
                    error_msg = f"ERROR: File '{filename}' not found on server."
                    send_framed(client_socket, error_msg.encode('utf-8'))
                    print(f"[FTP Server] '{filename}' not found, sent error to client.")

            else:
                error_msg = "ERROR: Unknown command."
                send_framed(client_socket, error_msg.encode('utf-8'))

        except Exception as e:
            print(f"[FTP Server] An error occurred: {e}")
        finally:
            # Always close the client socket to free up the connection
            client_socket.close()

if __name__ == "__main__":
    start_ftp_tcp_server()
