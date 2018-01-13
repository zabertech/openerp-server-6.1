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

{
    'name': 'WAMP',
    'version': '1.1',
    'category': 'Generic Modules',
    'description': """Add support for the Web Application Messaging Protocol""",
    'license': 'AGPL-3',
    'author': 'Zaber Technologies Inc. (Colin)',
    'post_load' : 'start_web_services',
    'website': 'http://www.zaber.com',
    'auto_install': True,
    'depends': ['users_ldap'],
    'init_xml': [],
    'update_xml': [
        'res_users.xml'
    ],
    'demo_xml': [],
    'installable': True,
    "external_dependencies" : {
        'python' : ['ddp'],
    }
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
