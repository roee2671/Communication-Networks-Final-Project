# -----------------------------------------------------------------------------
# Module map: TCP application server / HTTP proxy
#
# The client sends a framed FETCH command. This module downloads the requested
# resource and returns its bytes using the same length-prefixed TCP framing.
# Keeping command handling and framing together makes the request/response
# boundary explicit, despite TCP being a byte stream rather than a message bus.
# -----------------------------------------------------------------------------

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

