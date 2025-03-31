import socket
import threading
import time
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import genarate_shared_key as key

# Manually define public IPs and ports of both peers
PEER_A_PUBLIC_IP = "100.110.0.2"  # For local testing
PEER_B_PUBLIC_IP = "5.29.22.99"  # For local testing
PORT = 5000

# Packet spam rate (packets per second)
PACKET_SPAM_RATE = 5

# Generate a shared AES key (must be the same on both peers)
SHARED_KEY = key.SHARED_KEY

def detect_nat_type():
    """Simple function to return local IP for testing."""
    try:    
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        print(f"[LOCAL IP] {local_ip}")
        return "Unknown"
    except Exception as e:
        print(f"[ERROR] IP detection failed: {e}")
        return "Unknown"


def encrypt_message(message):
    """Encrypts a message using AES-GCM."""
    aesgcm = AESGCM(SHARED_KEY)
    nonce = os.urandom(12)  # 96-bit nonce
    encrypted_data = aesgcm.encrypt(nonce, message.encode(), None)
    return nonce + encrypted_data  # Send nonce with encrypted data


def decrypt_message(encrypted_message):
    """Decrypts a message using AES-GCM."""
    aesgcm = AESGCM(SHARED_KEY)
    nonce = encrypted_message[:12]  # Extract nonce
    ciphertext = encrypted_message[12:]
    try:
        return aesgcm.decrypt(nonce, ciphertext, None).decode()
    except Exception as e:
        print(f"[ERROR] Decryption failed: {e}")
        return "[Decryption Error]"


def udp_listener(sock):
    """ Listens for incoming UDP messages using the shared socket."""
    print(f"[LISTENING] on port {PORT}...")
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            message = decrypt_message(data)
            print(f"\n[PEER]: {message}")
        except Exception as e:
            print(f"[ERROR] Receiving message: {e}")


def udp_spammer(sock, target_ip):
    """ Continuously sends UDP packets (hole punching) using the shared socket."""
    message = encrypt_message("HOLE PUNCHING ATTEMPT")
    while True:
        try:
            sock.sendto(message, (target_ip, PORT))
            time.sleep(1 / PACKET_SPAM_RATE)
        except Exception as e:
            print(f"[ERROR] Sending UDP packet: {e}")
            break


def chat_sender(sock, target_ip):
    """ Sends chat messages to the peer using the shared socket."""
    while True:
        message = input("You: ")
        if message.lower() == "exit":
            print("Exiting chat...")
            break
        try:
            encrypted_message = encrypt_message(message)
            sock.sendto(encrypted_message, (target_ip, PORT))
        except Exception as e:
            print(f"[ERROR] Sending chat message: {e}")


if __name__ == "__main__":
    role = input("Run as (peera/peerb)? ").strip().lower()
    
    if role == "peera":
        target_ip = PEER_B_PUBLIC_IP
    elif role == "peerb":
        target_ip = PEER_A_PUBLIC_IP
    else:
        print("Invalid role. Use 'peerA' or 'peerB'.")
        exit(1)
    
    nat_type = detect_nat_type()
    
    # Create a single UDP socket bound to the fixed port
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", PORT))
    
    threading.Thread(target=udp_listener, args=(sock,), daemon=True).start()
    threading.Thread(target=udp_spammer, args=(sock, target_ip), daemon=True).start()
    chat_sender(sock, target_ip)
