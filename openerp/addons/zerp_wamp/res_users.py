from osv import fields, osv
from tools import config
from izaber_wamp import WAMP

class res_users(osv.osv):
    _inherit = 'res.users'
    _columns = {
        "wamp_api_key": fields.char("WAMP API Key", size=128)
    }

    def wamp_api_key(self, cr, uid, context=None):
        return self.read(cr, uid, uid, ["wamp_api_key"])["wamp_api_key"]

    def wamp_login(self, cr, uid, context=None):
        return self.read(cr, uid, uid, ["login"])["login"]

    def wamp_conn(self, cr, uid, context=None):
        username=self.wamp_login(cr, uid)
        apikey=self.wamp_api_key(cr, uid)
        uri_base = unicode(config.get("wamp_uri_base", "com.izaber.wamp"))
        url = unicode(config.get("wamp_url"))
        realm = unicode(config.get("wamp_realm"))
        authmethods = [u"ticket"]
        print username, apikey, uri_base, url, realm, authmethods
        wamp = WAMP()
        wamp.configure(username=username,
                       password=apikey,
                       url=url,
                       uri_base=uri_base,
                       realm=realm,
                       authmethods=authmethods)
        wamp.run()
        return wamp

