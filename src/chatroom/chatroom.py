import socket
import threading
import sys
import os
import json
from datetime import datetime

# Configuration
BROADCAST_IP = '255.255.255.255'  # Broadcast address
PORT = 12345  # Port for communication
BUFFER_SIZE = 1024
CONFIG_FILE = 'chat_config.json'

class ChatRoom:
    def __init__(self):
        # Create UDP socket for broadcasting
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.iSOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Flag for clean shutdown
        self.running = True
        
        # Bind to receive messages
        self.sock.bind(('', PORT))
        
        # Get or set device name
        self.device_name = self.get_or_set_name()
        
        print(f"\nWelcome to the chat room! Your name is: {self.device_name}")
        print("Type your messages and press Enter to send. Press Ctrl+C to exit.")
    
    def get_or_set_name(self):
        # Try to load saved name
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    saved_name = config.get('name')
                    if saved_name:
                        confirm = input(f"Found saved name: {saved_name}. Use this name? (y/n): ").lower()
                        if confirm == 'y':
                            return saved_name
            except Exception as e:
                print(f"Error reading saved name: {e}")
        
        # Get new name from user
        while True:
            name = input("Enter your name for the chat: ").strip()
            if name:
                # Save the name
                try:
                    with open(CONFIG_FILE, 'w') as f:
                        json.dump({'name': name}, f)
                except Exception as e:
                    print(f"Warning: Couldn't save name: {e}")
                return name
            print("Name cannot be empty. Please try again.")
        
    def receive_messages(self):
        while self.running:
            try:
                self.sock.settimeout(0.5)  # Add timeout to check running flag
                data, addr = self.sock.recvfrom(BUFFER_SIZE)
                if addr[0] != socket.gethostbyname(socket.gethostname()):  # Don't show our own messages
                    print(f"\n{data.decode()}")
            except socket.timeout:
                continue  # Just check running flag again
            except Exception as e:
                if self.running:  # Only show error if not shutting down
                    print(f"Error receiving message: {e}")
                break
    
    def send_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {self.device_name}: {message}"
        try:
            self.sock.sendto(formatted_message.encode(), (BROADCAST_IP, PORT))
        except Exception as e:
            print(f"Error sending message: {e}")
    
    def shutdown(self):
        """Clean shutdown of the chat room"""
        self.running = False
        print("\nLeaving the chat room...")
        self.sock.close()
    
    def run(self):
        # Start receive thread
        receive_thread = threading.Thread(target=self.receive_messages)
        receive_thread.daemon = True
        receive_thread.start()
        
        # Main loop for sending messages
        try:
            while True:
                message = input()
                if message.strip():  # Only send non-empty messages
                    self.send_message(message)
        except KeyboardInterrupt:
            self.shutdown()
            sys.exit()

if __name__ == "__main__":
    chat = ChatRoom()
    chat.run()
