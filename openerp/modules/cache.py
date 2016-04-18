import hashlib
import redis
import logging
import time
from pprint import pprint
import os
import signal

_domain_cache = {}
_model_blacklist = set([])
_cache_stats = {}
_logger = logging.getLogger(__name__)
_redis_connection_pool = {}

class RedisCacheException(Exception):
    """Exception fired for a cache miss
    """

class RedisCache(object):
    _stats_default = {'hit': 0, 'miss': 0, 'total_time': 0, 'total_get': 0, 'total_set': 0, 'error': 0}
    def __init__(self, cr, host="localhost", port=6379, unix=None, db=0, password=None, blacklist="", invalidation_tables={}, max_item_size=None):
        """Redis server details, plus a copy of the postgresql cursor for the dbname
        """
        global _redis_connection_pool
        global _model_blacklist
        self.unix = unix
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.dbname = cr.dbname
        self.redis_client = None
        if not _model_blacklist:
            _model_blacklist = blacklist
        self.invalidation_tables = invalidation_tables
        self.max_item_size = max_item_size

    def __repr__(self):
        return "<RedisCache object: host=%s port=%s db=%s password=%s dbname=%s>" % (self.host, self.port, self.db, self.password, self.dbname)

    def connect(self):
        """Connect to the redis server
        """
        global _redis_connection_pool

        # Connecting via unix socket
        if self.unix:
            self.redis_client = redis.Redis(unix_socket_path=self.unix)
            return True
        
        # Set up a TCP connection pool in a fork-safe way
        if self.host:
            if not _redis_connection_pool.get(os.getpid()):
                _redis_connection_pool[os.getpid()] = redis.ConnectionPool(host=self.host, port=self.port, db=self.db)
                self.redis_client = redis.Redis(connection_pool=_redis_connection_pool[os.getpid()])
            elif not self.redis_client:
                self.redis_client = redis.Redis(connection_pool=_redis_connection_pool[os.getpid()])
            return True

        return False

    def domaingen(self, model):
        """Postgresql database name and all tables which will cause invalidation of this data if written
        """
        global _domain_cache
        try:
            return _domain_cache[(self.dbname, model._table)]
        except KeyError:
            tables = set([model._table] + self.invalidation_tables.get(model._table, []))
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

    def cache_get(self, model, key, stats_key=None):
        """Try for a cache hit throwing a Cache Miss when failing
        """
        global _domain_cache
        self.timer_start()
        if self.model_is_blacklisted(model):
            raise RedisCacheException('Model is blacklisted %s', model._table)
        try:
            key = "|".join([_domain_cache.get((self.dbname, model._table), ""), key])
            self.connect()
            val = eval(self.redis_client.get(key))
        except Exception as err:
            self.stats_collect(stats_key, 'miss', 1)
            raise RedisCacheException("Cache Miss %s %s", key, err)
        finally:
            self.timer_stop(stats_key, 'total_get')
        self.stats_collect(stats_key, 'hit', 1)
        return val

    def cache_set(self, model, key, result, stats_key=None):
        """Attempt to cache data failing gracefully
        """
        self.timer_start()
        if self.model_is_blacklisted(model):
            return
        if self.max_item_size and len(str(result)) > self.max_item_size:
            return
        try:
            self.connect()
            domain = self.domaingen(model)
            key = "|".join((domain, key)) 
            self.redis_client.set(key, result)
        except Exception as err:
            _logger.error("cache_set error: %s", err)
            pass
        self.timer_stop(stats_key, 'total_set')

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
    def model_exists(cr, model):
        cr.execute("select * from information_schema.tables where table_name=%s" % model._table)
        return bool(cr.rowcount)

    @staticmethod
    def model_init(cr, model):
        """Create a trigger in the postgresql database for the given model's table to invalidate data when written
        """
        if not RedisCache.model_exists(cr, model):
            return
        cr.execute("DROP TRIGGER IF EXISTS trigger_cache_invalidate ON %s; CREATE TRIGGER trigger_cache_invalidate BEFORE INSERT OR UPDATE OR DELETE ON %s EXECUTE PROCEDURE cache_invalidate()" % (model._table, model._table));

    @staticmethod
    def model_clear(cr, model):
        """Remove invalidation trigger from the model
        """
        if not RedisCache.model_exists(cr, model):
            return
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
    def validate(model, cache_result, real_result):
        """Validate a cache result by comparing it to a real result
        """
        if cache_result != real_result:
            _logger.error("Validation failure for model %s\nCache Result: %s\nReal Result: %s\n", model._table, cache_result, real_result)
            return False
        return True


    def stats_collect(self, key, stat, num):
        global _stats_counter
        global _cache_stats
        if not key in _cache_stats:
            _cache_stats[key] = self._stats_default.copy()
        _cache_stats[key][stat] += num

    @staticmethod
    def stats_dump(*args):
        _stats_header = "{model:<28} {hit:>9} {miss:>9} {error:>9} {time:21}   {get:21}   {set:21}   {profit:10}\n".format(
                model="Model",
                hit="Hits",
                miss="Misses",
                error="Errors",
                time="Time Saved",
                get="Time Wasted Get",
                set="Time Wasted Set",
                profit="Profit"
            )
        _stats_template = "{model:<28} {hit:>9} {miss:>9} {error:9} {time:>10.3f} {total_time:>10.3f}   {get:>10.3f} {total_get:>10.3f}   {set:>10.3f} {total_set:>10.3f}   {profit:>10.3f}\n" 
        _stats_filename_template = "/tmp/redis-cache-stats-{time}"

        def div(a, b):
            try:
                return a / b
            except ZeroDivisionError:
                return 0
        out = _stats_header
        keys = sorted(_cache_stats.keys())
        profit = 0
        for key in keys:
            _profit = _cache_stats[key]["total_time"] - _cache_stats[key]["total_get"] - _cache_stats[key]["total_set"] + 0.001
            profit += _profit
            out += _stats_template.format(
                model=key,
                hit=_cache_stats[key]["hit"],
                miss=_cache_stats[key]["miss"],
                error=_cache_stats[key]["error"],
                time=div(_cache_stats[key]["total_time"], _cache_stats[key]["hit"]),
                total_time=_cache_stats[key]["total_time"],
                set=div(_cache_stats[key]["total_set"], _cache_stats[key]["miss"]),
                total_set=_cache_stats[key]["total_set"],
                get=div(_cache_stats[key]["total_get"], _cache_stats[key]["hit"]),
                total_get=_cache_stats[key]["total_get"],
                profit=_profit
            )
        out += "{profit:>141.3f}\n".format(profit=profit)
        with open(_stats_filename_template.format(time=time.time()), 'w') as f:
            f.write(out)
        print out
        RedisCache.stats_reset()

    @staticmethod
    def stats_reset():
        global _cache_stats
        _cache_stats = {}

    def timer_start(self):
        """
        """
        self.timer = time.time()

    def timer_stop(self, key, stat):
        """
        """
        global _cache_stats
        _time = time.time() - self.timer
        if not key in _cache_stats:
            _cache_stats[key] = _stats_default.copy()
        _cache_stats[key][stat] += _time

try:
    signal.signal(signal.SIGUSR1, RedisCache.stats_dump)
except ValueError:
    pass


