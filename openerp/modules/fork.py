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
import sys
import signal
from time import sleep
import openerp.tools.config
import logging
_logger = logging.getLogger(__name__)

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
            process_name = self.name
            for arg in self.name_args:
                process_name += " {}".format(args[arg])

            # Wrap the decorated function in another function which will replace
            # the passed cursor argument with a new cursor unique to the new process
            def forked(dbname, send, *args, **kwargs):

                # Make sure subprocesses exit on sigint
                def term_handler(signal, fname):
                    sleep(10) 
                    send.close()
                    sys.exit()

                signal.signal(signal.SIGTERM, term_handler)
                # Shut down twisted in this process if it's running
                from twisted.internet import reactor
                from twisted.internet.error import ReactorNotRunning
                try:
                    reactor.stop()
                except ReactorNotRunning:
                    pass
                
                # Set the proc title of this process for debugging
                if process_name:
                    from setproctitle import setproctitle
                    setproctitle(process_name)

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

                # can't hurt
                sys.exit()

            # Get the current db name from the passed cursor
            dbname = args[1].dbname

            # Create a pipe through which the forked process can send data back
            # to the caller
            (recv, send) = Pipe(False)

            # Create a new forked process targetting the forked function wrapper
            p = Process(target=forked, args=(dbname, send, args), name=process_name)

            # Daemon processes should die when the parent is killed
            p.daemon = True

            # Start the new process and close our copy of the child's pipe end
            p.start()
            send.close()

            try:
                # Listen on the pipe for the return value from the new process
                timeout = int(openerp.tools.config.get('forked_job_timeout', 3600))
                if recv.poll(timeout):
                    ret = recv.recv()
                else:
                    ret = Exception('TimeoutError', 'Forked process {} ran for longer than {} seconds and was terminated.'.format(p.pid, timeout))
                    _logger.warning('Terminating forked proccess {} with SIGTERM'.format(p.pid))
                    p.terminate()
            finally:
                recv.close()
                p.join(3)

            # If the process is hung, kill it for realsies
            if p.is_alive():
                _logger.warning('Terminating forked proccess {} with SIGKILL'.format(p.pid))
                os.kill(p.pid, signal.SIGKILL)
                p.join(3)

            if p.is_alive():
                _logger.error('Unable to terminate forked process {}'.format(p.pid))

            # If an exception was returned from the caller, raise it
            if type(ret) is Exception:
                raise ret

            # Return the value passed us from the forked process
            return ret

        # Replace the original function with the decorated version
        return inner

