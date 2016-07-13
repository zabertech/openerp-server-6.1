import os
import re

from tools import config
import logging
import netsvc

from twisted.logger import Logger
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.protocol import ReconnectingClientFactory

from autobahn.twisted import websocket
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner, ApplicationSessionFactory
from autobahn.wamp.exception import ApplicationError, InvalidUri

try:
    from autobahn.websocket.util import parse_url
except ImportError:
    from autobahn.websocket.protocol import parseWsUrl
    parse_url = parseWsUrl

from autobahn.wamp.types import SubscribeOptions, RegisterOptions, ComponentConfig

from pprint import pprint

import openerp
from openerp import pooler
import openerp.service

"""

To be able to use this library, one will probably have to:

sudo apt-get install python-dev
sudo pip install crossbar

Configuration Options to place into openerp.conf:

wamp_uri = wss://nexus.izaber.com/ws
wamp_login = someuser
wamp_password = somepass
wamp_realm = izaber
wamp_registration_prefix = com.izaber.nexus.zerp.

"""

_logger = logging.getLogger(__name__)

CLIENT_CACHE = {}

class ZERPSession(ApplicationSession):

    log = Logger()

    handled_methods = {
                    'execute':       ['object','execute',None],
                    'exec_workflow': ['object','exec_workflow',None],
                    'wizard_create': ['wizard','create',None],
                    'report':        ['report','report',None],
                    'report_get':    ['report','report_get',None],

                    'search':        ['object','execute','search'],
                    'fetch':         ['object','execute','read'],
                    'write':         ['object','execute','write'],
                    'create':        ['object','execute','create'],
                    'unlink':        ['object','execute','unlink'],
                }

    def zerp_get(self,details):
        """ Returns a user session from database or creates a new one
        """
        global CLIENT_CACHE

        # authid is the login of the authenticated user
        login = details.caller_authid
        if not login: return

        # Parse out what database the user is trying to attach to
        m = re.search('com.izaber.nexus.zerp.(.+)\.([\w_]+)',details.procedure)


        # Ensure that the database they're trying to access actually exists
        database = m.group(1)
        databases = openerp.service.web_services.db().exp_list()
        if database not in databases:
            raise ApplicationError("com.izaber.zerp.error.invalid_login",
                    "could not authenticate session")

        # Try and find the record based upon the session
        session = details.caller
        if not session: return

        # If we've got a cached session, let's use that
        user_zerp = CLIENT_CACHE.get(session,{}).get(database)
        if user_zerp: return user_zerp

        # Verify that the user actually exists in the database
        db, pool = pooler.get_db_and_pool(database)
        cr = db.cursor()
        user_uids = pool.get('res.users').search(cr,1,[('login','=',login)])
        if not user_uids:
            raise ApplicationError("com.izaber.zerp.error.invalid_login",
                    "could not authenticate session")

        # If they do, create the session
        user_uid = user_uids[0]
        sess_obj = pool.get('zerp.users.sessions')
        sess_key = sess_obj.create_session(cr,1,user_uid)

        # Store the session information
        # Cache the session for faster lookup and continue on
        user_zerp = [database, user_uid, sess_key]
        CLIENT_CACHE.setdefault(session,{})[database] = user_zerp
        cr.commit()

        return user_zerp

    def zerp_del(self,session):
        """ Removes user session from database
        """

        # Check if the user disconnecting has a session and
        # basic sanity work
        if not session: return
        if not session in CLIENT_CACHE: return

        sess = CLIENT_CACHE[session]
        del CLIENT_CACHE[session]

        if not sess: return

        for database, data in sess.items():
            (database, user_uid, sess_key) = data
            db, pool = pooler.get_db_and_pool(database)
            cr = db.cursor()
            sess_obj = pool.get('zerp.users.sessions')
            sess_ids = sess_obj.search(cr,1,
                            [ ('name','=',sess_key) ])
            sess_obj.unlink(cr,1,sess_ids)
            cr.commit()

        return

    def rpc_execute(self,*args,**kwargs):
        """ The catch-all function to do various RPC functions with
            ZERP.
        """

        details = kwargs.get('details')
        _logger.log(logging.INFO,"Received request '{}'".format(details.procedure))

        # Check to see if request is somewhat sane
        m = re.search('com.izaber.nexus.zerp.(.+)\.([\w_]+)',details.procedure)
        if not m: raise InvalidUri()
        database = m.group(1)
        zerp = self.zerp_get(details)
        del kwargs['details']

        # Now attempt to dispatch the request to the underlying RPC system
        method = m.group(2)
        if method not in self.handled_methods:
            raise InvalidUri()
        try:
            ( service_name, method, arg1 ) = self.handled_methods[method]

            # use the uid and token to get through user.check
            params = list(zerp)
            if arg1:
                params.append( args[0] )  # model
                params.append( arg1 )     # function/method
                params.extend( args[1:] ) # arguments
            else:
                params.extend( args )

            res = openerp.netsvc.dispatch_rpc(service_name,method,params)

            _logger.log(logging.INFO,"Responding with: '{}'".format(res))
            return res

        except Exception as ex:
            raise ApplicationError(details.procedure,unicode(ex))

    ##########################################################
    # Setup/Teardown callbacks
    ##########################################################

    @inlineCallbacks
    def onJoin(self, details):
        """ Executed when the script attaches to the server
        """
        _logger.log(logging.INFO,"Joined WAMP router. Attempting registration of calls")
        databases = openerp.service.web_services.db().exp_list()

        for database in databases:
            for service_name, method in self.handled_methods.items():
                service_uri = config.get('wamp_registration_prefix','com.izaber.nexus.zerp.')\
                                            +'{}.{}'.format(database,service_name)
                _logger.log(logging.INFO,"Registering '{}' on WAMP server".format(service_uri))
                yield self.register(
                            self.rpc_execute,
                            service_uri,
                            options=RegisterOptions(details_arg='details')
                        )

        yield self.subscribe(
                    self.onLeave,
                    u'wamp.session.on_leave',
                    options=SubscribeOptions(details_arg='details')
                )

    def onLeave(self, session_id, *args, **kwargs):
        """ Executed when script detaches
        """
        self.zerp_del(session_id)

    def onConnect(self):
        """ Executed upon ZERP connecting to WAMP router
        """
        _logger.log(logging.INFO,"Connected to WAMP router. Attempting login")
        self.join(self.config.realm, [u"ticket"], config.get('wamp_login'))

    def onChallenge(self, challenge):
        """ Executed when script requires itself to authenticate with the router
        """
        if challenge.method == u"ticket":
            _logger.log(logging.INFO,"WAMP-Ticket challenge received: {}".format(challenge))
            return config.get('wamp_password')
        else:
            raise Exception("Invalid authmethod {}".format(challenge.method))

class ZERPClientFactory(websocket.WampWebSocketClientFactory, ReconnectingClientFactory):

    maxDelay = 30

    def clientConnectionFailed(self, connector, reason):
        _logger.log(logging.WARNING,"Connection Failed because '{}'".format(reason))
        ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)

    def clientConnectionLost(self, connector, reason):
        _logger.log(logging.WARNING,"Connection lost because '{}'".format(reason))
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

def wamp_start(*a):
    wamp_uri = unicode(config.get('wamp_uri',''))
    if not wamp_uri:
        _logger.log(logging.WARNING,"Not starting WAMP services as no configuration found.")
        return

    component_config = ComponentConfig(realm=unicode(config.get('wamp_realm',u'izaber')))
    session_factory = ApplicationSessionFactory(config=component_config)
    session_factory.session = ZERPSession

    transport_factory = ZERPClientFactory(session_factory, url=wamp_uri)

    isSecure, host, port, resource, path, params = parse_url(wamp_uri)
    transport_factory.host = host
    transport_factory.port = port
    websocket.connectWS(transport_factory)

    reactor.run()


