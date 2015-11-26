import ejson
from datetime import datetime
from time import sleep
from openerp.osv import osv, orm, fields
from openerp import pooler
from ddp import *
from tools import config
from globals import *

class zerp_ddp_connection(osv.osv):
    _name = 'zerp.ddp.connection'
    _columns = {
        'user_id': fields.many2one('res.users', 'user', select=True, readonly=True),
        'ddp_session_id': fields.char('Session ID', size=128, select=True, readonly=True),
        'database': fields.char('Database', size=128, select=True, readonly=True),
        'remote_ip': fields.char('IP Address', size=128, select=True, readonly=True)
    }

class zerp_ddp_session(osv.osv):
    _name = 'zerp.ddp.session'
    _columns = { 
        'ddp_session_id': fields.char("Session ID", size=128, select=True, readonly=True),
        'expiry': fields.datetime("Expiry", select=True, readonly=True)
    }

class zerp_ddp_subscription(osv.osv):
    _name = 'zerp.ddp.subscription'
    _columns = {
        'user_id': fields.many2one('res.users', 'user', select=True, readonly=True),
        'ddp_session_id': fields.char('Session ID', size=128, select=True, readonly=True),
        'database': fields.char('Database', size=128, select=True, readonly=True),
        'remote_ip': fields.char('IP Address', size=128, select=True, readonly=True),
        'name': fields.char('Name', size=128, select=True, readonly=True),
        'params': fields.char('Params', size=256, select=True, readonly=True),
        'method': fields.char('Method', size=256, select=True, readonly=True)
    }

class ZerpDDPMonitor(object):
    dbname = None
    def __init__(self):
        """ 
        """
        self.dbname = config.get('ddp_monitor_db', None)
        if not self.dbname:
            raise osv.except_osv('Error', 'Set ddp_monitor_db configuration option to enable DDP monitoring.')

    def update_sessions(self):
        global ddp_sessions
        connection, pool = pooler.get_db_and_pool(self.dbname)
        cr = connection.cursor()
        session_obj = pool.get('zerp.ddp.session')
        cr.execute("DELETE FROM zerp_ddp_session")
        for session_id, session in ddp_sessions.items():
            session_obj.create(cr, 1, {'ddp_session_id': session_id, 'expiry': datetime.fromtimestamp(session.expiry)})
        cr.commit()
        cr.close()

    def update_connections(self):
        global ddp_connections
        connection, pool = pooler.get_db_and_pool('today')
        cr = connection.cursor()
        connection_obj = pool.get('zerp.ddp.connection')
        cr.execute("DELETE FROM zerp_ddp_connection")
        for conn in ddp_connections:
            connection_obj.create(cr, 1, {
                'ddp_session_id': conn.ddp_session and conn.ddp_session.ddp_session_id or None,
                'remote_ip': conn.remote_ip,
                'database': conn.database,
                'user_id': conn.uid
            });
        cr.commit()
        cr.close()

    def update_subscriptions(self):
        global ddp_subscriptions
        connection, pool = pooler.get_db_and_pool('today')
        cr = connection.cursor()
        subscription_obj = pool.get('zerp.ddp.subscription')
        cr.execute("DELETE FROM zerp_ddp_subscription")
        for sub in ddp_subscriptions:
            subscription_obj.create(cr, 1, {
               'ddp_session_id': sub.conn.ddp_session and sub.conn.ddp_session.ddp_session_id or None,
               'remote_ip': sub.conn.remote_ip,
               'database': sub.conn.database,
               'user_id': sub.conn.uid,
               'name': sub.name,
               'params': ejson.dumps(sub.params),
               'method': sub.method
            });
        cr.commit()
        cr.close()

    def start(self):
        global ddp_connections
        while True:
            sleep(10)
            self.update_subscriptions()
            self.update_connections()
            self.update_sessions()
