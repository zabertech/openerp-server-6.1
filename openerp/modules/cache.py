import hashlib
import redis

_domain_cache = {}
_model_blacklist = set([])

class RedisCacheException(Exception):
    """
    """

class RedisCache(object):
    def __init__(self, cr, host="localhost", port=6379, db=0, password=None):
        """
        """
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.dbname = cr.dbname

    def __repr__(self):
        return "<RedisCache object: host=%s port=%s db=%s password=%s dbname=%s>" % (self.host, self.port, self.db, self.password, self.dbname)

    def connect(self):
        self.redis_client = redis.StrictRedis(host=self.host, port=self.port, db=self.db)

    def domaingen(self, model):
        try:
            return _domain_cache[(self.dbname, model._table)]
        except KeyError:
            tables = set([model._table])
            for name, col in model._columns.items():
                if col._classic_write:
                    continue
                if hasattr(col, '_fnct'):
                    continue
                if col._type in ["one2many", "many2one", "many2many"]:
                    tables.add(model.pool.get(col._obj)._table)
                if col._type == "many2many":
                    tables.add(col._rel)
            
            domain = "{}|{}".format(self.dbname, "|".join(sorted(tables)))
            _domain_cache[(self.dbname, model._table)] = domain
            return domain

    @staticmethod
    def keygen(key_args):
        key = hashlib.md5(str(key_args)).hexdigest()
        return key

    def cache_get(self, key):
        try:
            key = self.redis_client.keys("*|"+key)[0]
            val = eval(self.redis_client.get(key))
        except Exception as err:
            raise RedisCacheException("Cache Miss %s %s", key, err)
        return val

    def cache_set(self, model, key, result):
        domain = self.domaingen(model)
        self.redis_client.set("|".join((domain, key)), result)

    def postgresql_init(self, cr):
        cr.execute("""CREATE OR REPLACE FUNCTION cache_invalidate()
  returns trigger
  language plpython3u
as $$
  import redis
  client = redis.StrictRedis(host="%s", port=%s, db=%s)
  pattern = "%s*|" + TD["table_name"] + "|*"
  keys = client.keys(pattern=pattern)
  if keys:
    client.delete(*keys)
  return None
$$;""" % (self.host, self.port, self.db, self.dbname))

    @staticmethod
    def model_init(cr, model):
        cr.execute("DROP TRIGGER IF EXISTS trigger_cache_invalidate ON %s; CREATE TRIGGER trigger_cache_invalidate BEFORE INSERT OR UPDATE OR DELETE ON %s EXECUTE PROCEDURE cache_invalidate()" % (model._table, model._table));

    @staticmethod
    def model_clear(cr, model):
        cr.execute("DROP TRIGGER IF EXISTS trigger_cache_invalidate ON %s" % model._table);

    @staticmethod
    def model_complex_fields(cr, model):
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
        """
        """
        #_model_blacklist.add(model._table)

    @staticmethod
    def model_is_blacklisted(model):
        return model._table in _model_blacklist


