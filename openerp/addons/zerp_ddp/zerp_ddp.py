import traceback
import uuid
import time
import tornado.web
from ddp import *
import openerp.osv
from osv import fields, osv
import pooler
from globals import login_tokens
from copy import copy
from tools import config
import logging
import netsvc

_logger = logging.getLogger(__name__)

class ZerpDDPError(ddp.DDPError):
    """
    """

class ZerpReaper(Reaper):
    """
    """

class ZerpWorker(Worker):
    """
    """

class ZerpSubscription(Subscription):
    """
    """
    uid = None
    nodata = False

    def __init__(self, id, name, params, conn, method=False, nodata=False, server_enforce_domain=False):
        super(ZerpSubscription, self).__init__(id, name, params, conn, method)
        self.uid = conn.uid
        self.nodata = nodata
        self.server_enforce_domain = server_enforce_domain
        self.database = self.conn.database

    def set_uid(self, uid):
        """
        """
        self.uid = uid

    def _matches_collection(self, message):
        """
        """
        if self.method:
            return True
        try:
            return message.collection == self.params[0]['model']
        except:
            return False


    def _matches_domain_expression(self, message):
        """
        """
        if self.method:
            return True

        try:
            params = self.params[0]
            if not params.get('domain', False):
                return True
        except:
            return True

        # Use the ORM to test if the messages record id matches the
        # subscription's domain expression (this will get expensive)
        try:
            db, pool = pooler.get_db_and_pool(self.database)
            cr = db.cursor()
            obj = pool.get(params['model'])
            ids = obj.search(cr, int(self.uid), params['domain'])
            cr.close()
            if int(message.id) in ids:
                return True
        except:
            try:
                cr.close()
            except:
                pass
        return False
        

    def process_for_db(self, message):
        """
        """
        params = self.params[0]

        # Split piggybacked databasename from collection name
        my_message = copy(message)
        (message_database, my_message.collection) = my_message.collection.split(':')

        # Does this message come from the subscribed database?
        if message_database != self.database:
            return False

        return my_message

    def _amend_added(self, message):
        """
        Send more fields to a record already added in this subscription. This
        is to allow for subscribes to the same collection with different fields
        without having to create a union of all subscribed fields before processing.
        
        TODO:In this iteration, we change the added message to a changed message. In
        the future we should probably implement a new DDP message type for amending
        data.
        """
        collection = message.collection
        id_ = message.id
        fields = message.fields
        
        changed_message = ddp.Changed(collection, id_, fields)
        self.conn.ddp_session.add_rec(collection, id_, fields.keys())
        super(ZerpSubscription, self).on_changed(changed_message)

    def _amend_subscribed_data(self, message):
        """
        Test to see if this subscription already has a copy of the added
        data, but with different fields. If so, we send it as a changed
        to amend the existing record.
        """
        collection = message.collection
        id_ = message.id
        fieldnames = set(message.fields.keys())

        try:
            added_fieldnames = set(self.conn.ddp_session.recs.get((collection, id_)))
        except:
            return False

        if not fieldnames:
            return False

        if fieldnames == added_fieldnames:
            return True

        for fieldname in set(fieldnames):
            if fieldname not in added_fieldnames:
                break
        else:
            return True

        self._amend_added(message)
        return True

    def on_added(self, message):
        """
        """
        if self.method:
            return
        message = self.process_for_db(message)
        if not message:
            return
        if not self._matches_collection(message):
            return
        if self.server_enforce_domain and not self._matches_domain_expression(message):
            return

        if not self._amend_subscribed_data(message):
            super(ZerpSubscription, self).on_added(message)
     
    def on_changed(self, message):
        """
        """
        if self.method:
            return
        message = self.process_for_db(message)
        if not message:
            return
        if not self._matches_collection(message):
            return
        if self.server_enforce_domain and not self._matches_domain_expression(message):
            return

        super(ZerpSubscription, self).on_changed(message)
    
    def on_removed(self, message):
        """
        """
        if self.method:
            return
        message = self.process_for_db(message)
        if not message:
            return
        if not self._matches_collection(message):
            return
        if self.server_enforce_domain and not self._matches_domain_expression(message):
            return

        super(ZerpSubscription, self).on_removed(message)
    
    def on_ready(self, message):
        """
        """
        if self.method:
            return
        super(ZerpSubscription, self).on_ready(message)

    def on_result(self, message):
        """
        """
        super(ZerpSubscription, self).on_result(message)
    
    def on_updated(self, message):
        """
        """
        super(ZerpSubscription, self).on_updated(message)
    

class ZerpDDPHandler(Handler):
    """
    """
    uid = None
    database = None

    def on_sub(self, rcvd):
        """
        """
        global ddp_message_queue
        global ddp_subscriptions
        try:
            params = rcvd.params[0]
            model = params['model']
            fields = params.get('fields', [])
            domain = params.get('domain', [])
            server_enforce_domain = params.get('server_enforce_domain', False)
            limit = params.get('limit', None)
            offset = params.get('offset', None)
            nodata = params.get('nodata', False)
            if not self.database:
                raise ZerpDDPError(403, "Error accessing database")

            subscription = ZerpSubscription(rcvd.id, rcvd.name, rcvd.params, self, nodata=nodata, server_enforce_domain=server_enforce_domain)
            ddp_subscriptions.add(subscription)

            # Don't send any initial data if we're only interested in
            # new things.
            if nodata:
                message = ddp.Ready([rcvd.id])
                ddp_message_queue.enqueue(message)
                return

            # Fetch the initial data sent on this subscription from
            # openerp
            db, pool = pooler.get_db_and_pool(self.database)
            cr = db.cursor()
            obj = pool.get(model)
            ids = obj.search(cr, self.uid, domain, limit=limit, offset=offset)
            res = obj.read(cr, self.uid, ids, fields)
            cr.close()

            # Piggyback the dbname on the collection name. This will get
            # stripped off when the subscription handles the outgoing
            # added messages
            model = "{}:{}".format(self.database, model)

            # Build and enqueue the initial data 'added' messages
            for rec in res:
                rec_id = str(rec['id'])
                del rec['id']
                message = ddp.Added(model, rec_id, rec)
                ddp_message_queue.enqueue(message)

            # Enqueue a ready message now that all of the data has
            # been enqueued
            message = ddp.Ready([rcvd.id])
        except ZerpDDPError as err:
            message = ddp.NoSub(rcvd.id, err)
        except Exception as err:
            message = ddp.NoSub(rcvd.id, ZerpDDPError(500, "Server Error", err.message))
        finally:
            ddp_message_queue.enqueue(message)
            try:
                cr.close()
            except:
                pass


    def databases(self):
        """
        """
        return openerp.service.web_services.db().exp_list()

    def schema(self, model):
        """
        """
        db, pool = pooler.get_db_and_pool(self.database)
        cr = db.cursor()
        model_obj = pool.get(model)
        schema = model_obj.fields_get(cr, self.uid)
        cr.close()
        return schema

    def get_user(self):
        """
        """
        fields = [
            'id',
            'name',
            'login',
            'context_tz',
            'context_lang',
            'user_email',
            'groups_id',
        ]
        fn = getattr(openerp.osv.osv.service, "execute")
        return fn(self.database, self.uid, 'res.users', 'read', self.uid, fields)

    def gen_token(self):
        return str(uuid.uuid1())

    def login(self, database, username, password):
        """
        """
        db, pool = pooler.get_db_and_pool(database)
        cr = db.cursor()

        user_obj = pool.get('res.users')

        uids = user_obj.search(cr, 1, [('login', '=', username)])
        cr.close()
        if not uids:
            raise DDPException(400, 'Invalid Login')
        uid = uids[0]

        # This will raise if it fails
        user_obj.check(database, uid, password)
        self.database = database
        self.uid = uid

        token = self.gen_token()
        self.token = token

        user = self.get_user()
        global login_tokens

        login_tokens[(database,token)] = user

        return {'user': user, 'token': token}

    def resume(self, database, token):
        """
        """
        global login_tokens
        try:
            # This will raise if it fails
            user = login_tokens[(database,token)]
            self.database = database
            self.uid = user['id']
            self.token = token
            return {'user': login_tokens[(database,token)], 'token': token}
        except:
            raise DDPException(400, 'Invalid Login')

    def logout(self, database, token):
        """
        """
        global login_tokens
        self.uid = None
        self.database = None
        self.token = None
        try:
            del login_tokens[(database, token)]
        except:
            pass

    def on_method(self, rcvd):
        """
        """
        global ddp_message_queue
        global ddp_subscription

        if rcvd.method == "databases":
            try:
                databases = self.databases()
                message = ddp.Result(rcvd.id, error=None, result=databases)
            except Exception as err:
                message = ddp.Result(rcvd.id, error=ZerpDDPError(500, "Server Error", err.message), result=false)
            finally:
                self.write_message(message)
                self.write_message(ddp.Updated([rcvd.id]))

        elif rcvd.method == "login":
            database = rcvd.params[0]
            username = rcvd.params[1]
            password = rcvd.params[2]
            try:
                user_info = self.login(database, username, password)
                message = ddp.Result(rcvd.id, error=None, result=user_info)
            except Exception as err:
                message = ddp.Result(rcvd.id, error=ZerpDDPError(400, "Invalid Login"), result=False)
            finally:
                self.write_message(message)
                self.write_message(ddp.Updated([rcvd.id]))

        elif rcvd.method == "resume":
            database = rcvd.params[0]
            token = rcvd.params[1]
            try:
                user_info = self.resume(database, token)
                message = ddp.Result(rcvd.id, error=None, result=user_info)
            except Exception as err:
                message = ddp.Result(rcvd.id, error=ZerpDDPError(400, "Invalid Login"), result=False)
            finally:
                self.write_message(message)
                self.write_message(ddp.Updated([rcvd.id]))

        elif rcvd.method == "logout":
            database = rcvd.params[0]
            token = rcvd.params[1]
            self.logout(database, token)
            message = ddp.Result(rcvd.id, error=None, result=True)
            self.write_message(message)
            self.write_message(ddp.Updated([rcvd.id]))

        elif rcvd.method == "schema":
            # This gets overwritten with a real message on success
            message = ddp.Result(rcvd.id, error=ZerpDDPError(500, "Server Error"), result=None)
            try:
                if self.uid == None:
                    raise ZerpDDPError(403, "Invalid UID")
                model = rcvd.params[0]
                if not model:
                    raise ZerpDDPError("500", "No model specified when requesting schema info")
                schema = self.schema(model)
                message = ddp.Result(rcvd.id, error=None, result=schema)
            except ZerpDDPError as err:
                message = ddp.Result(rcvd.id, error=err, result=None)
            except Exception as err:
                message = ddp.Result(rcvd.id, error=ZerpDDPError(500, "Server Error: {}".format(err)), result=None)
            finally:
                self.write_message(message)
                self.write_message(ddp.Updated([rcvd.id]))

        # object.execute, report.report_get, etc
        elif rcvd.method.index('.') > 0:
            try:
                elements = rcvd.method.split('.')
                if len(elements) != 2:
                    raise ZerpDDPError('RPC call has invalid format. Must be [service_name].[method]')
                ( service_name, method ) = elements

                # use the uid and token to get through user.check
                params = [ self.database, self.uid, self.token ]
                params.extend( rcvd.params )

                res = openerp.netsvc.dispatch_rpc(service_name,method,params)
                message = ddp.Result(rcvd.id, error=None, result=res)
            except Exception as err:
                trace = traceback.format_exc()
                message = ddp.Result(
                                rcvd.id,
                                error=ZerpDDPError(
                                            500,
                                            "Server Error",
                                            "{}\n{}".format(err.message, trace)),
                                result=None
                            )

            finally:
                self.write_message(message)
                self.write_message(ddp.Updated([rcvd.id]))

        #elif rcvd.method == "execute":
        else:
            model = rcvd.params[0]
            method = rcvd.params[1]
            args = []
            kwargs = {}
            try:
                args = rcvd.params[2]
                kwargs = rcvd.params[3]
            except:
                pass

            # We're going to retire this eventually
            _logger.warn("Client {uid}@{remote_ip} is using deprecated DDP object.{method} for {model}.{model_method}".format(
                        uid=self.uid,
                        remote_ip=self.remote_ip,
                        method=rcvd.method,
                        function=rcvd.params[0],
                        model=model,
                        model_method=method
                    ))


            fn = getattr(openerp.osv.osv.service, rcvd.method)
            try:
                if not (self.database and self.uid and self.ddp_session.ddp_session_id):
                    raise ZerpDDPError(403, "Access Denied: {} {} {}".format(self.database, self.uid, self.ddp_session.ddp_session_id))
                res = fn(self.database, self.uid, model, method, *args, **kwargs)
                message = ddp.Result(rcvd.id, error=None, result=res)
            except ZerpDDPError as err:
                message = ddp.Result(rcvd.id, error=err, result=None)
            except Exception as err:
                trace = traceback.format_exc()
                message = ddp.Result(rcvd.id, error=ZerpDDPError(500, "Server Error", "{}\n{}".format(err.message, trace)), result=None)
            finally:
                self.write_message(message)
                self.write_message(ddp.Updated([rcvd.id]))

    def on_message(self, message):
        if config.get('ddp_debug', False):
            _logger.log(logging.INFO, "DDP <<< %s", message)
        super(ZerpDDPHandler, self).on_message(message);

    def write_message(self, message):
        if config.get('ddp_debug', False):
            _logger.log(logging.INFO, "DDP >>> %s", message)
        super(ZerpDDPHandler, self).write_message(message)

class users(osv.osv):
    _inherit = "res.users"

    def check(self, db, uid, passwd):
        """ Checks the global session tokens if a token exists for validity.
            If it doesn't then passes the request up the rest of the 
            authenticators.
        """

        key = (db,passwd)

        # If the token doesn't match anything then just chain
        # the auth request up.
        if key not in login_tokens:
            return super(users,self).check(db, uid, passwd)

        # Ensure we have a token that matches an actual
        # user rather than a stub.
        user = login_tokens[key]
        if not user:
            return super(users,self).check(db, uid, passwd)

        # It does exist, let's make sure that the user isn't
        # trying anything sneaky like impersonate another user.
        if uid and user.get('id') == uid:
            return uid

        # Nope. Sadness. If you've gotten here, things have
        # gotten tres-weird.
        raise openerp.exceptions.AccessDenied()


