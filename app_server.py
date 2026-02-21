import socket
import urllib.request

# Pivot: This server is now an HTTP Proxy/Downloader (replaces the old FTP server).
# The client sends a "FETCH <url>" command, and this server fetches the URL from
# the real internet using Python's built-in urllib, then forwards the raw bytes
# back to the client using our standard 10-byte length-prefix framing.

APP_SERVER_IP = '127.0.0.3'  # Must match the "my-app-server.local" record in dns_server.py
APP_SERVER_PORT = 2121        # Port our custom application server listens on
BUFFER_SIZE = 1024
LENGTH_HEADER_SIZE = 10       # Number of bytes reserved for the message length prefix

def send_framed(sock, payload_bytes):
    """Prepend a 10-byte zero-padded length header, then send the full payload in one call."""
    length_header = str(len(payload_bytes)).zfill(LENGTH_HEADER_SIZE).encode('utf-8')
    sock.send(length_header + payload_bytes)

def start_app_server():
    # 1. Create a TCP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # SO_REUSEADDR lets us restart the server without "Address already in use" errors
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # 2. Bind and listen for incoming connections
    server_socket.bind((APP_SERVER_IP, APP_SERVER_PORT))
    server_socket.listen(1)

    print(f"[App Server] HTTP Proxy started. Listening on TCP {APP_SERVER_IP}:{APP_SERVER_PORT}...")

    while True:
        # 3. Accept a client connection
        client_socket, client_address = server_socket.accept()
        print(f"\n[App Server] Client connected from {client_address}")

        # Use try/finally so client_socket is always closed, even if an error occurs
        try:
            # 4. Read the 10-byte header to find out how long the incoming command is
            raw_header = client_socket.recv(LENGTH_HEADER_SIZE)
            cmd_length = int(raw_header.decode('utf-8'))

            # 5. Read exactly that many bytes to get the full command text
            data = client_socket.recv(cmd_length).decode('utf-8')
            print(f"[App Server] Received command: '{data}'")

            # 6. Handle the "FETCH <url>" command — act as an HTTP proxy
            if data.startswith("FETCH "):
                # Extract the URL: everything after the "FETCH " prefix
                url = data[len("FETCH "):]
                print(f"[App Server] Fetching from internet: {url}")

                try:
                    # Use a browser-like User-Agent header so servers don't reject the request
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    # urlopen makes the real HTTP request; .read() downloads the full response body
                    web_content = urllib.request.urlopen(req, timeout=10).read()
                    send_framed(client_socket, web_content)
                    print(f"[App Server] Fetched {len(web_content)} bytes, sent to client.")
                except Exception as fetch_error:
                    # If the real HTTP request fails, send a framed error so the client can read it
                    error_msg = f"ERROR: Could not fetch URL '{url}'. Reason: {fetch_error}"
                    send_framed(client_socket, error_msg.encode('utf-8'))
                    print(f"[App Server] Fetch failed: {fetch_error}")

            else:
                error_msg = "ERROR: Unknown command. Use: FETCH <url>"
                send_framed(client_socket, error_msg.encode('utf-8'))

        except Exception as e:
            print(f"[App Server] An error occurred: {e}")
        finally:
            # Always close the client socket to free up the connection
            client_socket.close()

if __name__ == "__main__":
    start_app_server()
