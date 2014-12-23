#!/usr/bin/env python

from __future__ import print_function

import logging
import os
import sys
import threading
import argparse
import subprocess


class TestStatus(object):
    def __init__(self, status_cond):
        self._status_cond = status_cond
        self._case_num = 0
        self.done_flag = False

    def next_test_case(self):
        with self._status_cond:
            if self.done_flag:
                return -1
            else:
                self._case_num += 1
                return self._case_num

    def notify_done(self):
        self._status_cond.acquire()
        try:
            self.done_flag = True
            self._status_cond.notify()
        finally:
            self._status_cond.release()


class TestInfo(object):
    def __init__(self, args):
        self._args = args

    def get_test_run_cmd(self, test_case):
        args = [self._args.path[0], str(test_case)]

        if self._args.verbosity > 0:
            args.extend(['v' for n in range(self._args.verbosity)])

        return args


class TestCaseRunner(threading.Thread):
    def __init__(self, info, status):
        threading.Thread.__init__(self)
        self._info = info
        self._status = status

    def run(self):
        while True:
            test_case = self._status.next_test_case()
            if test_case <= 0:
                return

            logging.info("Case %d: Start" % test_case)
            cmd = self._info.get_test_run_cmd(test_case)
            logging.debug("Case %d: cmd: %s", test_case, cmd)

            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT)
                (out, err) = p.communicate()
                ret = p.returncode
            except Exception as e:
                logging.exception('Case %d: Failed to execute %s (%s)' %
                                  (test_case, cmd, str(e)))
                self._status.notify_done()
                return

            if out:
                if not isinstance(out, str):
                    out = out.decode(sys.stdout.encoding or 'iso8859-1')
            else:
                out = ''

            # BDE uses the -1 return code to indciate that no more tests are
            # left to run.
            #   * On Linux, return code is always forced to be unsigned.
            #   * On Windows, return code is signed.
            #   * On Cygwin, -1 return code is 127!
            if (test_case > 99 or ret == -1 or ret == 255 or ret == 127):
                logging.info("Case %d: Does not exist" % test_case)
                self._status.notify_done()
                return
            else:
                logging.info("Case %d: Done (ret: %d):\n%s" %
                             (test_case, ret, out))


class TestDriverRunner:
    def __init__(self, args, num_jobs):
        self._info = TestInfo(args)
        self._status_cond = threading.Condition()
        self._status = TestStatus(self._status_cond)
        self._num_jobs = num_jobs
        self._workers = [TestCaseRunner(self._info, self._status)
                         for j in range(num_jobs)]

    def start(self):
        for worker in self._workers:
            worker.start()

        self._status_cond.acquire()
        try:
            if not self._status.done_flag:
                self._status_cond.wait()
        finally:
            self._status_cond.release()

        for worker in self._workers:
            worker.join()


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--abi')
    parser.add_argument('--junit')
    parser.add_argument('--jobs', '-j', type=int, default=4,
                        help='number of jobs to use')
    parser.add_argument('--valgrind')
    parser.add_argument('--verbosity', '-v', type=int, default=0)
    parser.add_argument('--debug', '-d', action='store_true')
    parser.add_argument('--timeout', type=int, default=100)
    parser.add_argument('path', metavar='TEST_DRIVER_PATH',
                        type=str, nargs=1)

    args = parser.parse_args()

    if args.debug:
        logging_level = logging.DEBUG
    else:
        logging_level = logging.INFO

    logging.basicConfig(level=logging_level,
                        format='[%(asctime)s] %(message)s',
                        datefmt='%H:%M:%S')

    test_driver_path = args.path[0]
    if not os.path.isfile(test_driver_path):
        logging.error("%s does not exist" % test_driver_path)
        sys.exit(1)

    runner = TestDriverRunner(args, 4)
    runner.start()
