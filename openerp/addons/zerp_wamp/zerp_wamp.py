"""

To be able to use this library, one will probably have to:

sudo apt-get install python-dev
sudo apt-get install openssl libssl-dev
sudo pip install crossbar

Configuration Options to place into openerp.conf:

wamp_url = wss://nexus.izaber.com/ws
wamp_login = someuser
wamp_password = somepass
wamp_realm = izaber
wamp_registration_prefix = com.izaber.nexus.zerp

Optional configuration

'wamp_register' will allow a ZERP database to register with an arbitrary name on the WAMP router

wamp_register = databasename,registername2=database2


"""
from tools import config
import logging
import netsvc

_logger = logging.getLogger(__name__)

import swampyer

import openerp
from openerp import pooler
import openerp.service

class ApplicationError(Exception):
    """
    """


CLIENT_CACHE = {}
DATABASE_MAPPINGS = {}
SERVICE_REWRITES = {
    # If the sevice is trying to access read, we'll just redirect it
    # to zerp_read. The reason is that read does not return the list of
    # results in the same order as passed in which breaks sorting
    'object.execute.read': 'object.execute.zerp_read',
}


class ZERPWampUri(object):
    """ Handles the parsing of the procedure URI and converts it into its
        constituent parts
    """
    def __init__(self,details):
        self.service_base = config.get('wamp_registration_prefix',u'com.izaber.nexus.zerp')
        self.service_base = unicode(self.service_base)

        uri_elements = details["procedure"].split(':')

        # Format should be
        # For reports it can be
        # <prefix>:<database>:<service>
        if len(uri_elements) == 3:
            ( prefix, self.database, self.service_name ) = uri_elements
            self.database = DATABASE_MAPPINGS.get(self.database)
            self.model = None
            self.version = 2
        # <prefix>:<database>:<model>:<service>:<method>
        elif len(uri_elements) == 4:
            ( prefix, self.database, self.model, self.service_name ) = uri_elements
            # Handle rewrites
            if self.service_name in SERVICE_REWRITES:
                self.service_name = SERVICE_REWRITES[self.service_name]
            self.database = DATABASE_MAPPINGS.get(self.database)
            self.version = 2
        else:
            raise Exception(u'URI should be in format "<prefix>:<database>:<model>:<service>:<method>"')

    def __repr__(self):
        return u"ZERPWampUri({s.service_base}:{s.database}:{s.model}:{s.service_name})".format(s=self)


class ZERPSession(swampyer.WAMPClientTicket):

    def zerp_get(self,details,uri=None):
        """ Returns a user session from database or creates a new one
        """
        global CLIENT_CACHE

        # authid is the login of the authenticated user
        login = details["caller_authid"]
        if not login:
            raise ApplicationError(u"com.izaber.zerp.error.invalid_login",
                    u"could not authenticate session")

        # Zerp needs lowercase usernames
        login = login.lower()

        # Parse out what database the user is trying to attach to
        if uri is None:
            uri = ZERPWampUri(details)

        # Ensure that the database they're trying to access actually exists
        databases = openerp.service.web_services.db().exp_list()
        if uri.database not in databases:
            raise ApplicationError(u"com.izaber.zerp.error.invalid_login",
                    u"could not authenticate session")

        # Try and find the record based upon the session
        session = details["caller"]
        if not session: return

        # If we've got a cached session, let's use that
        user_zerp = CLIENT_CACHE.get(session,{}).get(uri.database)
        if user_zerp: return user_zerp

        # Verify that the user actually exists in the database
        db, pool = pooler.get_db_and_pool(uri.database)
        cr = db.cursor()

        user_uids = pool.get('res.users').search(cr,1,[('login','=',login)])
        if not user_uids:
            raise ApplicationError(u"com.izaber.zerp.error.invalid_login",
                    u"could not authenticate session")

        # If they do, create the session
        user_uid = user_uids[0]
        sess_obj = pool.get('zerp.users.sessions')
        sess_key = sess_obj.create_session(cr,1,user_uid)

        # Store the session information
        # Cache the session for faster lookup and continue on
        user_zerp = [uri.database, user_uid, sess_key]
        CLIENT_CACHE.setdefault(session,{})[uri.database] = user_zerp

        cr.commit()
        cr.close()

        return user_zerp

    def zerp_del(self,session):
        """ Removes user session
            * Deletes session from cache
            * Removes related session tokens from each database known
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
            cr.close()

        return

    def dispatch_model_standard(self,args,kwargs,details,uri):
        """ Handle the Version 2 schema for URIs:

            [prefix].[database]:[model]:[service name]

        """
        # Returns the ZERP standard arguments that netsvc expects
        # zerp_params = [uri.database, user_uid, sess_key]
        zerp_params = self.zerp_get(details,uri)

        # We need to ensure model is at the begining of the arguments
        if uri.model:
            args.insert(0,uri.model)

        # Block calls to object.execute without method name to prevent
        # side-channel exploits
        if uri.service_name == 'object.execute':
            raise Exception(u'FQN must be used. Eg: object.execute.FUNCTIONAME')
        if uri.service_name == 'rpc.execute':
            raise Exception(u'FQN must be used. Eg: rpc.execute.FUNCTIONAME')

        # Take the service name and parse out the segments
        service_elements = uri.service_name.split('.')
        service_elements_len = len(service_elements)
        method = None
        if service_elements_len == 2:
            ( service_object, service_method) = service_elements
        elif service_elements_len == 3:
            ( service_object, service_method, method) = service_elements
        else:
            raise Exception(u'Require 2 or 3 elements for service name')

        # If there's a method, we'll want the method name added /after/ the
        # model name (so insert(1) vs insert(0))
        if method:
            args.insert(1,method)
        res = openerp.netsvc.dispatch_rpc(
                        service_object,
                        service_method,
                        zerp_params + args,
                        kwargs
                    )

        # This is for debugging. Otherwise, this can get really really big!
        # _logger.log(logging.INFO,"Responding with: '{}'".format(res))
        return res

    def dispatch_model(self, request, *args,**kwargs):
        """ The function to catch 'model' service based actions in
            ZERP.
        """

        try:
            details = request.details
            _logger.debug(u"Received model request '{}'".format(details["procedure"]))

            # Check to see if request is somewhat sane
            uri = ZERPWampUri(details)

            # Leaving this as an example stub for a future special method
            #if uri.method == 'specialmethod':
            #    return self.dispatch_model_specialmethod(args,details,uri)

            # Nope? use the normal
            if uri.version == 1:
                return self.dispatch_model_standard_legacy_v1(list(args),details,uri)
            elif uri.version == 2:
                return self.dispatch_model_standard(list(args),dict(kwargs),details,uri)
            raise Exception(u'WAMP version unhandled')

        except Exception as ex:
            _logger.warning(u"Request failed because: '{}'".format(unicode(ex))
            raise ApplicationError(details["procedure"],unicode(ex))

    def dispatch_rpc(self,*args,**kwargs):
        """ The standard function to do various RPC functions with ZERP.
        """
        try:
            details = kwargs.get('details')
            _logger.debug(u"Received request '{}'".format(details["procedure"]))

            # Check to see if request is somewhat sane
            uri = ZERPWampUri(details)
            zerp_params = list(self.zerp_get(details,uri))
            del kwargs['details']
            _logger.debug(u"Received arguments '{}'".format(zerp_params))

            # Now attempt to dispatch the request to the underlying RPC system
            res = openerp.netsvc.dispatch_rpc(
                            uri.service_name,
                            uri.method,
                            zerp_params + list(args),
                            kwargs
                        )
            _logger.debug(u"Responding with: '{}'".format(res))
            return res

        except Exception as ex:
            import traceback
            traceback.print_exc()
            _logger.warn(u"Error in dispatch because: '{}'".format(ex))
            raise ApplicationError(details["procedure"],unicode(ex))

    ##########################################################
    # Setup/Teardown callbacks
    ##########################################################

    def handle_join(self, details):
        """ Executed when the script attaches to the server
        """
        _logger.info(u"Joined WAMP router. Attempting registration of calls: {}".format(details))

        wamp_register = config.get('wamp_register','').split(',')
        for l in wamp_register:
            if '=' in l:
                (service_name, db_name) = l.split('=',1)
                service_name = service_name.strip()
                db_name = db_name.strip()
            else:
                service_name = l
                db_name = l
            if service_name and db_name:
                DATABASE_MAPPINGS[service_name] = db_name

        databases = openerp.service.web_services.db().exp_list()
        if not DATABASE_MAPPINGS:
            for database in databases:
                DATABASE_MAPPINGS[database] = database

        for service_name,db_name in DATABASE_MAPPINGS.items():
            if not db_name in databases:
                _logger.warn(u"Database '{}' does not exist for registering on WAMP!".format(db_name))
                continue

            # Version 2 Support
            # For '*.*' services (such as object.execute)
            service_uri = config.get('wamp_registration_prefix','com.izaber.nexus.zerp')\
                                        +':{}:'.format(service_name)
            service_uri = unicode(service_uri)
            _logger.info(u"Registering '{}' on WAMP server".format(service_uri))
            res = self.register(
                        service_uri,
                        self.dispatch_model,
                        details={"match": u"prefix"}
                    )

    def handle_disconnect(self):
        """ Executed when script detaches
        """
        self.zerp_del(self.session_id)
        _logger.info(u"Disconnected from WAMP router.")

def wamp_start(*a):
    # Sanity check, ensure we have something to connect to
    wamp_url = unicode(config.get('wamp_url', False))
    wamp_realm = unicode(config.get('wamp_realm', False))
    if not (wamp_url and wamp_realm):
        _logger.warn(u"Not starting WAMP services as no configuration found.")
        return
    client = ZERPSession(
        url=wamp_url,
        realm=wamp_realm,
        username=unicode(config.get('wamp_login', '')),
        password=unicode(config.get('wamp_password', '')),
        timeout=int(config.get('wamp_timeout', 10)))
    client.start()

