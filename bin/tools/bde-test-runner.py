#!/usr/bin/env python

from __future__ import print_function

import argparse
import logging
import os
import subprocess
import signal
import sys
import threading


class TestStatus(object):
    def __init__(self, status_cond):
        self._status_cond = status_cond
        self._case_num = 0
        self.is_done = False
        self.is_success = True

    def next_test_case(self):
        with self._status_cond:
            if self.is_done:
                return -1
            else:
                self._case_num += 1
                return self._case_num

    def notify_failure(self):
        self.is_success = False

    def notify_done(self):
        self._status_cond.acquire()
        try:
            self.is_done = True
            self._status_cond.notify()
        finally:
            self._status_cond.release()


class TestInfo(object):
    def __init__(self, args):
        self._args = args

    def is_verbose(self):
        return self._args.verbosity > 0

    def get_test_run_cmd(self, test_case):
        cmd = [self._args.path[0], str(test_case)]

        if self._args.verbosity > 0:
            cmd.extend(['v' for n in range(self._args.verbosity)])

        return cmd


class TestCaseRunner(threading.Thread):
    def __init__(self, id_, info, status):
        threading.Thread.__init__(self)
        self._info = info
        self._status = status
        self.proc = None
        self.id_ = id_
        self.case = 0

    def log(self, message):
        logging.info('CASE %2d: %s' % (self.case, message))

    def debug(self, message):
        logging.debug('CASE %2d: %s' % (self.case, message))

    def run(self):
        while True:
            self.case = self._status.next_test_case()

            # self.test_case = test_case
            if self.case <= 0:
                return

            self.debug('START')
            cmd = self._info.get_test_run_cmd(self.case)
            self.debug('COMMAND %s' % cmd)

            try:
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT)
                (out, err) = self.proc.communicate()
                rc = self.proc.returncode
            except Exception as e:
                self.log('EXCEPTION (%s)' % str(e))
                self._status.notify_done()
                return

            def decode_text(txt):
                if txt:
                    if not isinstance(out, str):
                        return txt.decode(sys.stdout.encoding or 'iso8859-1')
                return txt if txt else ''

            # BDE uses the -1 return code to indicate that no more tests are
            # left to run.
            #   * On Linux, -1 becomes 255, because return codes are always
            #     unsigned.
            #   * On Windows, -1 stay as -1.
            #   * On Cygwin, -1 becomes 127!
            #
            # To handle malformed test drivers, stop when there are more
            # than 99 test cases.
            if (rc == 255 or rc == -1 or rc == 127 or self.case > 99):
                self.debug('DOES NOT EXIST')
                self._status.notify_done()
                return
            elif rc == 0:
                if self._info.is_verbose():
                    msg = ' (rc %d):\n%s' % (rc, decode_text(out))
                else:
                    msg = ''
                self.log('SUCCESS%s' % msg)
            else:
                self.log('FAILED (rc %d):\n%s' % (rc, decode_text(out)))
                self._status.notify_failure()


class TestDriverRunner:
    def __init__(self, args):
        self._args = args
        self._info = TestInfo(args)
        self._status_cond = threading.Condition()
        self._status = TestStatus(self._status_cond)
        self._num_jobs = self._args.jobs
        self._workers = [TestCaseRunner(j, self._info, self._status)
                         for j in range(self._num_jobs)]

    def _terminate_procs(self):
        for worker in self._workers:
            # The following technique to terminate processes is not thread
            # safe, but this is acceptable considering that a race condition
            # will almost like mean that the test process was already
            # terminated, and the worst case scenario is that a few extra test
            # cases are run (in which case the user can use C-c to quit).
            try:
                if worker.is_alive() and worker.proc and worker.case > 0:
                    logging.info("TERMINATING TEST CASE %d" % worker.case)
                    worker.proc.terminate()
            except:
                pass

    def start(self):
        for worker in self._workers:
            worker.start()

        def timeout_handler():
            logging.info("TIMED OUT AFTER %ss" % self._args.timeout)
            self._status.notify_done()
            self._terminate_procs()

        def sigint_handler(signal, frame):
            logging.info("CAUGHT SIG_INT")
            self._status.notify_done()
            self._terminate_procs()

        timer = threading.Timer(self._args.timeout, timeout_handler)
        timer.start()

        signal.signal(signal.SIGINT, sigint_handler)
        logging.debug("TIMER STARTED")

        self._status_cond.acquire()
        try:
            if not self._status.is_done:
                self._status_cond.wait()
        finally:
            self._status_cond.release()

        for worker in self._workers:
            worker.join()

        timer.cancel()

        if self._status.is_success:
            sys.exit(0)
        else:
            sys.exit(1)

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--abi')
    parser.add_argument('--junit')
    parser.add_argument('--jobs', '-j', type=int, default=4,
                        help='number of jobs to use')
    parser.add_argument('--valgrind')
    parser.add_argument('--verbosity', '-v', type=int, default=0)
    parser.add_argument('--debug', '-d', action='store_true')
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('path', metavar='TEST_DRIVER_PATH',
                        type=str, nargs=1)

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG,
                            format='[%(asctime)s] [%(threadName)s] '
                                   ' %(message)s',
                            datefmt='%H:%M:%S')
    else:
        logging.basicConfig(level=logging.INFO,
                            format='[%(asctime)s] %(message)s',
                            datefmt='%H:%M:%S')

    test_driver_path = args.path[0]
    if not os.path.isfile(test_driver_path):
        logging.error("%s does not exist" % test_driver_path)
        sys.exit(1)

    runner = TestDriverRunner(args)
    runner.start()
