import hashlib
import redis

class RedisCacheException(Exception):
    """
    """

class RedisCache(object):
    def __init__(self, cr, host="localhost", port=6379, db=0, username=None, password=None, domain_blacklist=None):
        """
        """
        self.domain_blacklist=domain_blacklist
        self.host = host
        self.port = port
        self.db = db
        self.username = username
        self.password = password
        self.dbname = cr.dbname

    def connect(self):
        self.redis_client = redis.StrictRedis(host=self.host, port=self.port, db=self.db)

    def keygen(self, domain_args, key_args):
        domain = "|".join(domain_args)
        key = hashlib.md5(str(key_args)).hexdigest()
        return "|".join((domain, key)) 

    def cache_get(self, key):
        try:
            return eval(self.redis_client.get(key))
        except:
            raise RedisCacheException("Redis Cache Miss")

    def cache_set(self, key, result):
        try: 
            self.redis_client.set(key, result)
        except:
            pass 

    def domain_is_blacklisted(self, domain):
        return self.domain_blacklist and (domain in self.domain_blacklist)

    def init_postgresql(self, cr):
        cr.execute("""CREATE OR REPLACE FUNCTION redis_cache_invalidate()
  returns trigger
  language plpython3u
as $$
  import redis
  client = redis.StrictRedis(host="%s", port=%s, db=%s)
  pattern = "%s|" + TD["table_name"] + "|*"
  keys = client.keys(pattern=pattern)
  if keys:
    client.delete(*keys)
  return None
$$;""", self.dbname, self.host, self.port, self.db)


    def init_model(self, cr, table_name):
        cr.execute("DROP TRIGGER IF EXISTS trigger_cache_invalidate ON %s; CREATE TRIGGER trigger_cache_invalidate BEFORE INSERT OR UPDATE OR DELETE ON %s EXECUTE PROCEDURE kirby_invalidate()", table_name);


