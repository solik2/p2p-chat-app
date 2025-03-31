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
            message = data.decode()
            if message == 'KEEPALIVE' or message == 'PUNCH':
                # Send acknowledgment for connection establishment
                udp_socket.sendto(b'ACK', addr)
                continue
            elif message == 'ACK':
                continue
            print(f"\n[Message from {addr}]: {message}")
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

def register_with_server(username, ip, port):
    """Register with the server and handle retries"""
    max_retries = 3
    retry_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            payload = {
                'username': username,
                'ip': ip,
                'port': port
            }
            r = requests.post(f"{SERVER_URL}/register", json=payload)
            r.raise_for_status()
            print("Successfully registered with rendezvous server.")
            print(f"Active peers: {r.json().get('active_peers', 0)}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Registration attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print("Registration failed after all attempts.")
                return False

def discover_peer(target_username, max_attempts=30, delay=2):
    """Discover peer with retry logic"""
    print(f"Looking for peer {target_username}...")
    
    for attempt in range(max_attempts):
        try:
            r = requests.get(f"{SERVER_URL}/get_peer/{target_username}")
            if r.status_code == 200:
                peer_info = r.json()
                return (peer_info['ip'], peer_info['port'])
            elif r.status_code == 404:
                if attempt < max_attempts - 1:
                    print(f"Peer not found. Retrying in {delay} seconds... (attempt {attempt + 1}/{max_attempts})")
                    time.sleep(delay)
                continue
            else:
                r.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Error contacting rendezvous server: {e}")
            if attempt < max_attempts - 1:
                time.sleep(delay)
            continue
    
    return None

def establish_connection(udp_socket, peer_endpoint):
    """Establish connection with peer using UDP hole punching"""
    print("\nInitiating UDP hole punching...")
    connection_established = False
    
    for i in range(config['client']['punch_attempts']):
        try:
            udp_socket.sendto(b'PUNCH', peer_endpoint)
            # Set a timeout for receiving ACK
            udp_socket.settimeout(1)
            try:
                data, addr = udp_socket.recvfrom(1024)
                if data.decode() == 'ACK':
                    print("Connection established!")
                    connection_established = True
                    break
            except socket.timeout:
                pass
        except Exception as e:
            print(f"Error during hole punching: {e}")
        
        if i < config['client']['punch_attempts'] - 1:
            time.sleep(config['client']['punch_interval'])
    
    # Reset socket timeout
    udp_socket.settimeout(None)
    return connection_established

def main():
    print(f"Connecting to rendezvous server at {SERVER_URL}")
    
    try:
        r = requests.get(SERVER_URL)
        r.raise_for_status()
        print("Server status:", r.json())
    except Exception as e:
        print(f"Error checking server status: {e}")
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

    # Register with the server
    if not register_with_server(username, public_ip, public_port):
        return

    # Start registration refresh thread
    def refresh_registration():
        while True:
            time.sleep(240)  # Refresh every 4 minutes
            register_with_server(username, public_ip, public_port)
    
    refresh_thread = threading.Thread(target=refresh_registration, daemon=True)
    refresh_thread.start()

    # Discover peer with retry
    peer_endpoint = discover_peer(target_username)
    if not peer_endpoint:
        print(f"Failed to find peer {target_username} after multiple attempts.")
        return

    print(f"Found peer endpoint: {peer_endpoint}")

    # Start a listener thread to receive messages
    listener_thread = threading.Thread(target=listen_for_messages, args=(udp_socket,), daemon=True)
    listener_thread.start()

    # Establish connection
    if not establish_connection(udp_socket, peer_endpoint):
        print("Failed to establish connection with peer.")
        return

    # Start a keep-alive thread to maintain NAT bindings
    ka_thread = threading.Thread(target=send_keepalive, args=(udp_socket, peer_endpoint), daemon=True)
    ka_thread.start()

    print("\nConnection established! You can now start chatting.")
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