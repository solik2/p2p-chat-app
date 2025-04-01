import asyncio
import json
import logging
import socket
import time
import sys
import requests

logging.basicConfig(level=logging.INFO)

# Port constants
LOCAL_PORT = 5000  # Fixed internal port for both peers
MIN_PORT_RANGE = 10000  # Typical lower bound for NAT-assigned ports
MAX_PORT_RANGE = 65535  # Maximum port number
PORT_ATTEMPT_BATCH = 200  # Number of ports to try in each batch

def get_public_ip():
    """Get the public IP address of this machine"""
    try:
        response = requests.get('https://api.ipify.org?format=json')
        return response.json()['ip']
    except:
        return None

class P2PChat:
    def __init__(self, my_public_ip, peer_public_ip, is_peer_a):
        self.sock = None
        self.my_public_ip = my_public_ip
        self.peer_public_ip = peer_public_ip
        self.is_peer_a = is_peer_a
        self.remote_port = None
        self.stop_punching = False
        self.connected = asyncio.Event()
        
    async def setup(self):
        """Setup UDP socket"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', LOCAL_PORT))
        self.sock.setblocking(False)
        logging.info(f"Bound to local port {LOCAL_PORT}")
        logging.info(f"My Public IP: {self.my_public_ip}")
        logging.info(f"Peer Public IP: {self.peer_public_ip}")
        logging.info(f"Role: {'Initiator (Peer A)' if self.is_peer_a else 'Receiver (Peer B)'}")
    
    async def send_heartbeat(self, port):
        """Send a heartbeat packet to the peer's IP and specified port"""
        try:
            message = json.dumps({
                "type": "heartbeat",
                "sender_ip": self.my_public_ip,
                "timestamp": time.time()
            }).encode()
            self.sock.sendto(message, (self.peer_public_ip, port))
            return True
        except Exception as e:
            logging.error(f"Error sending heartbeat: {e}")
            return False
    
    async def listen_for_messages(self):
        """Listen for incoming messages"""
        try:
            while not self.stop_punching:
                try:
                    data, addr = self.sock.recvfrom(1024)
                    remote_ip, remote_port = addr
                    
                    try:
                        message = json.loads(data.decode())
                        if message["type"] == "heartbeat" and message["sender_ip"] == self.peer_public_ip:
                            logging.info(f"Received heartbeat from {remote_ip}:{remote_port}")
                            
                            # Send acknowledgment
                            ack = json.dumps({
                                "type": "ack",
                                "sender_ip": self.my_public_ip,
                                "timestamp": time.time()
                            }).encode()
                            self.sock.sendto(ack, addr)
                            self.remote_port = remote_port
                            self.connected.set()
                            
                        elif message["type"] == "ack" and message["sender_ip"] == self.peer_public_ip:
                            logging.info(f"Received acknowledgment from {remote_ip}:{remote_port}")
                            self.remote_port = remote_port
                            self.connected.set()
                            
                        elif message["type"] == "chat":
                            print(f"\nReceived: {message['content']}")
                            
                    except json.JSONDecodeError:
                        logging.warning(f"Received invalid JSON from {addr}")
                        
                except BlockingIOError:
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logging.error(f"Error receiving data: {e}")
                    await asyncio.sleep(0.1)
                    
        except Exception as e:
            logging.error(f"Error in listen_for_messages: {e}")
    
    async def initiate_connection(self):
        """Peer A: Send heartbeats on a fixed port and wait for response"""
        if not self.is_peer_a:
            return False
            
        logging.info("Starting connection as Peer A (Initiator)")
        listen_task = asyncio.create_task(self.listen_for_messages())
        
        # As Peer A, we'll send heartbeats on port 5000 (the known listening port)
        while not self.stop_punching and not self.connected.is_set():
            await self.send_heartbeat(LOCAL_PORT)
            await asyncio.sleep(1)
            
        return self.connected.is_set()
    
    async def brute_force_connect(self):
        """Peer B: Try to find the port Peer A is listening on"""
        if self.is_peer_a:
            return False
            
        logging.info("Starting connection as Peer B (Port Scanner)")
        listen_task = asyncio.create_task(self.listen_for_messages())
        
        current_port = MIN_PORT_RANGE
        while current_port <= MAX_PORT_RANGE and not self.stop_punching:
            batch_end = min(current_port + PORT_ATTEMPT_BATCH, MAX_PORT_RANGE + 1)
            logging.info(f"Trying ports {current_port}-{batch_end-1}")
            
            for port in range(current_port, batch_end):
                await self.send_heartbeat(port)
                
                if self.connected.is_set():
                    logging.info(f"Successfully connected to port {self.remote_port}")
                    return True
            
            await asyncio.sleep(0.5)
            current_port = batch_end
        
        self.stop_punching = True
        return False

    async def send_message(self, message):
        """Send a chat message"""
        if not self.remote_port:
            logging.error("No connection established")
            return False
            
        try:
            encoded_message = json.dumps({
                "type": "chat",
                "content": message,
                "sender_ip": self.my_public_ip
            }).encode()
            self.sock.sendto(encoded_message, (self.peer_public_ip, self.remote_port))
            logging.info(f"Sent message: {message}")
            return True
        except Exception as e:
            logging.error(f"Error sending message: {e}")
            return False

async def main():
    # Get the public IP of this machine
    my_public_ip = get_public_ip()
    if not my_public_ip:
        print("Could not determine your public IP. Please enter it manually:")
        my_public_ip = input().strip()
    
    print("\nYour public IP is:", my_public_ip)
    print("\nEnter the public IP of the peer you want to connect with:")
    peer_public_ip = input().strip()
    
    print("\nAre you Peer A (initiator) or Peer B (receiver)?")
    print("1. Peer A (initiator)")
    print("2. Peer B (receiver)")
    choice = input("Enter 1 or 2: ").strip()
    
    is_peer_a = choice == "1"
    
    chat = P2PChat(my_public_ip, peer_public_ip, is_peer_a)
    await chat.setup()
    
    try:
        if is_peer_a:
            success = await chat.initiate_connection()
        else:
            success = await chat.brute_force_connect()
            
        if not success:
            print("Failed to establish connection")
            return
            
        print("\nConnection established!")
        print("Chat session started. Type messages and press Enter to send (Ctrl+C to quit):")
        
        while True:
            message = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            message = message.strip()
            if message:
                await chat.send_message(message)
                
    except KeyboardInterrupt:
        print("\nClosing connection...")
    finally:
        chat.stop_punching = True
        if chat.sock:
            chat.sock.close()

if __name__ == "__main__":
    asyncio.run(main()) 