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

from ddp import *
from openerp.osv import orm
from openerp.sql_db import Cursor
from tools import config
import logging

import socket
import sys
import os

_logger = logging.getLogger(__name__)

""" Playing with unix domain sockets and datagrams for publishing
    ORM change events.

    This code replaces all of the DDP subscription handling that
    currently lives in Zerp. That code could now be written as a
    separate process that lives outside Zerp.

    All changes are send as DDP packets which are suitable for
    publishing, or are easily parsed and processed before publishing.
    For example, to fetch the record ID out of a change message and
    publish just it over WAMP for clients then to invalidate.

    RPC will still be handled by Zerp for the time being, but maybe
    that too will change. It'd be nice to have these things outside
    of Zerp entirely to reduce complexity.
"""

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

        # Create a new added message for each id of this
        # model which gets created
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

        # Create a new removed message for each id of this
        # model which gets unlinked
        for id in ids:
            message = ddp.Removed(model, str(id))
            ddp_temp_message_queues[cr].append(message)
        return fn(self, cr, user, ids, context)
    return inner_unlink

def ddp_decorated_commit(fn):
    global ddp_temp_message_queues
    def inner_commit(self):
        try:
            ret = fn(self)
        except:
            raise
        else:
            logging.warn("Committing with {} changes.".format(len(ddp_temp_message_queues.get(self, []))))
            # TODO: once I know this works, use a connection pool, or keep a connection alive on the socket
            # to make things run a little faster.
            # If there are message to send on this queue
            if len(ddp_temp_message_queues.get(self, [])):
                # establish a unix/seqpacket connection with the server.
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                sock.connect(config.get("ddp_socket", "/var/run/zerp.socket"))
                # With each message we pull off the queue
                for message in ddp_temp_message_queues.get(self, []):
                    # send it using the linux specific sendmsg (sendall in python) which is like SOCK_STREAM, but preserves boundary
                    sock.sendall(message.ejson_serialize())
                # Close the socket.
                sock.shutdown()
        return ret
    return inner_commit

def ddp_decorated_rollback(fn):
    global ddp_temp_message_queues
    def inner_rollback(self):
        logging.warn("Committing with {} changes.".format(len(ddp_temp_message_queues.get(cr, []))))
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
    if config.get("ddp_enable", False):
        start_ddp_ormlog()
