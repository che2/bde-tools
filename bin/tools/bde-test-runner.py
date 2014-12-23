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
    def __init__(self, id_, info, status):
        threading.Thread.__init__(self)
        self._info = info
        self._status = status
        self.proc = None
        self.id_ = id_

    def log(self, message):
        logging.info("Case %d: %s" % (self.case, message))

    def debug(self, message):
        logging.debug("Case %d: %s" % (self.case, message))

    def run(self):
        while True:
            self.case = self._status.next_test_case()

            # self.test_case = test_case
            if self.case <= 0:
                return

            self.debug("START")
            cmd = self._info.get_test_run_cmd(self.case)
            self.debug("CMD %s" % cmd)

            try:
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT)
                (out, err) = self.proc.communicate()
                ret = self.proc.returncode
            except Exception as e:
                self.log("FAILED (%s)" % str(e))
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
            if (self.case > 99 or ret == -1 or ret == 255 or ret == 127):
                self.debug("DOES NOT EXIST")
                # self._status.notify_done()
                return
            elif ret == 0:
                self.log("SUCCESS (ret: %d):\n%s" % (ret, out))
            else:
                self.log("FAILED (ret: %d):\n%s" % (ret, out))


class TestDriverRunner:
    def __init__(self, args, num_jobs):
        self._args = args
        self._info = TestInfo(args)
        self._status_cond = threading.Condition()
        self._status = TestStatus(self._status_cond)
        self._num_jobs = num_jobs
        self._workers = [TestCaseRunner(j, self._info, self._status)
                         for j in range(num_jobs)]

    def _terminate_workers(self):
        logging.info("TIMED OUT AFTER %d SECONDS" % self._args.timeout)
        for worker in self._workers:
            # The following method to terminate processes is probably not
            # thread safe with out locks, but considering that we are a test
            # driver runner, doing so is probably acceptable.
            if worker.is_alive() and worker.proc:
                logging.info("TERMINATING CASE %d [thread %d] **" %
                             (worker.case, worker.id_))
                worker.proc.terminate()

    def start(self):
        for worker in self._workers:
            worker.start()

        timer = threading.Timer(self._args.timeout, self._terminate_workers)
        timer.start()
        logging.debug("TIMER STARTED")

        self._status_cond.acquire()
        try:
            if not self._status.done_flag:
                self._status_cond.wait(1)
        finally:
            self._status_cond.release()

        for worker in self._workers:
            worker.join()

        timer.cancel()

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
