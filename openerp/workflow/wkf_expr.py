# -*- coding: utf-8 -*-
##############################################################################
#    
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.     
#
##############################################################################

import sys
import logging

import openerp.netsvc as netsvc
import openerp.osv as base
import openerp.pooler as pooler
from openerp.tools.safe_eval import safe_eval as eval

_logger = logging.getLogger(__name__)

class Env(dict):
    def __init__(self, cr, uid, model, ids):
        self.cr = cr
        self.uid = uid
        self.model = model
        self.ids = ids
        self.obj = pooler.get_pool(cr.dbname).get(model)
        self.columns = self.obj._columns.keys() + self.obj._inherit_fields.keys()

    def __getitem__(self, key):
        if (key in self.columns) or (key in dir(self.obj)):
            res = self.obj.browse(self.cr, self.uid, self.ids[0])
            return res[key]
        else:
            return super(Env, self).__getitem__(key)

def _eval_expr(cr, ident, workitem, action):
    ret=False
    assert action, 'You used a NULL action in a workflow, use dummy node instead.'
    for line in action.split('\n'):
        line = line.strip()
        uid=ident[0]
        model=ident[1]
        ids=[ident[2]]
        if line =='True':
            ret=True
        elif line =='False':
            ret=False
        else:
            env = Env(cr, uid, model, ids)
            ret = eval(line, env, nocopy=True)
    return ret

def execute_action(cr, ident, workitem, activity):
    obj = pooler.get_pool(cr.dbname).get('ir.actions.server')
    ctx = {'active_model':ident[1], 'active_id':ident[2], 'active_ids':[ident[2]]}
    result = obj.run(cr, ident[0], [activity['action_id']], ctx)
    return result

def execute(cr, ident, workitem, activity):
    return _eval_expr(cr, ident, workitem, activity['action'])

def check(cr, workitem, ident, transition, signal):
    """ Returns true if the workitem is in a state that allows this transition

    @param cr: database handle
    @param workitem: dict of the workitem to process
    @param ident: tuple of (uid, dotted model name, resource id )
    @param signal: desired signal (or transition name) to follow
                   if this transition's name is not the same signal
                   name as the target, automatically return none
                   This only matters if a transition has a signal
                   name associated with it. Transitions without
                   signal names will ignore the provided signal

    """
    if transition['signal'] and signal != transition['signal']:
        return False

    uid = ident[0]
    if transition['group_id'] and uid != 1:
        pool = pooler.get_pool(cr.dbname)
        user_groups = pool.get('res.users').read(cr, uid, [uid], ['groups_id'])[0]['groups_id']
        if not transition['group_id'] in user_groups:
            return False

    return _eval_expr(cr, ident, workitem, transition['condition'])


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:

