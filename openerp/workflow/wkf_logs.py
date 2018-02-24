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
# May be uncommented to logs workflows modifications
#
import logging

from openerp.tools.config import config
import openerp.netsvc as netsvc

_logger = logging.getLogger(__name__)

def log(cr,ident,act_id,info=''):

    if not config['debug_workflow']:
        return

    # Get information about the action if available
    if act_id:
        cr.execute('select w.name, wa.name '\
                  'from wkf_activity wa '\
                  'left join '\
                  'wkf w on wa.wkf_id = w.id '\
                  'where wa.id=%s',(act_id,))
        (wname,waname) = cr.fetchone()

        act_id = "action: {w}:{wa},{a}".format(
                          w=wname,
                          wa=waname,
                          a=act_id,
                      )

    msg = "{res},{res_id} {act} (uid:{uid}) {nfo}".format(
        res=ident[1],
        res_id=ident[2],
        uid=ident[0],
        act=str(act_id),
        nfo=info
    )
    _logger.debug(msg)

    #cr.execute('insert into wkf_logs (res_type, res_id, uid, act_id, time, info) values (%s,%s,%s,%s,current_time,%s)', (ident[1],int(ident[2]),int(ident[0]),int(act_id),info))

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:

