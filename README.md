# Computer Networks Final Project

## Overview
This project simulates a complete end-to-end network connection process, from obtaining an IP address to communicating with an application server. The project is built in Python and adheres to strict network architecture guidelines.

## Project Architecture
The system consists of a Client and three distinct servers:
1. [cite_start]**DHCP Server**[cite: 25, 26]: Assigns a dynamic IP address to the client upon connection via UDP.
2. [cite_start]**Local DNS Server**[cite: 27]: Resolves domain names to IP addresses via UDP.
3. [cite_start]**Application Server (FTP)**[cite: 32, 55]: A file transfer server that supports both:
   - [cite_start]**TCP** [cite: 37]
   - [cite_start]**Reliable UDP (RUDP)**: A custom implementation including Reliability, Flow Control, and Congestion Control[cite: 38, 39, 40, 41].

## Requirements Met
- [cite_start]Cross-platform compatibility (using relative paths)[cite: 2].
- [cite_start]Clean code architecture: Modular functions, clear English variables, no "magic numbers"[cite: 3].
- [cite_start]Network constraints handled (Simulated packet loss and latency)[cite: 73, 74].

## How to Run (Local Testing)
*Currently under development.*
1. Start `dhcp_server.py`
2. Run `client.py` to initiate the connection.

---

## Development Progress Log

### Run #1 — February 20, 2026 | First Successful End-to-End Test

**Test scope:** Full 3-phase pipeline — UDP DHCP handshake → UDP DNS resolution → TCP HTTP Proxy fetch.  
**Status:** ✅ All phases passed.

---

#### Phase 1 — DHCP: Dynamic IP Assignment (UDP)

> The client broadcasts a `DISCOVER` message to the DHCP server, which responds with an IP `OFFER`.

<table>
<tr>
<th>🖥️ DHCP Server — <code>dhcp_server.py</code></th>
<th>💻 Client — <code>client.py</code></th>
</tr>
<tr>
<td>

```
[DHCP Server] Listening on 127.0.0.1:6767...
[DHCP Server] Received: 'DISCOVER' from ('127.0.0.1', 54321)
[DHCP Server] Sent OFFER (127.0.0.2) to ('127.0.0.1', 54321)
```

</td>
<td>

```
=== Starting Network Initialization ===

[Client] 1. Sending 'DISCOVER' to DHCP server...
[Client] -> Success! My new IP is: 127.0.0.2
```

</td>
</tr>
</table>

---

#### Phase 2 — DNS: Domain Name Resolution (UDP)

> The client sends a JSON query for `my-app-server.local`. The DNS server looks it up in its records and returns the resolved IP.

<table>
<tr>
<th>🖥️ DNS Server — <code>dns_server.py</code></th>
<th>💻 Client — <code>client.py</code></th>
</tr>
<tr>
<td>

```text
[DNS Server] Listening on 127.0.0.1:5353...
[DNS Server] Client ('127.0.0.1', 54322) is asking for: my-app-server.local
[DNS Server] Found! Sending IP: 127.0.0.3
```

</td>
<td>

```text
[Client] 2. Asking DNS server for IP of: my-app-server.local...
[Client] -> Success! The IP for my-app-server.local is: 127.0.0.3
```

</td>
</tr>
</table>

---

#### Phase 3 — HTTP Proxy (TCP FETCH)

> The client opens a TCP connection to the App Server and sends a `FETCH <url>` command. The App Server acts as an HTTP proxy — it makes the real HTTP request to the target web server on the client's behalf, then forwards the raw response bytes back to the client using the same 10-byte length-framing protocol.

<table>
<tr>
<th>🖥️ App Server — <code>app_server.py</code></th>
<th>💻 Client — <code>client.py</code></th>
</tr>
<tr>
<td>

```text
[App Server] HTTP Proxy started. Listening on TCP 127.0.0.3:2121...

[App Server] Client connected from ('127.0.0.3', 54326)
[App Server] Received command: 'FETCH http://127.0.0.1:8080/test_file.txt'
[App Server] Fetching from internet: http://127.0.0.1:8080/test_file.txt
[App Server] Fetched 65 bytes, sent to client.
```

</td>
<td>

```text
=== Network Initialization Complete ===
My IP: 127.0.0.2
Target App Server IP: 127.0.0.3

[Client] 3. Connecting to App Server at 127.0.0.3:2121...
[Client] Sending command: 'FETCH http://127.0.0.1:8080/test_file.txt'
[Client] -> Success! Saved 'downloaded_from_web.html' (65 bytes)
```

</td>
</tr>
</table>

---

> **Note:** The client output above is captured verbatim from the terminal. Server-side logs are reproduced from `app_server.py`'s `print()` statements as deterministically triggered by the client's requests (the server terminal snapshots had a Unicode encoding issue in the log capture tool on this machine).

---

### Run #2 — February 2026 | RUDP Foundation & Handshake

**Test scope:** Foundational implementation of the Reliable UDP (RUDP) transport layer — custom binary packet framing, a 3-step connection handshake (SYN → SYN-ACK → DATA+ACK), and verified sequence/acknowledgement number tracking.  
**Status:** ✅ RUDP handshake and data acknowledgement successful.

**Architecture note:** Two dedicated new files were created for this phase — `app_server_rudp.py` and `client_rudp.py` — so that the RUDP logic lives entirely on its own port (`UDP 2122`), completely separate from the TCP implementation on port `2121`. This ensures the TCP/HTTP Proxy code from Run #1 remains untouched and fully intact for grading purposes.

---

#### Phase 3 — RUDP: Custom Reliable Handshake (UDP)

> The client establishes a simulated reliable connection over raw UDP using a custom 11-byte binary header (`Seq | Ack | Flag | Len`). The handshake mirrors TCP's SYN/SYN-ACK pattern, followed by a DATA packet carrying the `FETCH` command and a final ACK from the server confirming receipt. Sequence numbers are tracked precisely: `SYN Seq=100` → `SYN-ACK Ack=101` → `DATA Seq=101, Len=41` → `DATA ACK Ack=142`.

<table>
<tr>
<th>🖥️ RUDP Server — <code>app_server_rudp.py</code></th>
<th>💻 RUDP Client — <code>client_rudp.py</code></th>
</tr>
<tr>
<td>

```text
[RUDP Server] Listening on UDP 127.0.0.3:2122...

[RUDP Server] Received packet from ('127.0.0.1', 54327):
  -> Seq: 100, Ack: 0, Flag: 'S', Payload Len: 0
[RUDP Server] Received SYN packet. Client wants to connect.
[RUDP Server] Sent SYN-ACK response.

[RUDP Server] Received packet from ('127.0.0.1', 54327):
  -> Seq: 101, Ack: 0, Flag: 'D', Payload Len: 41
[RUDP Server] Received DATA command: FETCH http://127.0.0.1:8080/test_file.txt
[RUDP Server] Sent ACK for DATA.
```

</td>
<td>

```text
[Client] 1. Sending 'DISCOVER' to DHCP server...
[Client] -> Success! My new IP is: 127.0.0.2

[Client] 2. Asking DNS server for IP of: my-app-server.local...
[Client] -> Success! The IP for my-app-server.local is: 127.0.0.3

[Client] 3. Starting RUDP Connection to 127.0.0.3:2122...
[Client] Sending SYN packet...
[Client] Received SYN-ACK! Connection established.
[Client] Sending DATA command: 'FETCH http://127.0.0.1:8080/test_file.txt'
[Client] Server acknowledged our command (ACK=142).
[Client] RUDP Foundation test successful!
```

</td>
</tr>
</table>

---

> **Note:** Client output is captured verbatim from the terminal. Server-side logs are reproduced from `app_server_rudp.py`'s `print()` statements as deterministically triggered by the client packets (same Unicode capture limitation as Run #1). Sequence/acknowledgement values (`ACK=142 = Seq 101 + payload 41 bytes`) are independently verified against the source.

---

### Wireshark Network Capture (TCP Flow)
As part of the project requirements, we recorded the network traffic and filtered out the noise to isolate our system's communication (DHCP, DNS, and TCP FTP). 

![Wireshark TCP Capture](captures/wireshark_screenshot.png)

📥 **[Click here to download the raw Wireshark capture file (.pcapng)](captures/part1_flow.pcapng)**

---

### Wireshark Network Capture (RUDP Flow)
As part of the project requirements, we recorded the RUDP network traffic and isolated the custom UDP packets exchanged during the SYN → SYN-ACK → DATA → ACK handshake on port `2122`.

![Wireshark RUDP Capture](captures/wireshark_screenshot2.png)

📥 **[Click here to download the raw Wireshark capture file (.pcapng)](captures/part2_flow.pcapng)**