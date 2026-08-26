# -----------------------------------------------------------------------------
# Module map: minimal DNS service for the local network simulation
#
# It resolves the single simulated application hostname to the loopback address
# used by the application server. JSON keeps the request and response format
# visible while debugging the UDP exchange.
# -----------------------------------------------------------------------------

import socket
import json


# DNS Server - Phase 1
# DNS (Domain Name System) resolves human-readable domain names to IP addresses.
# This implementation uses a static dictionary as the DNS record store.
# UDP is used because DNS queries are small and latency is more important than reliability.


SERVER_IP   = '127.0.0.1'
SERVER_PORT = 5353  # Standard DNS uses port 53; we use 5353 to avoid requiring admin rights.


# Static DNS records - maps domain names to IP addresses.
DNS_RECORDS = {
    "my-app-server.local" : "127.0.0.3",   # Must match APP_SERVER_IP in app_server.py.
    "google.com"          : "8.8.8.8"
}




def start_dns_server():
    print("starting DNS server...")


    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((SERVER_IP, SERVER_PORT))
    print(f"DNS server listening on {SERVER_IP}:{SERVER_PORT}")


    while True:
        print("waiting for DNS query...")


        raw_data    = None
        client_addr = None
        try:
            raw_data, client_addr = server_sock.recvfrom(1024)
        except Exception as e:
            print(f"error receiving packet: {e}")
            continue
