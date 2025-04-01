import os

# Bind to 0.0.0.0 to listen on all interfaces
port = int(os.environ.get("PORT", 10000))
bind = f"0.0.0.0:{port}"

# Worker configuration
workers = 2
threads = 4
worker_class = "gthread"
timeout = 120

# Access logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "info" 