# Gunicorn configuration for production deployment
import multiprocessing

# Server socket
bind = "0.0.0.0:8080"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2
max_requests = 1000
max_requests_jitter = 100

# Restart workers after this many requests to help prevent memory leaks
preload_app = True

# Restart workers when memory usage exceeds this limit
max_requests = 1000
max_requests_jitter = 50

# Application reload
reload = False
daemon = False
pidfile = None
user = None
group = None
tmp_upload_dir = None

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = 'telegram-job-bot'

# SSL (if using HTTPS)
# keyfile = '/path/to/keyfile'
# certfile = '/path/to/certfile'

# Environment variables
raw_env = [
    'FLASK_ENV=production',
]

# Worker temp directory
worker_tmp_dir = '/dev/shm'

# Send process title to statsD/Prometheus etc.
enable_stdio_inheritance = True

# SSL context
# ssl_version = 5
# ciphers = "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS"