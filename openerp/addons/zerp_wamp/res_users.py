from osv import fields, osv
from tools import config
from izaber_wamp import WAMP
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

        # Look for a cached connection for this user and reuse it if possible
        # otherwise, configure the new connection for the authenticated user.
        connection_hash = (os.getpid(), uid)
        wamp = wamp_client_connections.get(connection_hash, WAMP())
        # An is_connecting state would be nice here so we can wait for a
        # successful connection tobe established
        if not wamp.wamp.is_connected():
            wamp_client_connections[connection_hash] = wamp
            uri_base = unicode(config.get("wamp_uri_base", "com.izaber.wamp"))
            url = unicode(config.get("wamp_url"))
            realm = unicode(config.get("wamp_realm"))
            if uid != 0:
                username = unicode(self.wamp_login(cr, uid))
                password = unicode(self.wamp_api_key(cr, uid))
            else:
                username = unicode(config.get("wamp_login"))
                password = unicode(config.get("wamp_password"))
            authmethods = [u"ticket"]
            wamp.configure(username=username,
                           password=password,
                           url=url,
                           uri_base=uri_base,
                           realm=realm,
                           authmethods=authmethods)
            wamp.run()
        return wamp

