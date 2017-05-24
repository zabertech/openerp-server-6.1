import redis
import md5
import logging
import time
from pprint import pprint
import os
import sys
from Queue import Queue

_logger = logging.getLogger(__name__)
_redis_connection_pool = {}
_redis_queue_backlog = {}

class RedisQueueException(Exception):
    """Exception fired for a queue problem
    """

class RedisQueue(object):
    def __init__(self, name, host=None, port=None, socket=None, db=0, password=None):
        """Redis server and queue details
        """
        global _redis_connection_pool
        self.socket = socket
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.redis_client = None
        self.name = name
        self.name_processing = "{}_processing".format(name)
        _redis_queue_backlog.setdefault(self.name, [])

    def __repr__(self):
        return "<RedisQueue object: name=%s socket=%s host=%s port=%s db=%s>" % (self.name, self.socket, self.host, self.port, self.db)

    def connect(self):
        """Connect to the redis server
        """

        # Connecting via unix socket
        if self.socket:
            self.redis_client = redis.Redis(unix_socket_path=self.socket)
            self.redis_client.ping()
            return True

        # Set up a TCP connection pool in a fork-safe way
        if self.host:
            global _redis_connection_pool
            if not _redis_connection_pool.get(os.getpid()):
                _redis_connection_pool[os.getpid()] = redis.ConnectionPool(host=self.host, port=self.port, db=self.db)
                self.redis_client = redis.Redis(connection_pool=_redis_connection_pool[os.getpid()])
            elif not self.redis_client:
                self.redis_client = redis.Redis(connection_pool=_redis_connection_pool[os.getpid()])
            self.redis_client.ping()
            return True

        return False

    def add_to_backlog(self, message):
        """Add a message to the local queue backlog
        """
        global _redis_queue_backlog
        _redis_queue_backlog[self.name].append(message)

    def send_backlog(self):
        """Send whatever's on the local queue backlog to the redis queue
        """
        global _redis_queue_backlog
        while len(_redis_queue_backlog[self.name]) > 0:
            # get the next locally enqueued message
            message = _redis_queue_backlog[self.name][0]
            # push it onto the redis queue
            num = self.redis_client.lpush(self.name, message)
            # pop the message from the end of the local queue now that we're sure
            # it's been safely pushed to redis
            _redis_queue_backlog[self.name].pop(0)

    def send(self, message):
        """Put a new message on the queue, via the local backlog
        so it isn't lost if we cannot contact redis.
        """
        self.add_to_backlog(message)
        self.connect()
        self.send_backlog()
        return True

    def receive(self):
        """Get the next message from the queue
        """
        self.connect()
        self.wait_processing()
        # If  there's nothing there, wait for a new message on the main queue. When one
        # arrives, pop it for processing and push it onto the processing list. if all
        # goes well, it'll be removed from the processing list by calling 'acknowledge()'
        message = self.redis_client.brpoplpush(self.name, self.name_processing)
        return message

    def wait_processing(self):
        """Check the processing queue to see if there are still
        jobs to complete
        """
        self.connect()
        count = 0
        while self.redis_client.llen(self.name_processing):
            count += 1
            if count > 100: return False
        return True

    def flush(self):
        """Flush stale messages from the processing queue
        """
        self.connect()
        return self.redis_client.delete(self.name_processing)

    def acknowledge(self, message):
        """Remove the leftmost message from the processing queue once done procesing.
        """
        self.connect()
        ack = self.redis_client.lrem(self.name_processing, message)

