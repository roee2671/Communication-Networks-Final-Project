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

        if raw_data is None:
            continue

        text = raw_data.decode('utf-8')
        print(f"received query from {client_addr}: {text}")

        # Validate that the data is JSON before attempting to parse it.
        if len(text) == 0 or text[0] != '{':
            print("received data is not valid JSON. ignoring.")
            continue

        request = None
        try:
            request = json.loads(text)
        except Exception as e:
            print(f"JSON parse error: {e}. ignoring.")
            continue

        if request is None:
            continue

        # Defensive check - verify the required key exists before accessing it.
        if "domain" not in request:
            print("request is missing 'domain' field. sending error.")
            error_response = {"status": "ERROR", "ip": None}
            server_sock.sendto(json.dumps(error_response).encode('utf-8'), client_addr)
            continue

        domain = request["domain"]
        print(f"looking up: '{domain}'")

        if domain in DNS_RECORDS:
            ip_address = DNS_RECORDS[domain]
            response   = {"status": "SUCCESS", "ip": ip_address}
            print(f"found: {domain} -> {ip_address}")
        else:
            response = {"status": "NOT_FOUND", "ip": None}
            print(f"domain '{domain}' not found.")

        response_bytes = json.dumps(response).encode('utf-8')
        server_sock.sendto(response_bytes, client_addr)
        print(f"response sent to {client_addr}")


if __name__ == "__main__":
    start_dns_server()
