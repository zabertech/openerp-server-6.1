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
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#################################################################################

import openerp.modules.ddp as ddp
from openerp.osv import orm
from openerp.sql_db import Cursor
from tools import config
import logging

import socket
import sys
import os

from zerp_wamp import wamp_start

import posix_ipc
import json
import ejson

_logger = logging.getLogger(__name__)
ddp_temp_message_queues = {}

def ddp_decorated_write(fn):
    global ddp_temp_message_queues
    def inner_write(self, cr, user, ids, vals, context=None):
        ret = fn(self, cr, user, ids, vals, context)

        # Don't publish transient models. They can't be read yet
        # for some reason.
        if self._transient:
            return ret
        try:
            global ddp_temp_message_queues
            if not cr in ddp_temp_message_queues:
                ddp_temp_message_queues[cr] = []
            model = "{}:{}".format(cr.dbname, self._name)
            if type(ids) in [int, long]:
                ids = [ids]
            # Send read records as changed messages
            recs = orm.BaseModel.read(self, cr, user, ids, vals.keys(), context)
            for rec in recs:
                message = ddp.Changed(model, rec['id'], rec)
                ddp_temp_message_queues[cr].append(message)
        except Exception as err:
            logging.warn("Error creating DDP Changed message {}: {}".format(model, err))
        return ret
    return inner_write

def ddp_decorated_create(fn):
    global ddp_temp_message_queues
    def inner_create(self, cr, user, vals, context=None):
        ret = fn(self, cr, user, vals, context)

        # Don't publish transient models. They can't be read yet
        # for some reason.
        if self._transient:
            return ret
        try:
            global ddp_temp_message_queues
            if not cr in ddp_temp_message_queues:
                ddp_temp_message_queues[cr] = []
            model = "{}:{}".format(cr.dbname, self._name)
            # Create a new added message for each id of this
            # model which gets created
            rec = orm.BaseModel.read(self, cr, user, ret, vals.keys(), context)
            message = ddp.Added(model, ret, rec)
            ddp_temp_message_queues[cr].append(message)
        except Exception as err:
            logging.warn("Error creating DDP Added message {}: {}".format(model, err))
        return ret
    return inner_create

def ddp_decorated_unlink(fn):
    global ddp_temp_message_queues
    def inner_unlink(self, cr, user, ids, context=None):
        ret = fn(self, cr, user, ids, context)

        # Don't publish transient models. They can't be read yet
        # for some reason.
        if self._transient:
            return ret

        global ddp_temp_message_queues
        if not cr in ddp_temp_message_queues:
            ddp_temp_message_queues[cr] = []
        model = "{}:{}".format(cr.dbname, self._name)

        # Create a new removed message for each id of this
        # model which gets unlinked
        if type(ids) in [int, long]:
            ids = [ids]
        for id in ids:
            message = ddp.Removed(model, id)
            ddp_temp_message_queues[cr].append(message)
        return ret
    return inner_unlink

def ddp_decorated_commit(fn):
    global ddp_temp_message_queues
    def inner_commit(self):
        global ddp_temp_message_queues
        try:
            ret = fn(self)
        except:
            raise
        else:
            if len(ddp_temp_message_queues.get(self, [])):
                mqueue_name = config.get("wamp_mqueue", "/zerp.mqueue") 
                max_message_size = config.get("wamp_max_message_size", 8192)
                message_queue = None
                try:
                    # TODO: Open the mqueue on cursor instantiation so we don't do it so often
                    message_queue = posix_ipc.MessageQueue(mqueue_name,
                                                           flags=posix_ipc.O_CREAT,
                                                           max_message_size=int(max_message_size))
                    # With each message we pull off the queue
                    for message in ddp_temp_message_queues.get(self, []):
                        message = ddp.serialize(message, serializer=json)
                        message_queue.send(message, timeout=0.1)
                except Exception, err:
                    logging.warn("Error logging commit to socket {}: {}".format(mqueue_name, err))
                finally:
                    # Mqueue must be explicitely closed or this process will hit it's open files limit.
                    # Thanks, Stephen for finding this!
                    try:
                        message_queue.close()
                    except:
                        pass
        return ret
    return inner_commit

def ddp_decorated_rollback(fn):
    global ddp_temp_message_queues
    def inner_rollback(self):
        global ddp_temp_message_queues
        if self in ddp_temp_message_queues:
            del ddp_temp_message_queues[self]
        return fn(self)
    return inner_rollback

def start_ddp_ormlog():
    # Monkeypatch osv and orm methods
    orm.BaseModel.write = ddp_decorated_write(orm.BaseModel.write)
    orm.BaseModel.create = ddp_decorated_create(orm.BaseModel.create)
    orm.BaseModel.unlink = ddp_decorated_unlink(orm.BaseModel.unlink)
    Cursor.commit = ddp_decorated_commit(Cursor.commit)
    Cursor.rollback = ddp_decorated_rollback(Cursor.rollback)

def start_web_services():
    if (config.get("wamp_uri", False)):
        start_ddp_ormlog()
        wamp_start()
