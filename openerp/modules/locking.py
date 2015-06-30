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

import threading

_locks = {}

def getlock(lockname):
    global _locks
    if not lockname in _locks:
        _locks[lockname] = threading.Lock()
    return _locks[lockname]

class locking(object):
    def __init__(self, lockname):
        self.lockname = lockname

    def __call__(self, func):
        def inner(*args, **kwargs):
            lock = getlock(self.lockname)
            lock.acquire()
            try:
                return func(*args, **kwargs)
            finally:
                lock.release()
        return inner


