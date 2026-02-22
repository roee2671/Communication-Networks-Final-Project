import socket
import urllib.request

# App Server (HTTP Proxy) - Phase 2
# This server acts as an HTTP proxy. The client sends a "FETCH <url>" command
# and this server downloads the resource using urllib and forwards the bytes back.
#
# TCP Framing:
# TCP is a stream protocol with no built-in message boundaries. To prevent partial
# reads, we prepend a 10-byte zero-padded length field before each payload.
# The receiver reads 10 bytes first, converts to int, then reads exactly that many more.

APP_SERVER_IP      = '127.0.0.3'  # Must match the DNS record for "my-app-server.local".
APP_SERVER_PORT    = 2121
BUFFER_SIZE        = 1024
LENGTH_HEADER_SIZE = 10           # Must match LENGTH_HEADER_SIZE in client.py.


def send_framed(sock, data):
    # TCP is a stream protocol, so we prepend a 10-byte length header to delimit messages.
    # Format: [10-char zero-padded length string][payload bytes]
    length_str = str(len(data)).zfill(LENGTH_HEADER_SIZE)
    header     = length_str.encode('utf-8')
    print(f"sending {len(data)} bytes (header='{length_str}')")
    sock.send(header + data)


def start_app_server():
    print("starting app server (HTTP proxy)...")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((APP_SERVER_IP, APP_SERVER_PORT))
    server_sock.listen(1)
    print(f"listening on TCP {APP_SERVER_IP}:{APP_SERVER_PORT}")

    while True:
        print("waiting for client connection...")
        client_sock, client_addr = server_sock.accept()
        print(f"client connected from {client_addr}")

        try:
            # Step 1: Read the 10-byte length header.
            print("reading length header...")
            header_bytes = client_sock.recv(LENGTH_HEADER_SIZE)

            if len(header_bytes) < LENGTH_HEADER_SIZE:
                print(f"header too short ({len(header_bytes)} bytes). closing.")
                client_sock.close()
                continue

            cmd_length = int(header_bytes.decode('utf-8'))
            print(f"command length: {cmd_length} bytes")

            # Step 2: Read exactly cmd_length bytes for the command string.
            print("reading command...")
            cmd_bytes = client_sock.recv(cmd_length)
            command   = cmd_bytes.decode('utf-8')
            print(f"received command: '{command}'")

            # Step 3: Dispatch on the command type.
            if command.startswith("FETCH "):
                url = command[len("FETCH "):]
                print(f"fetching: {url}")

                downloaded_bytes = None
                error_msg        = ""
                try:
                    req              = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    downloaded_bytes = urllib.request.urlopen(req, timeout=10).read()
                    print(f"download complete: {len(downloaded_bytes)} bytes")
                except Exception as e:
                    error_msg = str(e)
                    print(f"download failed: {e}")

                if downloaded_bytes is not None:
                    send_framed(client_sock, downloaded_bytes)
                else:
                    error_text = f"ERROR: Could not fetch '{url}'. Reason: {error_msg}"
                    send_framed(client_sock, error_text.encode('utf-8'))

            else:
                print(f"unknown command: '{command}'")
                send_framed(client_sock, b"ERROR: Unknown command. Use: FETCH <url>")

        except Exception as e:
            print(f"error handling client: {e}")

        print(f"closing connection with {client_addr}")
        client_sock.close()
        print("ready for next client.")


if __name__ == "__main__":
    start_app_server()
