# -*- encoding: utf-8 -*-
#################################################################################
#
#    Copyright (C) 2015 - Aki Mimoto 
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#################################################################################

from ddp import *
import zerp_ddp
import threading
import Queue
from openerp.osv import osv, orm
from openerp import pooler
from pprint import pprint

from globals import *

def ddp_decorated_write(fn):
    global ddp_temp_message_queues
    def inner_write(self, cr, user, ids, vals, context=None):
        if type(ids) in [int, long]:
            ids = [ids]
        global ddp_temp_message_queues
        if not cr in ddp_temp_message_queues:
            ddp_temp_message_queues[cr] = []
        model = "{}:{}".format(cr.dbname, self._name)
        ret = fn(self, cr, user, ids, vals, context)

        # Send read records as changed messages
        recs = orm.BaseModel.read(self, cr, user, ids, vals.keys(), context)
        for rec in recs:
            message = ddp.Changed(model, str(rec['id']), rec)
            ddp_temp_message_queues[cr].append(message)
        return ret
    return inner_write

def ddp_decorated_create(fn):
    global ddp_temp_message_queues
    def inner_create(self, cr, user, vals, context=None):
        global ddp_temp_message_queues
        if not cr in ddp_temp_message_queues:
            ddp_temp_message_queues[cr] = []
        model = "{}:{}".format(cr.dbname, self._name)
    
        id = fn(self, cr, user, vals, context)
        
        # Create a new changed message for each id of this
        # model which gets changed
        message = ddp.Added(model, str(id), vals)
        ddp_temp_message_queues[cr].append(message)
        return id
    return inner_create

def ddp_decorated_unlink(fn):
    global ddp_temp_message_queues
    def inner_unlink(self, cr, user, ids, context=None):
        if type(ids) in [int, long]:
            ids = [ids]
        global ddp_temp_message_queues
        if not cr in ddp_temp_message_queues:
            ddp_temp_message_queues[cr] = []
        model = "{}:{}".format(cr.dbname, self._name)
    
        # Create a new changed message for each id of this
        # model which gets changed
        for id in ids:
            message = ddp.Removed(model, str(id))
            ddp_temp_message_queues[cr].append(message)
        return fn(self, cr, user, ids, context)
    return inner_unlink

def execute(self, db, uid, obj, method, *args, **kw):
    global ddp_temp_message_queues
    global ddp_message_queue
    cr = pooler.get_db(db).cursor()

    # Create a new temporary message queue for the cursor to collect messages
    # this cursor generates for later use if it's committed or disposal if not
    ddp_temp_message_queues.setdefault(cr, [])
    try:
        try:
            if method.startswith('_'):
                raise except_osv('Access Denied', 'Private methods (such as %s) cannot be called remotely.' % (method,))
            res = self.execute_cr(cr, uid, obj, method, *args, **kw)
            if res is None:
                _logger.warning('The method %s of the object %s can not return `None` !', method, obj)
            
            cr.commit()
        except Exception as err:

            # Remove this cursor and its temporary message queue from the temporary
            # queues pool since we're about to roll back its changes and destroy it
            del(ddp_temp_message_queues[cr])
            
            cr.rollback()
            raise
    finally:
        # Copy all messages from the temporary queue to the main queue for processing
        # TODO: rewrite as something like ddp.enqueue_messages(messages_list)
        if cr in ddp_temp_message_queues:
            for item in ddp_temp_message_queues[cr]:
                ddp_message_queue.put(item)
        
        cr.close()
    return res

def launch_ddp():
    global server
    global server_thread

    # globals created from ddp/globals.py
    global ddp_message_queue
    global ddp_subscriptions
    global ddp_sessions

    # Monkeypatch osv and orm methods
    osv.object_proxy.execute = execute
    orm.BaseModel.write = ddp_decorated_write(orm.BaseModel.write)
    orm.BaseModel.create = ddp_decorated_create(orm.BaseModel.create)
    orm.BaseModel.unlink = ddp_decorated_unlink(orm.BaseModel.unlink)

    # Create then start the server
    server = Server(zerp_ddp.ZerpDDPHandler, '/ddp', 3001)
    server_thread = threading.Thread(target=lambda *a: server.start())
    server_thread.daemon = False
    server_thread.start()

    # Create then start the message queue processor
    worker = zerp_ddp.ZerpWorker()
    worker_thread = threading.Thread(target=lambda *a: worker.start())
    worker_thread.daemon = False
    worker_thread.start()

    # Create then start the reaper
    reaper = zerp_ddp.ZerpReaper()
    reaper_thread = threading.Thread(target=lambda *a: reaper.start())
    reaper_thread.daemon = False
    reaper_thread.start()

