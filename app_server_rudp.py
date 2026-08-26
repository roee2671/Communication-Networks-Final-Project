# -----------------------------------------------------------------------------
# Module map: reliable file-transfer server built on UDP
#
# This server layers connection setup, acknowledgements, retransmissions, a
# Go-Back-N send window, and AIMD congestion control over ordinary UDP datagrams.
# The protocol constants and header layout must remain identical to the client.
# -----------------------------------------------------------------------------

import socket
import struct
import urllib.request


# RUDP App Server - Phase 3
# This server implements reliable file transfer over UDP using:
#   1. A custom 11-byte RUDP header per packet (Seq, Ack, Flag, DataLen).
#   2. Go-Back-N sliding window: multiple unACKed packets allowed in flight.
#      On timeout, retransmit from the oldest unACKed sequence number.
#   3. AIMD congestion control:
#      Additive Increase - window_size += 1 on each successful ACK.
#      Multiplicative Decrease - window_size //= 2 on timeout.
#
# The '!IIcH' header format must not be changed - it is shared with client_rudp.py.


APP_SERVER_IP = '127.0.0.3'  # Must match the DNS record for "my-app-server.local".
APP_PORT_RUDP = 2122          # Must match APP_PORT_RUDP in client_rudp.py.
BUFFER_SIZE   = 2048          # Large enough for header (11) + max chunk (500).
CHUNK_SIZE    = 500           # Maximum payload bytes per DATA packet.
MAX_WINDOW    = 5             # AIMD cap - window_size never exceeds this value.


# RUDP header format: 4+4+1+2 = 11 bytes total. DO NOT CHANGE.
# '!' = network byte order (big-endian)
# 'I' = unsigned int  (4 bytes) = Sequence Number
# 'I' = unsigned int  (4 bytes) = Acknowledgement Number
# 'c' = char          (1 byte)  = Flag byte (b'S', b'A', b'D', or b'F')
# 'H' = unsigned short(2 bytes) = Payload length in bytes
# Must be identical in client_rudp.py.
HEADER_FORMAT = '!IIcH'
HEADER_SIZE   = struct.calcsize(HEADER_FORMAT)  # = 11




def build_packet(seq_num, ack_num, flag, payload=b''):
    # Pack the 4 fields into an 11-byte header and append the payload.
    # flag must be a single bytes object: b'S', b'A', b'D', or b'F'.
    header = struct.pack(HEADER_FORMAT, seq_num, ack_num, flag, len(payload))
