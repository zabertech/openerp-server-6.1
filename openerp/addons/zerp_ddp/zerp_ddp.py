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
        print message.name
        pprint(globals())

    def on_unsub(self, message):
        """
        """

    def on_method(self):
        """
        """
    
    def send_result(self):
        """
        """
    
    def send_ready(self):
        """
        """

    def send_changed(self):
        """
        """

    def send_added(self):
        """
        """

    def send_removed(self):
        """
        """

    def send_updated(self):
        """
        """

