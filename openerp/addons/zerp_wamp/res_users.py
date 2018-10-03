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
        uri_base = unicode(config.get("wamp_uri_base", "com.izaber.wamp"))
        url = unicode(config.get("wamp_url"))
        realm = unicode(config.get("wamp_realm"))
        timeout = config.get("wamp_timout", 10)
        if uid != 0:
            username = unicode(self.wamp_login(cr, uid))
            password = unicode(self.wamp_api_key(cr, uid))
        else:
            username = unicode(config.get("wamp_login"))
            password = unicode(config.get("wamp_password"))
        wamp.configure(username=username,
                       password=password,
                       url=url,
                       uri_base=uri_base,
                       realm=realm,
                       timeout=timeout)
        wamp.start()
        return wamp

