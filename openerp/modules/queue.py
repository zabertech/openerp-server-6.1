import redis
import logging
import time
from pprint import pprint
import os
import sys
from Queue import Queue

_logger = logging.getLogger(__name__)
_redis_connection_pool = {}

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

    def __repr__(self):
        return "<RedisQueue object: name=%s socket=%s host=%s port=%s db=%s>" % (self.name, self.socket, self.host, self.port, self.db)

    def connect(self):
        """Connect to the redis server
        """

        # Connecting via unix socket
        if self.socket:
            self.redis_client = redis.Redis(unix_socket_path=self.socket)
            return True

        # Set up a TCP connection pool in a fork-safe way
        if self.host:
            global _redis_connection_pool
            if not _redis_connection_pool.get(os.getpid()):
                _redis_connection_pool[os.getpid()] = redis.ConnectionPool(host=self.host, port=self.port, db=self.db)
                self.redis_client = redis.Redis(connection_pool=_redis_connection_pool[os.getpid()])
            elif not self.redis_client:
                self.redis_client = redis.Redis(connection_pool=_redis_connection_pool[os.getpid()])
            return True

        return False

    def send(self, message):
        """Put a new message on the queue
        """
        self.connect()
        return self.redis_client.rpush(self.name, message)

    def receive(self):
        """Get the next message from the queue
        """
        self.connect()
        (name, message) = self.redis_client.blpop(self.name)
        return message


