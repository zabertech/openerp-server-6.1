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

from multiprocessing import Pipe, Process
import os
import signal

class fork(object):

    def __init__(self, timeout=3600, name="[openerp-server]", name_args=[]):
        self.timeout = timeout
        self.name = name
        self.name_args = name_args

    def __call__(self, func):

        # Wrap the caller function (this part does the work of the decoration)
        def inner(*args, **kwargs):

            # If a list of argv index values is passed, append those arguments to the
            # process name
            __process_name = self.name
            for arg in self.name_args:
                __process_name += " {}".format(args[arg])

            # Wrap the decorated function in another function which will replace
            # the passed cursor argument with a new cursor unique to the new process
            def forked(dbname, send, *args, **kwargs):
                # Shut down twisted in this process if it's running
                from twisted.internet import reactor
                from twisted.internet.error import ReactorNotRunning
                try:
                    reactor.stop()
                except ReactorNotRunning:
                    pass
                
                # Set the proc title of this process for debugging
                if __process_name:
                    from setproctitle import setproctitle
                    setproctitle(__process_name)

                # Get our own db cursor just for this process
                from sql_db import ConnectionPool, Connection, Cursor
                cr = Connection(ConnectionPool(), dbname).cursor()

                # Replace the caller's cursor with our new cursor in args
                args = list(args[0])
                args[1] = cr
                args = tuple(args)

                # Make the call to the decorated function
                try:
                    ret = func(*args, **kwargs)
                except Exception as err:
                    cr.rollback()
                    ret = Exception(err)
                else:
                    cr.commit()
                finally:
                    cr.close()

                # Put the return value on the pipe to send it back to caller
                send.send(ret)
                send.close()

            # Get the current db name from the passed cursor
            dbname = args[1].dbname

            # Create a pipe through which the forked process can send data back
            # to the caller
            (recv, send) = Pipe(False)

            # Create a new forked process targetting the forked function wrapper
            p = Process(target=forked, args=(dbname, send, args), name=__process_name)

            # Start the new process and close our copy of the child's pipe end
            p.start()
            send.close()

            try:
                # Listen on the pipe for the return value from the new process
                ret = recv.recv()
            except Exception, err:
                # Default to an exception just incase the forked process doesn't respond
                ret = err
            finally:
                recv.close()
                p.join()

            # If an exception was returned from the caller, raise it
            if type(ret) is Exception:
                raise ret

            # Return the value passed us from the forked process
            return ret

        # Replace the original function with the decorated version
        return inner

