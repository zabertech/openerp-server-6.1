# -*- encoding: utf-8 -*-
#################################################################################
#
#    Copyright (C) 2015 - Zaber Technologies
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
#    along with self.program.  If not, see <http://www.gnu.org/licenses/>.
#
#################################################################################

import openerp.modules.ddp as ddp
from openerp.osv import orm
import openerp.pooler as pooler
from openerp.sql_db import Cursor
from tools import config
import logging

import socket
import sys
import os

from zerp_wamp import wamp_start

import json
import ejson

import res_users


_zerp_wamp_monkeypatched = False

_logger = logging.getLogger(__name__)
ddp_transaction_message_queues = {}

def ddp_decorated_write(fn):
    global ddp_transaction_message_queues
    def inner_write(self, cr, user, ids, vals, context=None):
        ret = fn(self, cr, user, ids, vals, context)
        # Don't do any publishing if the database is in migration
        if pooler.get_pool(cr.dbname)._init:
            return ret

        # Don't publish anything if the model or cursor is flagged
        if getattr(self, '_disable_wamp_publish', False) or getattr(cr, '_disable_wamp_publish', False):
            return ret

        # Don't publish transient models. They can't be read yet
        # for some reason.
        if self._transient:
            return ret
        try:
            global ddp_transaction_message_queues
            if not cr in ddp_transaction_message_queues:
                ddp_transaction_message_queues[cr] = []
            model = "{}:{}".format(cr.dbname, self._name)
            if type(ids) in [int, long]:
                ids = [ids]

            if getattr(self, '_disable_wamp_publish_data', False) or getattr(cr, '_disable_wamp_publish_data', False):
                # Don't publish data if the cursor or model are flagged
                for id in ids:
                    message = ddp.Changed(model, id, None)
                    ddp_transaction_message_queues[cr].append(message)

            else:
                # Send read records as changed messages
                recs = orm.BaseModel.read(self, cr, user, ids, vals.keys(), context)
                for rec in recs:
                    message = ddp.Changed(model, rec['id'], rec)
                    ddp_transaction_message_queues[cr].append(message)

        except Exception as err:
            logging.warn("Error creating DDP Changed message {}: {}".format(model, err))
        return ret
    return inner_write

def ddp_decorated_create(fn):
    global ddp_transaction_message_queues
    def inner_create(self, cr, user, vals, context=None):
        ret = fn(self, cr, user, vals, context)

        # Don't do any publishing if the database is in migration
        if pooler.get_pool(cr.dbname)._init:
            return ret

        # Don't publish anything if the model or cursor is flagged
        if getattr(self, '_disable_wamp_publish', False) or getattr(cr, '_disable_wamp_publish', False):
            return ret

        # Don't publish transient models. They can't be read yet
        # for some reason.
        if self._transient:
            return ret
        try:
            global ddp_transaction_message_queues
            if not cr in ddp_transaction_message_queues:
                ddp_transaction_message_queues[cr] = []
            model = "{}:{}".format(cr.dbname, self._name)
            # Create a new added message for each id of this
            # model which gets created
            if getattr(self, '_disable_wamp_publish_data', False) or getattr(cr, '_disable_wamp_publish_data', False):
                message = ddp.Added(model, ret, None)
            else:
                rec = orm.BaseModel.read(self, cr, user, ret, [], context)
                message = ddp.Added(model, ret, rec)
            ddp_transaction_message_queues[cr].append(message)
        except Exception as err:
            logging.warn("Error creating DDP Added message {}: {}".format(model, err))
        return ret
    return inner_create

def ddp_decorated_unlink(fn):
    global ddp_transaction_message_queues
    def inner_unlink(self, cr, user, ids, context=None):
        ret = fn(self, cr, user, ids, context)

        # Don't do any publishing if the database is in migration
        if pooler.get_pool(cr.dbname)._init:
            return ret

        # Don't publish anything if the model or cursor is flagged
        if getattr(self, '_disable_wamp_publish', False) or getattr(cr, '_disable_wamp_publish', False):
            return ret

        # Don't publish transient models. They can't be read yet
        # for some reason.
        if self._transient:
            return ret

        global ddp_transaction_message_queues
        if not cr in ddp_transaction_message_queues:
            ddp_transaction_message_queues[cr] = []
        model = "{}:{}".format(cr.dbname, self._name)

        # Create a new removed message for each id of this
        # model which gets unlinked
        if type(ids) in [int, long]:
            ids = [ids]
        for id in ids:
            message = ddp.Removed(model, id)
            ddp_transaction_message_queues[cr].append(message)
        return ret
    return inner_unlink

def ddp_decorated_commit(fn):
    def inner_commit(self):
        global ddp_transaction_message_queues
        try:
            ret = fn(self)
            # Turn off the disable_wamp_publish and disable_wamp_publish_data flags
            # as they're only temporary
            if getattr(self, '_disable_wamp_publish_data', False):
                self.disable_wamp_publish_data = False
            # Don't bother checking for data to publish if the cursor is
            # flagged
            if getattr(self, '_disable_wamp_publish', False):
                self.disable_wamp_publish = False
                try:
                    del ddp_transaction_message_queues[self]
                except Exception:
                    pass
                return ret
        except:
            # Destroy the transaction queue
            del ddp_transaction_message_queues[self]
            raise
        else:
            if len(ddp_transaction_message_queues.get(self, [])):
                try:
                    wamp = pooler.get_pool(self.dbname).get('res.users').wamp_connect(self, 0)
                    for message in ddp_transaction_message_queues.get(self, []):
                        data_uri = u'{service_uri}:{collection}:data.{record_id}.{msg}'.format(
                            service_uri='zerp',
                            collection=message.collection,
                            record_id=message.id,
                            msg=message.msg
                        )
                        events_uri = u'{service_uri}:{collection}:events.{record_id}.{msg}'.format(
                            service_uri='zerp',
                            collection=message.collection,
                            record_id=message.id,
                            msg=message.msg
                        )
                        message.collection = message.collection.split(':')[1] # Remove database name from collection
                        wamp.publish(data_uri, args=[message.__dict__])
                        wamp.publish(events_uri, args=[message.__dict__['msg']])

                    # Destroy the transaction queue
                    del ddp_transaction_message_queues[self]
                except Exception, err:
                    logging.warn("Error logging commit: {}".format(err))
                    import traceback
                    traceback.print_exc()
        return ret
    return inner_commit

def ddp_decorated_rollback(fn):
    global ddp_transaction_message_queues
    def inner_rollback(self):
        global ddp_transaction_message_queues
        if self in ddp_transaction_message_queues:
            del ddp_transaction_message_queues[self]
        return fn(self)
    return inner_rollback

def start_ddp_ormlog():
    # Monkeypatch osv and orm methods
    global _zerp_wamp_monkeypatched
    if not _zerp_wamp_monkeypatched:
        orm.BaseModel.write = ddp_decorated_write(orm.BaseModel.write)
        orm.BaseModel.create = ddp_decorated_create(orm.BaseModel.create)
        orm.BaseModel.unlink = ddp_decorated_unlink(orm.BaseModel.unlink)
        Cursor.commit = ddp_decorated_commit(Cursor.commit)
        Cursor.rollback = ddp_decorated_rollback(Cursor.rollback)
        _zerp_wamp_monkeypatched = True

def start_web_services():
    if (config.get("wamp_url", False)):
        start_ddp_ormlog()
        wamp_start()
