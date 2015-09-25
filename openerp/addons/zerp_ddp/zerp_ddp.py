import tornado.web
from ddp import *
import openerp.osv
import pooler

from copy import copy

class ZerpWorker(Worker):
    """
    """

class ZerpSubscription(Subscription):
    """
    """
    uid = None

    def __init__(self, id, name, params, conn, method=False):
        super(ZerpSubscription, self).__init__(id, name, params, conn, method)
        self.uid = conn.uid

    def set_uid(self, uid):
        """
        """
        self.uid = uid

    def test_collection(self, message):
        """
        """
        if self.method:
            return True
        
        try:
            return message.collection == self.params[0]['model']
        except:
            return False


    def test_domain(self, message):
        """
        """
        if self.method:
            return True
        try:
            params = self.params[0]
            if not params['domain']:
                return True
        except:
            return 

        # Use the ORM to test if the messages record id matches the
        # subscription's domain expression (this will get expensive)
        try:
            db, pool = pooler.get_db_and_pool(params['database'])
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
        if message_database != params['database']:
            return False

        return my_message

    def on_added(self, message):
        """
        """
        if self.method:
            return
        message = self.process_for_db(message)
        if not message:
            return
        if not self.test_collection(message):
            return
        if not self.test_domain(message):
            return
        super(ZerpSubscription, self).on_added(message)
     
    def on_changed(self, message):
        """
        """
        if self.method:
            return
        message = self.process_for_db(message)
        if not message:
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
    session_id = None

    def on_sub(self, rcvd):
        """
        """
        global ddp_message_queue
        global ddp_subscriptions
        sub_params = rcvd.params[0]
        database = sub_params['database']
        model = sub_params['model']
        fields = sub_params['fields']
        domain = sub_params['domain']
        args = {}
        try:
            db, pool = pooler.get_db_and_pool(self.database)
            cr = db.cursor()
            obj = pool.get(model)

            ids = obj.search(cr, self.uid, domain)

            model = "{}:{}".format(cr.dbname, model)

            subscription = ZerpSubscription(rcvd.id, rcvd.name, rcvd.params, self)
            subscription.set_uid(self.uid)
            ddp_subscriptions.add(subscription)

            res = obj.read(cr, self.uid, ids, fields)
            cr.close()

            for rec in res:
                rec_id = str(rec['id'])
                del rec['id']
                message = ddp.Added(model, rec_id, rec)
                ddp_message_queue.enqueue(message)

            message = ddp.Ready([rcvd.id])
            ddp_message_queue.enqueue(message)
        except Exception as err:
            message = ddp.NoSub(rcvd.id, err)
            ddp_message_queue.enqueue(message)
        finally:
            try:
                cr.close()
            except:
                pass


    def on_unsub(self, rcvd):
        """
        """

    def databases(self):
        """
        """
        return openerp.service.web_services.db().exp_list()

    def user(self):
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

    def login(self, database, username, password):
        """
        """
        db, pool = pooler.get_db_and_pool(database)
        cr = db.cursor()

        user_obj = pool.get('res.users')

        uids = user_obj.search(cr, 1, [('login', '=', username)])
        cr.close()
        if not uids:
            raise Exception('Invalid Login')
        uid = uids[0]

        # This will raise if it fails
        user_obj.check(database, uid, password)
        self.database = database
        self.uid = uid
        
        return self.user()

    def logout(self):
        """
        """
        self.session_id = None
        self.uid = None
        self.database = None

    def on_method(self, rcvd):
        """
        """
        global ddp_message_queue
        global ddp_subscriptions

        if rcvd.method == "databases":
            subscription = ZerpSubscription(rcvd.id, rcvd.method, rcvd.params, self, method=True)
            ddp_subscriptions.add(subscription)
            try:
                databases = self.databases()
                message = ddp.Result(rcvd.id, error=None, result=databases)
            except Exception as err:
                message = ddp.Result(rcvd.id, error="Error fetching databases", result=false)
            finally:
                ddp_message_queue.enqueue(ddp.Updated([rcvd.id]))
                ddp_message_queue.enqueue(message)
            
        elif rcvd.method == "login":
            subscription = ZerpSubscription(rcvd.id, rcvd.method, rcvd.params, self, method=True)
            ddp_subscriptions.add(subscription)
            try:
                user_info = self.login(rcvd.params[0], rcvd.params[1], rcvd.params[2])
                message = ddp.Result(rcvd.id, error=None, result=user_info)
            except Exception as err:
                message = ddp.Result(rcvd.id, error="Invalid Login", result=false)
            finally:
                ddp_message_queue.enqueue(ddp.Updated([rcvd.id]))
                ddp_message_queue.enqueue(message)

        elif rcvd.method == "logout":
            subscription = ZerpSubscription(rcvd.id, rcvd.method, rcvd.params, self, method=True)
            ddp_subscriptions.add(subscription)
            self.logout()
            ddp_message_queue.enqueue(ddp.Result(rcvd.id, error=None, result=true))
            ddp_message_queue.enqueue(ddp.Updated([rcvd.id]))
            ddp_message_queue.enqueue(message)
        
        elif rcvd.method == "execute":
            subscription = ZerpSubscription(rcvd.id, rcvd.method, rcvd.params, self, method=True)
            subscription.set_uid(self.uid)
            ddp_subscriptions.add(subscription)
            model = rcvd.params[0]
            method = rcvd.params[1]
            args = []
            kwargs = {}
            try:
                args = rcvd.params[2]
                kwargs = rcvd.params[3]
            except:
                pass

            fn = getattr(openerp.osv.osv.service, rcvd.method)
            try:
                if not (self.database and self.uid and self.session_id):
                    raise Exception("Access Denied")
                res = fn(self.database, self.uid, model, method, *args, **kwargs)
                message = ddp.Result(rcvd.id, error=None, result=res)
            except Exception as err:
                message = ddp.Result(rcvd.id, error=err.message, result=None)
            finally:
                ddp_message_queue.enqueue(ddp.Updated([rcvd.id]))
                ddp_message_queue.enqueue(message)

    def write_message(self, message):
        super(ZerpDDPHandler, self).write_message(message)

