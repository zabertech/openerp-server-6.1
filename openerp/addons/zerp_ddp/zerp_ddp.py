import ddp
import openerp.osv.orm
import pooler

from pprint import pprint

class ZerpDDPHandler(ddp.Handler):
    """
    """

    def on_sub(self, message):
        """
        """

    def on_unsub(self, message):
        """
        """

    def on_method(self, message):
        """
        """
        orm_model = message.params[0]
        orm_method = message.params[1]
        args = message.params[2]
        kwargs = message.params[3]
        db_name = 'today'
        uid = 96
        db, pool = pooler.get_db_and_pool(db_name)
        fn = getattr(openerp.osv.osv.service, message.method)
        try:
            res = fn(db_name, uid, orm_model, orm_method, *args, **kwargs)
            message = ddp.ddp.Result(message.id, error=None, result=res)
        except Exception as err:
            message = ddp.ddp.Result(message.id, error=err, result=None)
        self.write_message(ddp.ddp.serialize(message))
        return res

