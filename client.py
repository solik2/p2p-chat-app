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
    """Get public endpoint using multiple STUN servers"""
    results = []
    
    for stun_server in config['stun']['servers']:
        try:
            print(f"\nTrying STUN server: {stun_server['host']}:{stun_server['port']}")
            nat_type, external_ip, external_port = stun.get_ip_info(
                stun_host=stun_server['host'],
                stun_port=stun_server['port']
            )
            if external_ip and external_port:
                results.append({
                    'nat_type': nat_type,
                    'ip': external_ip,
                    'port': external_port,
                    'server': stun_server['host']
                })
                print(f"✓ Success: {nat_type} NAT, endpoint: {external_ip}:{external_port}")
            else:
                print(f"✗ Failed: No endpoint received")
        except Exception as e:
            print(f"✗ Error with {stun_server['host']}: {e}")
    
    if not results:
        print("\n⚠️ All STUN servers failed. Falling back to local IP")
        local_ip = socket.gethostbyname(socket.gethostname())
        return local_ip, 0, "Unknown"
    
    # Analyze results
    nat_types = set(r['nat_type'] for r in results)
    ips = set(r['ip'] for r in results)
    
    print("\nNAT Analysis:")
    print(f"Detected NAT types: {', '.join(nat_types)}")
    print(f"Detected IPs: {', '.join(ips)}")
    
    # Use the most common result
    from collections import Counter
    ip_counter = Counter(r['ip'] for r in results)
    most_common_ip = ip_counter.most_common(1)[0][0]
    
    # Find the corresponding port for the most common IP
    for r in results:
        if r['ip'] == most_common_ip:
            print(f"\nSelected endpoint: {r['ip']}:{r['port']} (NAT: {r['nat_type']})")
            return r['ip'], r['port'], r['nat_type']
    
    # Fallback to first result if no common IP found
    print(f"\nFalling back to first valid result")
    return results[0]['ip'], results[0]['port'], results[0]['nat_type']

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

def create_socket():
    """Create and configure UDP socket for P2P communication"""
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Enable broadcasting and reuse address
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Increase socket buffers for better performance
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
    
    # Bind to all interfaces but with a specific port
    udp_socket.bind(('', 0))
    
    return udp_socket

def establish_connection(udp_socket, peer_endpoint):
    """Establish connection with peer using simultaneous UDP hole punching"""
    print("\nInitiating simultaneous UDP hole punching...")
    print(f"Local endpoint: {udp_socket.getsockname()}")
    print(f"Peer endpoint: {peer_endpoint}")
    
    if config['client'].get('cgnat_mode', False):
        print("CGNAT mode enabled - using aggressive hole punching")
    
    connection_established = False
    received_punch = False
    sent_punch = False
    
    def send_punch_packets():
        """Send burst of punch packets"""
        for _ in range(5):
            try:
                udp_socket.sendto(b'PUNCH', peer_endpoint)
                time.sleep(0.05)
            except Exception as e:
                print(f"Error sending punch packet: {e}")
    
    # Start with aggressive burst
    send_punch_packets()
    
    # Main connection loop
    start_time = time.time()
    while time.time() - start_time < config['client']['punch_timeout']:
        try:
            # Send periodic punch packets
            if time.time() - start_time > 2 and not sent_punch:  # After 2 seconds
                print("Sending additional punch packets...")
                send_punch_packets()
                sent_punch = True
            
            # Try to receive
            udp_socket.settimeout(1)
            try:
                data, addr = udp_socket.recvfrom(4096)
                message = data.decode()
                print(f"Received {message} from {addr}")
                
                if message == 'PUNCH':
                    print("Received PUNCH - sending ACK")
                    udp_socket.sendto(b'ACK', addr)
                    received_punch = True
                elif message == 'ACK':
                    print("Received ACK - connection established!")
                    connection_established = True
                    break
                
                # In CGNAT mode, consider connection established if we've both sent and received packets
                if config['client'].get('cgnat_mode', False) and received_punch and sent_punch:
                    print("CGNAT: Bidirectional communication established!")
                    connection_established = True
                    break
                
            except socket.timeout:
                continue
            
        except Exception as e:
            print(f"Error during hole punching: {e}")
            time.sleep(0.5)
    
    # Reset socket timeout
    udp_socket.settimeout(None)
    
    if connection_established:
        print("\n✓ P2P Connection established successfully!")
    else:
        print("\n✗ Failed to establish P2P connection")
        if received_punch:
            print("  → Received PUNCH but no ACK")
        elif sent_punch:
            print("  → Sent PUNCH but no response")
        else:
            print("  → No packets exchanged")
    
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
    print(f"Public endpoint: {public_ip}:{public_port}")
    print(f"NAT type: {nat_type}")

    # Create and configure UDP socket
    udp_socket = create_socket()
    local_port = udp_socket.getsockname()[1]
    print(f"Local UDP socket bound to: {udp_socket.getsockname()}")

    # If STUN failed to get a port, use the local port
    if public_port == 0:
        public_port = local_port
        print("Using local port as public port")

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