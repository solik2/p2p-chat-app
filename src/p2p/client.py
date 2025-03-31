import socket
import threading
import requests
import time
import stun  # Requires a STUN client library such as pystun3
import json
import os
from datetime import datetime

# Load configuration
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config', 'chat_config.json')
with open(config_path) as f:
    config = json.load(f)

# Build server URL with proper protocol
SERVER_URL = f"{'https' if config['server']['use_https'] else 'http'}://{config['server']['host']}"
if (not config['server']['use_https'] and config['server']['port'] != 80) or \
   (config['server']['use_https'] and config['server']['port'] != 443):
    SERVER_URL += f":{config['server']['port']}"

def get_public_endpoint():
    try:
        # Uses the STUN library to determine public endpoint and NAT type.
        nat_type, external_ip, external_port = stun.get_ip_info(
            stun_host=config['stun']['server'],
            stun_port=config['stun']['port']
        )
        if not external_ip or not external_port:
            # If STUN fails, use local IP as fallback for testing
            external_ip = socket.gethostbyname(socket.gethostname())
            external_port = 0  # Let the OS choose a port
        return external_ip, external_port, nat_type
    except Exception as e:
        print(f"STUN error: {e}")
        # Fallback to local IP for testing
        return socket.gethostbyname(socket.gethostname()), 0, "Unknown"

def listen_for_messages(udp_socket):
    while True:
        try:
            data, addr = udp_socket.recvfrom(1024)
            if data == b'KEEPALIVE' or data == b'PUNCH':
                continue
            print(f"\n[Message from {addr}]: {data.decode()}")
            print("> ", end='', flush=True)
        except Exception as e:
            print("Error receiving message:", e)
            break

def send_keepalive(udp_socket, peer_endpoint):
    while True:
        try:
            # Send a simple keep-alive packet to maintain NAT binding
            udp_socket.sendto(b'KEEPALIVE', peer_endpoint)
            time.sleep(config['client']['keepalive_interval'])
        except Exception as e:
            print("Keep-alive error:", e)
            break

def check_server_status():
    try:
        r = requests.get(SERVER_URL)
        r.raise_for_status()
        print("Server status:", r.json())
        return True
    except Exception as e:
        print(f"Error checking server status: {e}")
        return False

def main():
    print(f"Connecting to rendezvous server at {SERVER_URL}")
    
    if not check_server_status():
        print("Failed to connect to the server. Please try again later.")
        return

    username = input("Enter your username: ").strip()
    target_username = input("Enter target username to chat with: ").strip()

    # Discover public IP, port, and NAT type using STUN
    public_ip, public_port, nat_type = get_public_endpoint()
    print(f"Discovered endpoint: {public_ip}:{public_port} (NAT type: {nat_type})")

    # Create a UDP socket and bind it to an available local port.
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind(('', 0))
    local_port = udp_socket.getsockname()[1]
    print(f"Local UDP socket bound on port {local_port}")

    # If STUN failed to get a port, use the local port
    if public_port == 0:
        public_port = local_port

    # Register our public endpoint with the rendezvous server.
    payload = {
        'username': username,
        'ip': public_ip,
        'port': public_port
    }
    try:
        r = requests.post(f"{SERVER_URL}/register", json=payload)
        r.raise_for_status()  # Raise an exception for bad status codes
        print("Successfully registered with rendezvous server.")
        print(f"Active peers: {r.json().get('active_peers', 0)}")
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to rendezvous server: {e}")
        return

    # Retrieve the target peer's public endpoint from the server.
    try:
        r = requests.get(f"{SERVER_URL}/get_peer/{target_username}")
        r.raise_for_status()  # Raise an exception for bad status codes
        peer_info = r.json()
        peer_endpoint = (peer_info['ip'], peer_info['port'])
        print(f"Target peer endpoint: {peer_endpoint}")
    except requests.exceptions.RequestException as e:
        print(f"Error contacting rendezvous server: {e}")
        return

    # Start a listener thread to receive messages
    listener_thread = threading.Thread(target=listen_for_messages, args=(udp_socket,), daemon=True)
    listener_thread.start()

    # Start a keep-alive thread to maintain NAT bindings
    ka_thread = threading.Thread(target=send_keepalive, args=(udp_socket, peer_endpoint), daemon=True)
    ka_thread.start()

    # Begin UDP hole punching: send several initial packets to the peer.
    print("Initiating UDP hole punching...")
    for i in range(config['client']['punch_attempts']):
        udp_socket.sendto(b'PUNCH', peer_endpoint)
        time.sleep(config['client']['punch_interval'])

    print("\nYou can now start chatting. Type your messages and press enter.")
    print("Press Ctrl+C to exit.")
    while True:
        try:
            message = input("> ")
            if message.strip() == "":
                continue
            udp_socket.sendto(message.encode(), peer_endpoint)
        except KeyboardInterrupt:
            print("\nExiting chat.")
            break
        except Exception as e:
            print("Error sending message:", e)
            break

if __name__ == '__main__':
    main() 