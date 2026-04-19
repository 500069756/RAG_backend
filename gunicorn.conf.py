# Gunicorn configuration for Render deployment

import os

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = 2
worker_class = "sync"
timeout = 120

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Server mechanics
preload_app = True
