# -----------------------------------------------------------------------------
# Module map: minimal DHCP service for the local network simulation
#
# It responds to a DISCOVER datagram with a JSON OFFER. The fixed addresses are
# intentional: they make the multi-process demonstration deterministic and easy
# to inspect in Wireshark.
# -----------------------------------------------------------------------------

import socket
import json


# DHCP Server - Phase 1
# DHCP (Dynamic Host Configuration Protocol) assigns IP addresses to clients
# when they first join a network. The client sends a DISCOVER broadcast and
# this server responds with an OFFER containing an available IP address.
# UDP is used because the client has no IP yet and cannot perform a TCP handshake.


SERVER_IP   = '127.0.0.1'
SERVER_PORT = 6767       # Standard DHCP uses port 67; we use 6767 to avoid requiring admin rights.
OFFERED_IP  = '127.0.0.2'  # The IP address assigned to all clients in this simulation.




def start_dhcp_server():
    print("starting DHCP server...")


    # SOCK_DGRAM creates a UDP socket.
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


    # SO_REUSEADDR prevents "Address already in use" errors when restarting during development.
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


    server_sock.bind((SERVER_IP, SERVER_PORT))
    print(f"DHCP server listening on {SERVER_IP}:{SERVER_PORT}")


    while True:
        print("waiting for DHCP request...")


        raw_data    = None
        client_addr = None
        try:
            raw_data, client_addr = server_sock.recvfrom(1024)
        except Exception as e:
            print(f"error receiving packet: {e}")
            continue
