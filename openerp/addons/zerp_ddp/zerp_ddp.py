import tornado.web
from ddp import *
import openerp.osv
import pooler

class ZerpWorker(Worker):
    """
    """
    def on_added(self, subscription, message):
        model = ''
        try:
            model = subscription.params[0]['model']
        except:
            pass
        if message.collection == model:
            super(ZerpWorker, self).on_added(subscription, message)

class ZerpDDPHandler(Handler):
    """
    """
    uid = None
    db_name = None
    session_id = None

    def on_sub(self, rcvd):
        """
        """
        global ddp_message_queue
        global ddp_subscriptions
        sub_params = rcvd.params[0]
        model = sub_params['model']
        fields = sub_params['fields']
        domain = sub_params['domain']
        args = {}
        try:
            db, pool = pooler.get_db_and_pool(self.db_name)
            cr = db.cursor()
            obj = pool.get(model)

            ids = obj.search(cr, self.uid, domain)

            subscription = ddp.Subscription(rcvd.id, rcvd.name, rcvd.params, self)
            for id in ids:
                subscription.add_rec(model, str(id))
            ddp_subscriptions.append(subscription)

            res = obj.read(cr, self.uid, ids, fields)
            cr.close()

            for rec in res:
                rec_id = str(rec['id'])
                del rec['id']
                message = ddp.Added(model, rec_id, rec)
                ddp_message_queue.put(message)
            message = ddp.Ready([rcvd.id])
            ddp_message_queue.put(message)
        except Exception as err:
            message = ddp.NoSub(rcvd.id, err)
            ddp_message_queue.put(message)
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
        return fn(self.db_name, self.uid, 'res.users', 'read', self.uid, fields)

    def login(self, db_name, username, password):
        """
        """
        db, pool = pooler.get_db_and_pool(db_name)
        cr = db.cursor()

        user_obj = pool.get('res.users')

        uids = user_obj.search(cr, 1, [('login', '=', username)])
        cr.close()
        if not uids:
            raise Exception('Invalid Login')
        uid = uids[0]

        # This will raise if it fails
        user_obj.check(db_name, uid, password)
        self.db_name = db_name
        self.uid = uid
        
        return self.user()

    def logout(self):
        """
        """
        self.session_id = None
        self.uid = None
        self.db_name = None

    def on_method(self, rcvd):
        """
        """
        global ddp_message_queue
        global ddp_subscriptions

        subscription = ddp.Subscription(rcvd.id, rcvd.method, rcvd.params, self)
        ddp_subscriptions.append(subscription)

        if rcvd.method == "databases":
            try:
                databases = self.databases()
                message = ddp.Result(rcvd.id, error=None, result=databases)
            except Exception as err:
                message = ddp.Result(rcvd.id, error="Error fetching databases", result=false)
            finally:
                ddp_message_queue.put(ddp.Updated([rcvd.id]))
                ddp_message_queue.put(message)
            
        elif rcvd.method == "login":
            try:
                user_info = self.login(rcvd.params[0], rcvd.params[1], rcvd.params[2])
                message = ddp.Result(rcvd.id, error=None, result=user_info)
            except Exception as err:
                message = ddp.Result(rcvd.id, error="Invalid Login", result=false)
            finally:
                ddp_message_queue.put(ddp.Updated([rcvd.id]))
                ddp_message_queue.put(message)

        elif rcvd.method == "logout":
            self.logout()
            ddp_message_queue.put(ddp.Result(rcvd.id, error=None, result=true))
            ddp_message_queue.put(ddp.Updated([rcvd.id]))
            ddp_message_queue.put(message)
        
        elif rcvd.method == "execute":
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
                if not (self.db_name and self.uid and self.session_id):
                    raise Exception("Access Denied")
                res = fn(self.db_name, self.uid, model, method, *args, **kwargs)
                message = ddp.Result(rcvd.id, error=None, result=res)
            except Exception as err:
                message = ddp.Result(rcvd.id, error=err.message, result=None)
            finally:
                ddp_message_queue.put(ddp.Updated([rcvd.id]))
                ddp_message_queue.put(message)

    def write_message(self, message):
        super(ZerpDDPHandler, self).write_message(message)

