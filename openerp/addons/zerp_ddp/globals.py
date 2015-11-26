import Queue

server = None
server_thread = None
worker = None
worker_thread = None
reaper = None
reaper_thread = None
monitor = None
monitor_thread = None

ddp_temp_message_queues = {}
login_tokens = {}

