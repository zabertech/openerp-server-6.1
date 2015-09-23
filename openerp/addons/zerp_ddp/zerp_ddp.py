from ddp import *
import openerp.osv
import pooler

class ZerpDDPHandler(Handler):
    """
    """
    uid = 96
    db_name = 'today'
    session_id = 'blee'

    def on_sub(self, rcvd):
        """
        """
        global ddp_message_queue
        global ddp_subscriptions
        model = rcvd.params['model']
        fields = rcvd.params['fields']
        domain = rcvd.params['domain']
        args = {}
        db, pool = pooler.get_db_and_pool(self.db_name)
        cr = db.cursor()
        try:
            obj = pool.get(model)
            ids = obj.search(cr, self.uid, domain)
            subscription = ddp.Subscription(rcvd.id, rcvd.name, rcvd.params, self)
            for id in ids:
                subscription.add_rec(model, id)
            ddp_subscriptions.append(subscription)
            res = obj.read(cr, self.uid, ids, fields)
            for rec in res:
                rec_id = rec['id']
                del rec['id']
                message = ddp.Added(model, rec_id, rec)
                ddp_message_queue.put(message)
            message = ddp.Ready([rcvd.id])
            ddp_message_queue.put(message)
            print ddp_message_queue, ddp_subscriptions
        except Exception as err:
            message = ddp.NoSub(rcvd.id, err)
            ddp_message_queue.put(message)
            raise err
        finally:
            cr.close()
            

    def on_unsub(self, rcvd):
        """
        """

    def on_method(self, rcvd):
        """
        """
        model = rcvd.params[0]
        method = rcvd.params[1]
        args = rcvd.params[2]
        kwargs = rcvd.params[3]
        fn = getattr(openerp.osv.osv.service, rcvd.method)
        try:
            res = fn(self.db_name, self.uid, model, method, *args, **kwargs)
            message = ddp.Result(rcvd.id, error=None, result=res)
        except Exception as err:
            message = ddp.Result(rcvd.id, error=err, result=None)
        finally:
            self.write_message(message)
    def write_message(self, message):
        super(ZerpDDPHandler, self).write_message(message)
        print message

