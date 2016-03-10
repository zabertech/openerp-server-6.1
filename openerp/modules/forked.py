# -*- encoding: utf-8 -*-
#################################################################################
#
#    Copyright (C) 2015 - Zaber Technologies Inc.
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

from multiprocessing import Queue, Process

class forked(object):

    def __call__(self, func):

        # Wrap the caller function (this part does the work of the decoration)
        def inner(*args, **kwargs):

            # Wrap the decorated function in another function which will replace
            # the passed cursor argument with a new cursor unique to the new process
            def forked(dbname, q, *args, **kwargs):

                # Get our own db cursor just for this process
                from sql_db import ConnectionPool, Connection, Cursor
                cr = Connection(ConnectionPool(), dbname).cursor()

                # Replace the caller's cursor with our new cursor in args
                args = list(args[0])
                args[1] = cr
                args = tuple(args)

                # Make the call to the decorated function
                ret = func(*args, **kwargs)

                # Put the return value on the queue to send it back to caller
                q.put(ret)

            # Get the current db name from the passed cursor
            dbname = args[1].dbname

            # Create a queue through which the forked process can send data back
            # to the caller
            q = Queue()

            # Create a new forked process targetting the forked function wrapper
            p = Process(target=forked, args=(dbname, q, args))

            # Start the new process
            p.start()

            # Listen on the queue for the return value from the new process
            ret = q.get()

            # Wait for the new process to finish (probably redundent given the
            # queue will block, but anyway...)
            p.join()

            # Return the value passed us from the forked process
            return ret

        # Replace the original function with the decorated version
        return inner

