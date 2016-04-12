import hashlib
import redis
import logging
from pprint import pprint

_domain_cache = {}
_model_blacklist = set([])
_cache_stats = {}
_stats_counter = 0
_logger = logging.getLogger(__name__)

class RedisCacheException(Exception):
    """Exception fired for a cache miss
    """

class RedisCache(object):
    def __init__(self, cr, host="localhost", port=6379, db=0, password=None):
        """Redis server details, plus a copy of the postgresql cursor for the dbname
        """
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.dbname = cr.dbname
        self.redis_client = None

    def __repr__(self):
        return "<RedisCache object: host=%s port=%s db=%s password=%s dbname=%s>" % (self.host, self.port, self.db, self.password, self.dbname)

    def connect(self):
        """Connect to the redis server
        """
        if not self.redis_client:
            self.redis_client = redis.StrictRedis(host=self.host, port=self.port, db=self.db)

    def domaingen(self, model):
        """Postgresql database name and all tables which will cause invalidation of this data if written
        """
        global _domain_cache
        try:
            return _domain_cache[(self.dbname, model._table)]
        except KeyError:
            tables = set([model._table])
            for name, col in model._columns.items():
                if col._classic_write:
                    continue
                if hasattr(col, '_obj'):
                    try:
                        tables.add(model.pool.get(col._obj)._table)
                    except:
                        pass
                if hasattr(col, '_rel'):
                    tables.add(col._rel)
            
            domain = "{}|{}".format(self.dbname, "|".join(sorted(tables)))
            _domain_cache[(self.dbname, model._table)] = domain
            return domain

    @staticmethod
    def keygen(key_args):
        """Create an md5 hash digest of the arguments passed to the cached method
        """
        key = hashlib.md5(str(key_args)).hexdigest()
        return key

    def cache_get(self, key, stats_key=None):
        """Try for a cache hit throwing a Cache Miss when failing
        """
        try:
            self.connect()
            key = self.redis_client.keys("*|"+key)[0]
            val = eval(self.redis_client.get(key))
        except Exception as err:
            self.stats_collect(stats_key, 'miss', 1)
            raise RedisCacheException("Cache Miss %s %s", key, err)
        self.stats_collect(stats_key, 'hit', 1)
        return val

    def cache_set(self, model, key, result, stats_key=None):
        """Attempt to cache data failing gracefully
        """
        #try:
        self.connect()
        domain = self.domaingen(model)
        key = "|".join((domain, key)) 
        self.redis_client.set(key, result)
        self.stats_collect(stats_key, 'set', 1)
        #except Exception as err:
        #    _logger.error("cache_set error: %s", err)
        #    pass

    def postgresql_init(self, cr):
        """Create a function in the postgresql database which will be triggered to invalidate data in the cache
        """
        cr.execute("""CREATE OR REPLACE FUNCTION cache_invalidate()
    returns trigger
    language plpython3u
as $$
    try:
        import redis
        client = redis.StrictRedis(host="%s", port=%s, db=%s)
        pattern = "%s*|" + TD["table_name"] + "|*"
        keys = client.keys(pattern=pattern)
        if keys:
            client.delete(*keys)
    except:
        pass
    return None
$$;""" % (self.host, self.port, self.db, self.dbname))

    @staticmethod
    def model_init(cr, model):
        """Create a trigger in the postgresql database for the given model's table to invalidate data when written
        """
        cr.execute("DROP TRIGGER IF EXISTS trigger_cache_invalidate ON %s; CREATE TRIGGER trigger_cache_invalidate BEFORE INSERT OR UPDATE OR DELETE ON %s EXECUTE PROCEDURE cache_invalidate()" % (model._table, model._table));

    @staticmethod
    def model_clear(cr, model):
        """Remove invalidation trigger from the model
        """
        cr.execute("DROP TRIGGER IF EXISTS trigger_cache_invalidate ON %s" % model._table);

    @staticmethod
    def model_complex_fields(cr, model):
        """Return the fields of the model which should not be considered safe to cache
        """
        fields = set([])
        for name, col in model._columns.items():
            if col._classic_write:
                continue
            if not hasattr(col, '_fnct'):
                continue
            fields.add(name)
        return fields

    @staticmethod
    def model_blacklist(model):
        """Add a model to the global model blacklist
        """
        global _model_blacklist
        _model_blacklist.add(model._table)  

    @staticmethod
    def model_is_blacklisted(model):
        """Test if the model is currently blacklisted
        """
        global _model_blacklist
        return model._table in _model_blacklist

    def panic(self):
        """Something's gone wrong, so flush the cache
        """
        self.connect()
        self.redis_client.flushall()

    @staticmethod
    def validate(cache_result, real_result):
        """Validate a cache result by comparing it to a real result
        """
        if cache_result != real_result:
            _logger.error("Validation failure\nCache Result: %s\nReal Result: %s\n", cache_result, real_result)
            return false
        return True

    @staticmethod
    def stats_collect(key, stat, num):
        global _stats_counter
        global _cache_stats
        if not key or not stat in ('hit', 'miss', 'set'):
            return
        if not key in _cache_stats:
            _cache_stats[key] = {'hit': 0, 'miss': 0, 'set': 0}
        _cache_stats[key][stat] += num
        _stats_counter = _stats_counter % 100 + 1
        if _stats_counter == 100:
            pprint(_cache_stats)
        
