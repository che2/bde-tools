#!/usr/bin/python

from __future__ import print_function

import logging
import os
import sys
import time
import threading


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


class TestCaseRunner(threading.Thread):
    def __init__(self, status):
        threading.Thread.__init__(self)
        self._status = status

    def run(self):
        while True:
            test_case = self._status.next_test_case()
            if test_case <= 0:
                return

            sys.stdout.write("Running Case %d\n" % test_case)
            if test_case > 93:
                sys.stdout.write("Test Case %d does not exist\n" % test_case)
                self._status.notify_done()
                return


class TestDriverRunner:
    def __init__(self, num_jobs):
        self._status_cond = threading.Condition()
        self._status = TestStatus(self._status_cond)
        self._num_jobs = num_jobs
        self._workers = [TestCaseRunner(self._status)
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
    # Don't buffer sterr or stdout.
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)
    sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 0)

    logging.basicConfig(level=logging.DEBUG,
                        format='%(message)s')

    runner = TestDriverRunner(5)
    runner.start()
