from flask import Flask, request, jsonify
import json
import os
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory registry mapping usernames to their public endpoint
# Add timestamp to handle stale entries
registry = {}

def cleanup_stale_entries():
    """Remove entries older than 5 minutes"""
    now = datetime.now()
    stale_users = [
        username for username, data in registry.items()
        if (now - data['timestamp']).total_seconds() > 300
    ]
    for username in stale_users:
        del registry[username]
        logger.info(f"Removed stale entry for user: {username}")

@app.route('/')
def home():
    cleanup_stale_entries()
    return jsonify({
        'status': 'running',
        'active_peers': len(registry),
        'server_time': datetime.now().isoformat()
    })

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON data received'}), 400

        username = data.get('username')
        ip = data.get('ip')
        port = data.get('port')

        if not all([username, ip, port]):
            return jsonify({'status': 'error', 'message': 'Missing required parameters'}), 400

        try:
            port = int(port)
        except (TypeError, ValueError):
            return jsonify({'status': 'error', 'message': 'Port must be a number'}), 400

        # Store endpoint with timestamp
        registry[username] = {
            'endpoint': (ip, port),
            'timestamp': datetime.now()
        }
        logger.info(f"Registered user {username} at {ip}:{port}")
        
        # Cleanup old entries
        cleanup_stale_entries()
        
        return jsonify({
            'status': 'success',
            'message': 'Successfully registered',
            'active_peers': len(registry)
        })

    except Exception as e:
        logger.error(f"Error in register endpoint: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500

@app.route('/get_peer/<username>', methods=['GET'])
def get_peer(username):
    try:
        cleanup_stale_entries()
        
        if username not in registry:
            return jsonify({'status': 'error', 'message': 'Peer not found'}), 404

        ip, port = registry[username]['endpoint']
        # Update timestamp
        registry[username]['timestamp'] = datetime.now()
        
        logger.info(f"Retrieved peer info for {username}: {ip}:{port}")
        return jsonify({'ip': ip, 'port': port})

    except Exception as e:
        logger.error(f"Error in get_peer endpoint: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500

@app.route('/list_peers', methods=['GET'])
def list_peers():
    try:
        cleanup_stale_entries()
        peers = list(registry.keys())
        return jsonify({
            'peers': peers,
            'count': len(peers),
            'server_time': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error in list_peers endpoint: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500

if __name__ == '__main__':
    # Get port from environment variable (for cloud deployment) or use default
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port) 