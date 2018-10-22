from osv import fields, osv
from tools import config
from swampyer import WAMPClientTicket
import os

wamp_client_connections = {}

class res_users(osv.osv):
    _inherit = "res.users"
    _columns = {
        "wamp_api_key": fields.char("WAMP API Key", size=128)
    }

    def wamp_api_key(self, cr, uid, context=None):
        return self.read(cr, uid, uid, ["wamp_api_key"])["wamp_api_key"]

    def wamp_login(self, cr, uid, context=None):
        return self.read(cr, uid, uid, ["login"])["login"]

    def wamp_connect(self, cr, uid, context=None):
        global wamp_client_connections
        url = unicode(config.get("wamp_url"))
        realm = unicode(config.get("wamp_realm"))
        if not (url and realm):
            raise Exception("Error", "Error creating wamp client connection: No wamp_url or wamp_realm configured.")
        wamp = wamp_client_connections.setdefault((os.getpid(), uid), WAMPClientTicket())
        if not wamp.is_connected():
            if uid != 0:
                username = unicode(self.wamp_login(cr, uid))
                password = unicode(self.wamp_api_key(cr, uid))
            else:
                username = unicode(config.get("wamp_login"))
                password = unicode(config.get("wamp_password"))
            wamp.configure(username=username,
                           password=password,
                           url=url,
                           uri_base=unicode(config.get("wamp_uri_base", "com.izaber.wamp")),
                           realm=unicode(config.get("wamp_realm", "izaber")),
                           timeout=config.get("wamp_timout", 10))
            wamp.start()
        return wamp

