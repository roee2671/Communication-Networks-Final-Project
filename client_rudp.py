# -----------------------------------------------------------------------------
# Module map: reliable-UDP network-simulation client
#
# This client first completes DHCP and DNS setup, then speaks the custom UDP
# protocol: handshake, command acknowledgement, ordered data receipt, and FIN.
# Optional loss and latency switches deliberately exercise recovery behaviour.
# -----------------------------------------------------------------------------

import socket
import struct
import json
import random
import time


# RUDP Client - Phase 3
# Performs the full DHCP -> DNS -> RUDP initialization sequence.
#
# RUDP receive logic (Go-Back-N receiver):
#   In-order packet (seq == expected_seq): buffer it, ACK it, advance expected_seq.
#   Out-of-order packet (seq != expected_seq): discard it, send a cumulative ACK
#     for the last successfully received sequence number. This signals the server
#     to retransmit from the gap position.
#   FIN packet: ACK it and exit the receive loop.
#
# Simulation flags:
#   SIMULATE_PACKET_LOSS: randomly drops ~30% of incoming DATA packets without
#     sending an ACK, forcing the server's 1-second timeout to fire and proving
#     retransmission works.
#   SIMULATE_LATENCY: adds a random delay before processing each packet to
#     simulate network latency, as required by the assignment.
#
# The '!IIcH' header format must match app_server_rudp.py exactly.


DHCP_SERVER_IP   = '127.0.0.1'
DHCP_SERVER_PORT = 6767
DNS_SERVER_IP    = '127.0.0.1'
DNS_SERVER_PORT  = 5353
APP_PORT_RUDP    = 2122   # Must match APP_PORT_RUDP in app_server_rudp.py.
BUFFER_SIZE      = 2048   # Large enough for header (11) + max chunk (500).
TIMEOUT          = 5.0
TARGET_DOMAIN    = "my-app-server.local"


SIMULATE_PACKET_LOSS = True   # Drop ~30% of incoming DATA chunks to test retransmission.
SIMULATE_LATENCY     = True   # Using time.sleep to simulate network latency as required by the assignment.
