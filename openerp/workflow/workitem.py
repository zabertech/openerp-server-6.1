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

#
# TODO:
# cr.execute('delete from wkf_triggers where model=%s and res_id=%s', (res_type,res_id))
#

import logging
import datetime

from openerp.tools.config import config
import openerp.netsvc as netsvc
import instance

import wkf_expr
import wkf_logs

_logger = logging.getLogger(__name__)

def create(cr, act_datas, inst_id, ident, stack):
    """ Create a new workitem for the provided instance

    @param cr: database handle
    @param act_datas: cr.selected wkf_activity entries associated with wkf (flow_start=True)
    @param inst_id: Associated wkf_instance ID for ident
    @param ident: tuple of (uid, dotted model name, resource id )
    @param stack: ???

    For each start point of the instance in the workflow, create a new state tracker (wkf_workitem).
    Once the state tracker (wkf_workitem) has been created, kick it off with workitem.process to see if it needs to do anything right away
    """

    for act in act_datas:
        cr.execute("select nextval('wkf_workitem_id_seq')")
        id_new = cr.fetchone()[0]
        cr.execute("insert into wkf_workitem (id,act_id,inst_id,state) values (%s,%s,%s,'active')", (id_new, act['id'], inst_id))
        cr.execute('select * from wkf_workitem where id=%s',(id_new,))
        res = cr.dictfetchone()
        wkf_logs.log(cr,ident,act['id'],'create:active')
        process(cr, res, ident, stack=stack)

def process(cr, workitem, ident, signal=None, force_running=False, stack=None):
    """ Let the workitem do some work

    @param cr: database handle
    @param workitem: dict of the workitem to process
    @param ident: tuple of (uid, dotted model name, resource id )
    @param signal: desired signal (or transition name) to follow upon complete
                   this will filter the list of possible transitions to
                   only that signal noted.
    @param force_running:
    @param stack: ???

    A single workitem can only be associated with a single workflow state, this
    function will see if there are any actions that must be performed on this
    workitem.

    """
    if stack is None:
        raise 'Error !!!'
    result = True
    cr.execute('select * from wkf_activity where id=%s', (workitem['act_id'],))
    activity = cr.dictfetchone()

    if config['debug_workflow']:
        _logger.debug("process {i[1]},{i[2]} workitem,{w[id]} {w[state]} -> {s}".format(w=workitem,i=ident,s=signal))

    # If a workitem is "active" we will get the configured "activity" to execute
    # upon this information
    triggers = False
    if workitem['state']=='active':
        triggers = True
        result = _execute(cr, workitem, activity, ident, stack)
        if not result:
            return False

    # If a workitem is "running" it's doing something and we don't need to work
    # further on it.
    if workitem['state']=='running':
        pass

    # If a workitem is "complete", this means that all activity/code that has to run
    # on this code is done or the subflow is now also complete. This means we can
    # move to the next node if required.
    if workitem['state']=='complete' or force_running:
        ok = _split_test(cr, workitem, activity['split_mode'], ident, signal, stack)
        triggers = triggers and not ok

    # WAT DO TRWIGGERS DO??
    if triggers:
        cr.execute('select * from wkf_transition where act_from=%s', (workitem['act_id'],))
        alltrans = cr.dictfetchall()
        for trans in alltrans:
            if trans['trigger_model']:
                ids = wkf_expr._eval_expr(cr,ident,workitem,trans['trigger_expr_id'])
                for res_id in ids:
                    cr.execute('select nextval(\'wkf_triggers_id_seq\')')
                    id =cr.fetchone()[0]
                    cr.execute('insert into wkf_triggers (model,res_id,instance_id,workitem_id,id) values (%s,%s,%s,%s,%s)', (trans['trigger_model'],res_id,workitem['inst_id'], workitem['id'], id))

    return result


# ---------------------- PRIVATE FUNCS --------------------------------

def _state_set(cr, workitem, activity, state, ident):
    """ Sets the wkf_workitem's state

    @param cr: database handle
    @param workitem: dict of the wkf_workitem to process
    @param activity: dict of the wkf_activity
    @param state: string val of what to set the state to
    @param ident: tuple of (uid, dotted model name, resource id )

    """
    cr.execute('update wkf_workitem set state=%s where id=%s', (state,workitem['id']))
    workitem['state'] = state
    wkf_logs.log(cr,ident,activity['id'],"state_set:"+state)

def _execute(cr, workitem, activity, ident, stack):
    """ Execute wkf_activity's action on a given workitem

    @param cr: database handle
    @param workitem: dict of the wkf_workitem to process
    @param activity: dict of the wkf_activity
    @param ident: tuple of (uid, dotted model name, resource id )
    @param stack: ???

    There are 4 different types of activities:

    * dummy: blank state, no processing required
             stack is used to return data from an ir.act.server function call 
                if action_id is set
    * function: executes a particular function on a workitem
                note that while the function is executing the system will
                mark the wkf_workitem's state as 'running' to prevent
                doubled up work
    * stopall: deletes the current workitem from the database
    * subflow: creates a new subflow if required 

    """
    result = True
    #
    # send a signal to parent workflow (signal: subflow.signal_name)
    #
    signal_todo = []
    if (workitem['state']=='active') and activity['signal_send']:
        cr.execute("select i.id,w.osv,i.res_id from wkf_instance i left join wkf w on (i.wkf_id=w.id) where i.id IN (select inst_id from wkf_workitem where subflow_id=%s)", (workitem['inst_id'],))
        for i in cr.fetchall():
            signal_todo.append((i[0], (ident[0],i[1],i[2]), activity['signal_send']))

    if config['debug_workflow']:
        exec_started = datetime.datetime.now()
        _logger.debug("  execute {a[kind]} {i[1]},{i[2]} {d}".format(
              i=ident,w=workitem,a=activity,d=exec_started
        ))

    # ACTIVITY: dummy
    if activity['kind']=='dummy':
        if workitem['state']=='active':
            _state_set(cr, workitem, activity, 'complete', ident)
            if activity['action_id']:
                res2 = wkf_expr.execute_action(cr, ident, workitem, activity)
                if res2:
                    stack.append(res2)
                    result=res2

    # ACTIVITY: function
    elif activity['kind']=='function':
        if workitem['state']=='active':

            if config['debug_workflow']:
                _logger.debug("  function {i[1]},{i[2]}: {a[action]}".format(
                      i=ident,w=workitem,a=activity
                ))

            _state_set(cr, workitem, activity, 'running', ident)
            returned_action = wkf_expr.execute(cr, ident, workitem, activity)
            if type(returned_action) in (dict,):
                stack.append(returned_action)
            if activity['action_id']:
                res2 = wkf_expr.execute_action(cr, ident, workitem, activity)
                # A client action has been returned
                if res2:
                    stack.append(res2)
                    result=res2
            _state_set(cr, workitem, activity, 'complete', ident)

    # ACTIVITY: stopall
    elif activity['kind']=='stopall':
        if workitem['state']=='active':
            _state_set(cr, workitem, activity, 'running', ident)
            cr.execute('delete from wkf_workitem where inst_id=%s and id<>%s', (workitem['inst_id'], workitem['id']))
            if activity['action']:
                wkf_expr.execute(cr, ident, workitem, activity)
            _state_set(cr, workitem, activity, 'complete', ident)

    # ACTIVITY: subflow
    elif activity['kind']=='subflow':

        # If the state is currently marked as 'active' it means that the node
        # has yet to start the subflow. So let's create it.
        if workitem['state']=='active':
            _state_set(cr, workitem, activity, 'running', ident)

            # action will be a python function on the wkf_instance's res_type model
            # What we expect from this function is the new target record's ID
            # As we expect that the new record will have its own workflow, we just
            # need to know what workflow this object will be launched into. We know
            # the new record's workflow id because the current wkf_activity has
            # wkf_activity.subflow_id references the target sub-object's wkf record
            if activity.get('action', False):
                id_new = wkf_expr.execute(cr, ident, workitem, activity)
                # If we don't get a new record id, stop the workflow and drop out
                if not (id_new):
                    cr.execute('delete from wkf_workitem where id=%s', (workitem['id'],))
                    return False
                assert type(id_new)==type(1) or type(id_new)==type(1L), 'Wrong return value: '+str(id_new)+' '+str(type(id_new))
                cr.execute('select id from wkf_instance where res_id=%s and wkf_id=%s', (id_new,activity['subflow_id']))
                id_new = cr.fetchone()[0]

            # If there is no function, we just put the current object on the subflow.
            # TODO: this seems a little perilous if the workflow references some other model
            else:
                id_new = instance.create(cr, ident, activity['subflow_id'])
            cr.execute('update wkf_workitem set subflow_id=%s where id=%s', (id_new, workitem['id']))
            workitem['subflow_id'] = id_new

        # If the state is running, we're waiting for the subflow to complete. Check the subflow
        # to see what the status it happens to be and if the subflow is marked 'complete', we can
        # finally mark this activity as complete as well
        if workitem['state']=='running':
            cr.execute("select state from wkf_instance where id=%s", (workitem['subflow_id'],))
            state= cr.fetchone()[0]
            if state=='complete':
                _state_set(cr, workitem, activity, 'complete', ident)

    for t in signal_todo:
        instance.validate(cr, t[0], t[1], t[2], force_running=True)

    if config['debug_workflow']:
        _logger.debug("  /execute {a[kind]} {i[1]},{i[2]} started {d}".format(
              i=ident,w=workitem,a=activity,d=exec_started
        ))


    return result

def _split_test(cr, workitem, split_mode, ident, signal=None, stack=None):
    """ Attempt to move the workitem to a target state denoted by signal

    @param cr: database handle
    @param workitem: dict of the workitem to process
    @param split_mode: Can be 'xor', 'or', or 'and' controls how the
                       next workitems get generated? #FIXME
    @param ident: tuple of (uid, dotted model name, resource id )
    @param signal: desired signal (or transition name) to follow
                   this will filter the list of possible transitions to
                   only that signal noted.
    @param stack: ???

    """
    if stack is None:
        raise 'Error !!!'

    # Find all transitions out of the current activity node. Depending on the
    # splitting style of the current activity node, create a list of possible
    # allowed transitions this record can follow.
    cr.execute('select * from wkf_transition where act_from=%s', (workitem['act_id'],))
    test = False
    transitions = []
    alltrans = cr.dictfetchall()
    if split_mode=='XOR' or split_mode=='OR':
        for transition in alltrans:
            if wkf_expr.check(cr, workitem, ident, transition,signal):
                if config['debug_workflow']:
                    _logger.debug(" {m} split {i[1]},{i[2]} workitem,{w[id]} "\
                                    "transition {t[id]},{t[signal]} OK".format(
                        w=workitem,i=ident,s=signal,t=transition,m=split_mode)
                    )
                test = True
                transitions.append((transition['id'], workitem['inst_id']))
                # XOR only allows one transition so break after finding the first one
                if split_mode=='XOR':
                    break
            else:
                if config['debug_workflow']:
                    _logger.debug(" {m} split {i[1]},{i[2]} workitem,{w[id]} "\
                                    "transition {t[id]},{t[signal]} NOK".format(
                        w=workitem,i=ident,s=signal,t=transition,m=split_mode)
                    )

    # If the split mode is 'AND', we only progress when ALL transitions can be
    # followed
    else:
        test = True
        for transition in alltrans:
            if not wkf_expr.check(cr, workitem, ident, transition,signal):
                test = False
                if config['debug_workflow']:
                    _logger.debug(" {m} split {i[1]},{i[2]} workitem,{w[id]} transition {t[id]},{t[signal]} NOK".format(
                        w=workitem,i=ident,s=signal,t=transition,m=split_mode)
                    )
                break
            else:
                if config['debug_workflow']:
                    _logger.debug(" {m} split {i[1]},{i[2]} workitem,{w[id]} transition {t[id]},{t[signal]} OK".format(
                        w=workitem,i=ident,s=signal,t=transition,m=split_mode)
                    )

            cr.execute('select count(*) from wkf_witm_trans where trans_id=%s and inst_id=%s', (transition['id'], workitem['inst_id']))
            if not cr.fetchone()[0]:
                transitions.append((transition['id'], workitem['inst_id']))

    # If we now have some transitions, let's move the instance into the new states
    # via wkf_workitems. Note that this sytem create a list of entries in
    # wkf_witm_trans then turns them into new wkf_workitems. I guess we do things
    # this way to take advantage of the create method's processing of associated actions
    if test and len(transitions):
        cr.executemany('insert into wkf_witm_trans (trans_id,inst_id) values (%s,%s)', transitions)
        cr.execute('delete from wkf_workitem where id=%s', (workitem['id'],))
        for t in transitions:
            _join_test(cr, t[0], t[1], ident, stack)
        return True
    return False

def _join_test(cr, trans_id, inst_id, ident, stack):
    """ Check to see if pending transitions can be followed. If they can, do so

    @param cr: database handle
    @param trans_id: ID of the wkf_transition we're poking
    @param workitem: dict of the workitem to process
    @param ident: tuple of (uid, dotted model name, resource id )
    @param stack: ???

    """

    # The activity that the transition will link to
    cr.execute('select * from wkf_activity where id=(select act_to from wkf_transition where id=%s)', (trans_id,))
    activity = cr.dictfetchone()

    # XOR join mode is first one is good
    if activity['join_mode']=='XOR':
        if config['debug_workflow']:
            _logger.debug(" join {a[join_mode]} {i[1]},{i[2]}".format(
                i=ident,a=activity)
            )

        create(cr,[activity], inst_id, ident, stack)
        cr.execute('delete from wkf_witm_trans where inst_id=%s and trans_id=%s', (inst_id,trans_id))

    # AND join mode requires all transitions into this activity to be ready.
    # Then we'll create the new node
    else:
        cr.execute('select id from wkf_transition where act_to=%s', (activity['id'],))
        trans_ids = cr.fetchall()
        ok = True
        for (id,) in trans_ids:
            cr.execute('select count(*) from wkf_witm_trans where trans_id=%s and inst_id=%s', (id,inst_id))
            res = cr.fetchone()[0]
            if not res:
                ok = False
                if config['debug_workflow']:
                    _logger.debug(" join {a[join_mode]} {i[1]},{i[2]} NOK".format(
                        i=ident,a=activity)
                    )

                break
            else:
                if config['debug_workflow']:
                    _logger.debug(" join {a[join_mode]} {i[1]},{i[2]} OK".format(
                        i=ident,a=activity)
                    )


        if ok:
            for (id,) in trans_ids:
                cr.execute('delete from wkf_witm_trans where trans_id=%s and inst_id=%s', (id,inst_id))
            create(cr, [activity], inst_id, ident, stack)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:

