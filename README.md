# P2P Chat Application

A simple peer-to-peer chat application that uses UDP hole punching for direct communication between peers.

## Features

- Direct P2P communication using UDP
- NAT traversal using STUN and UDP hole punching
- Simple rendezvous server for peer discovery
- Keep-alive mechanism to maintain NAT bindings

## Prerequisites

- Python 3.11 or later
- Conda package manager

## Installation

1. Create and activate a new conda environment:

```bash
conda create -n p2p_chat python=3.11
conda activate p2p_chat
```

2. Install the required packages:

```bash
pip install flask requests pystun3
```

## Usage

### Starting the Rendezvous Server

1. Run the server:

```bash
python server.py
```

The server will start on port 5000 and listen on all interfaces.

### Starting a Chat Client

1. Run the client:

```bash
python client.py
```

2. When prompted:

   - Enter your username
   - Enter the username of the peer you want to chat with

3. The client will:
   - Discover its public endpoint using STUN
   - Register with the rendezvous server
   - Attempt to establish a direct connection with the peer
   - Start the chat session if successful

## Important Notes

- Both peers must be running the client application to establish a connection
- The rendezvous server must be accessible by both peers
- NAT traversal may not work with all types of NATs (especially Symmetric NAT)
- For testing locally, you can run both clients on the same machine, but in a real scenario, they should be on different networks

## Limitations

- No encryption or authentication
- Basic error handling
- May not work with all NAT configurations
- In-memory peer registry (resets when server restarts)

## Future Improvements

- Add end-to-end encryption
- Implement authentication
- Add support for group chats
- Add fallback to TURN servers when direct connection fails
- Add persistent storage for peer registry
- Implement better error handling and recovery

## Project Structure

```
.
├── config/
│   └── chat_config.json
├── src/
│   ├── p2p/
│   │   ├── __init__.py
│   │   ├── p2p_chat.py
│   │   ├── client.py
│   │   └── server.py
│   ├── chatroom/
│   │   ├── __init__.py
│   │   └── chatroom.py
│   └── utils/
│       ├── __init__.py
│       └── genarate_shared_key.py
├── tests/
│   ├── __init__.py
│   └── ptp_test.py
├── requirements.txt
├── LICENSE
└── README.md
```
