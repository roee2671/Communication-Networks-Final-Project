# -----------------------------------------------------------------------------
# Module map: TCP network-simulation client
#
# The client performs the simulated DHCP -> DNS -> application-server sequence,
# then saves the byte stream returned by the TCP proxy. Framing helpers are kept
# here so the client consumes exactly one application-level message at a time.
# -----------------------------------------------------------------------------

import socket
import json


# TCP Client - Phase 1 and 2
# Performs the full network initialization sequence:
#   Step 1 - DHCP: request an IP address.
#   Step 2 - DNS:  resolve the app server's domain name to an IP.
#   Step 3 - App:  connect over TCP, send a FETCH command, receive the file.
#
# TCP Framing:
# TCP is a stream protocol, so we prepend a 10-byte length header to avoid
# fragmentation issues. The receiver reads 10 bytes first to determine message length.


DHCP_SERVER_IP     = '127.0.0.1'
DHCP_SERVER_PORT   = 6767
DNS_SERVER_IP      = '127.0.0.1'
DNS_SERVER_PORT    = 5353
BUFFER_SIZE        = 1024
TIMEOUT            = 5.0
TARGET_DOMAIN      = "my-app-server.local"
APP_SERVER_PORT    = 2121  # Must match APP_SERVER_PORT in app_server.py.
LENGTH_HEADER_SIZE = 10    # Must match LENGTH_HEADER_SIZE in app_server.py.




def send_framed(sock, text):
    # Encode the text to bytes and prepend a 10-byte zero-padded length header.
    cmd_bytes  = text.encode('utf-8')
    length_str = str(len(cmd_bytes)).zfill(LENGTH_HEADER_SIZE)
    header     = length_str.encode('utf-8')
    print(f"sending: '{text}' ({len(cmd_bytes)} bytes)")
    sock.send(header + cmd_bytes)




def receive_framed(sock):
    # Read the 10-byte length header, then loop until all expected bytes are received.
    # TCP may deliver data in fragments, so a single recv() call is not sufficient.
