# This is a fork of waf_unit_test.py supporting BDE-style unit tests.

from __future__ import print_function

import fnmatch
import os
import sys
import time

from waflib import Utils
from waflib import Task
from waflib import Logs
from waflib import Options
from waflib import TaskGen

from bdebuild.common import sysutil
from bdebuild.waf import lcov

testlock = Utils.threading.Lock()
test_runner_path = os.path.join(sysutil.repo_root_path(), 'bin',
                                'bde_runtest.py')


@TaskGen.feature('cxx', 'c')
@TaskGen.after_method('process_use')
def add_coverage(self):
    if self.bld.env['with_coverage']:
        if getattr(self, 'uselib', None):
            if 'GCOV' not in self.uselib:
                self.uselib += ['GCOV']
        else:
            self.uselib = ['GCOV']


@TaskGen.feature('test')
@TaskGen.after_method('apply_link')
def make_test(self):
    """Create the unit test task.

    There can be only one unit test task by task generator.
    """
    if getattr(self, 'link_task', None):
        self.create_task('utest', self.link_task.outputs)


class utest(Task.Task):
    """Execute a unit test
    """
    color = 'PINK'
    after = ['vnum', 'inst']
    vars = []

    def runnable_status(self):
        """Return whether the test can be run.

        Execute the test if the option ``--test run`` has been used.
        """

        skip_test = Options.options.test not in ('run', 'changed')
        if skip_test:
            return Task.SKIP_ME

        ret = super(utest, self).runnable_status()
        if ret == Task.SKIP_ME:
            if Options.options.test == 'run':
                return Task.RUN_ME

        return ret

    def get_testcmd(self):
        testcmd = [
            sys.executable, test_runner_path,
            '--verbosity=%s' % Options.options.test_v,
            '--timeout=%s' % Options.options.test_timeout,
            '-j%s' % Options.options.test_j,
            self.testdriver_node.abspath()
        ]
        if Options.options.gtest:
            testcmd += ['--gtest']
        if Options.options.test_junit:
            testcmd += ['--junit=%s-junit.xml' %
                        self.testdriver_node.abspath()]

        if Options.options.valgrind:
            testcmd += [
                '--valgrind',
                '--valgrind-tool=%s' % Options.options.valgrind_tool
            ]
        return testcmd

    def run(self):
        """Execute the test.

        The execution is always successful, but the results are stored on
        ``self.generator.bld.utest_results`` for postprocessing.
        """

        self.testdriver_node = self.inputs[0]
        try:
            fu = getattr(self.generator.bld, 'all_test_paths')
        except AttributeError:
            # this operation may be performed by at most #maxjobs
            fu = os.environ.copy()

            lst = []
            for g in self.generator.bld.groups:
                for tg in g:
                    if getattr(tg, 'link_task', None):
                        s = tg.link_task.outputs[0].parent.abspath()
                        if s not in lst:
                            lst.append(s)

            def add_path(dct, path, var):
                dct[var] = os.pathsep.join(Utils.to_list(path) +
                                           [os.environ.get(var, '')])

            if Utils.is_win32:
                add_path(fu, lst, 'PATH')
            elif Utils.unversioned_sys_platform() == 'darwin':
                add_path(fu, lst, 'DYLD_LIBRARY_PATH')
                add_path(fu, lst, 'LD_LIBRARY_PATH')
            else:
                add_path(fu, lst, 'LD_LIBRARY_PATH')
            self.generator.bld.all_test_paths = fu

        cwd = self.testdriver_node.parent.abspath()
        testcmd = self.get_testcmd()

        start_time = time.time()
        proc = Utils.subprocess.Popen(testcmd, cwd=cwd, env=fu,
                                      stderr=Utils.subprocess.STDOUT,
                                      stdout=Utils.subprocess.PIPE)
        stdout = proc.communicate()[0]
        end_time = time.time()

        if not isinstance(stdout, str):
            stdout = stdout.decode(sys.stdout.encoding or 'iso8859-1')

        tup = (self.testdriver_node, proc.returncode, stdout,
               end_time - start_time, self.generator.source[0])
        self.generator.utest_result = tup

        testlock.acquire()
        try:
            bld = self.generator.bld
            Logs.debug("ut: %r", tup)
            try:
                bld.utest_results.append(tup)
            except AttributeError:
                bld.utest_results = [tup]
        finally:
            testlock.release()


def print_test_summary(ctx):
    """Display an execution summary.

    Args:
        ctx (BuildContext): The build context.

    Returns:
        Number of test failures and total number of tests.
    """

    def get_time(seconds):
        m, s = divmod(seconds, 60)
        if m == 0:
            return '%dms' % (seconds * 1000)
        else:
            return '%02d:%02d' % (m, s)

    lst = getattr(ctx, 'utest_results', [])
    Logs.pprint('CYAN', 'Test Summary')

    total = len(lst)
    tfail = len([x for x in lst if x[1]])

    Logs.pprint('CYAN', '  tests that pass %d/%d' % (total-tfail, total))
    for (f, code, out, t, _) in lst:
        if not code:
            if ctx.options.show_test_out:
                Logs.pprint('YELLOW', '[%s (TEST)] <<<<<<<<<<' % f.abspath())
                Logs.info(out, extra={'c1': '', 'c2': ''})
                Logs.pprint('YELLOW', '>>>>>>>>>>')
            else:

                msg = '%s%s%s %s(%s)%s' % (
                    Logs.colors.GREEN, f.abspath(), Logs.colors.NORMAL,
                    Logs.colors.YELLOW, get_time(t), Logs.colors.NORMAL)
                Logs.info(msg, extra={'c1': '', 'c2': ''})

    Logs.pprint('CYAN', '  tests that fail %d/%d' % (tfail, total))
    for (f, code, out, _, _) in lst:
        if code:
            Logs.pprint('RED', '[%s (TEST)] <<<<<<<<<<' % f.abspath())
            Logs.info(out, extra={'c1': '', 'c2': ''})
            Logs.pprint('RED', '>>>>>>>>>>')

    return tfail, total


def generate_coverage_report(ctx):
    """Generate a test coverage report.

    Args:
        ctx (BuildContext): The build context.

    Returns:
        True if successful.
    """

    lst = getattr(ctx, 'utest_results', [])
    obj_dirs = []
    src_dirs = []
    for (tst, _, _, _, src) in lst:
        if tst.parent.abspath() not in obj_dirs:
            obj_dirs.append(tst.parent.abspath())
            src_dirs.append(src.parent.abspath())

    tmp_dir_node = ctx.bldnode.make_node('_test_coverage')
    tmp_dir_node.mkdir()

    if ctx.options.coverage_out:
        test_coverage_out_path = ctx.options.coverage_out
    else:
        test_coverage_out_path = tmp_dir_node.make_node('report').abspath()

    return lcov.generate_coverage_report(
        obj_dirs, src_dirs, ctx.path.abspath(), ctx.bldnode.abspath(),
        tmp_dir_node.abspath(), test_coverage_out_path, ctx.env['LCOV'],
        ctx.env['GENHTML'])


def remove_gcda_files(ctx):
    """Remove gcda coverage files generated from previous test run.

    Info about the types of gcov data files:
    https://gcc.gnu.org/onlinedocs/gcc/Gcov-Data-Files.html
    """

    Logs.info('Removing leftover gcda files...')
    matches = []
    for root, dirnames, filenames in os.walk(ctx.bldnode.abspath()):
        for filename in fnmatch.filter(filenames, '*.gcda'):
            matches.append(os.path.join(root, filename))

    for f in matches:
        os.remove(f)


def post_build_fun(ctx):
    is_success = True
    num_test_failures, num_tests = print_test_summary(ctx)

    error_msg = ''
    if num_test_failures > 0:
        error_msg += '%d/%d tests have failed.' % (num_test_failures,
                                                   num_tests)
        is_success = False
    else:
        Logs.info('All tests passed.')

    if ctx.env['with_coverage']:
        is_coverage_success = generate_coverage_report(ctx)
        if not is_coverage_success:
            is_success = False
            error_msg += '\nFailed to generate coverage report.'

    if not is_success:
        ctx.fatal('%s (%s)' % (error_msg, str(ctx.log_timer)))


def build(ctx):
    if ctx.options.test == 'run':
        if ctx.env['with_coverage']:
            remove_gcda_files(ctx)
        ctx.add_post_fun(post_build_fun)


def configure(ctx):
    if ctx.options.with_coverage:
        if ctx.env.COMPILER_CC == 'gcc':
            ctx.check(cxxflags=['-fprofile-arcs', '-ftest-coverage'],
                      stlib=['gcov'],
                      uselib_store='GCOV', mandatory=True)
            gcov_search_paths = os.environ['PATH'].split(os.pathsep)
            for gcc_path in ctx.env.CC:
                gcov_search_paths.insert(0, os.path.dirname(gcc_path))
            ctx.find_program('gcov', path_list=gcov_search_paths)
            ctx.find_program('lcov')
            ctx.find_program('genhtml')
            ctx.env.LCOV = ctx.env.LCOV + ['--gcov-tool',
                                           ctx.env.GCOV[0]]
        else:
            ctx.fatal('Coverage test is not supported on this compiler.')

    ctx.env['with_coverage'] = ctx.options.with_coverage


def options(ctx):
    """Provide the command-line options.
    """

    grp = ctx.get_option_group('configure options')
    grp.add_option('--with-coverage', action='store_true', default=False,
                   help='generate a test coverage report using lcov',
                   dest='with_coverage')

    grp = ctx.get_option_group('build and install options')

    grp.add_option('--test', type='choice',
                   choices=('none', 'build', 'run', 'changed'),
                   default='none',
                   help="whether to build and run test drivers "
                        "(none/build/run/changed) [default: %default]. "
                        "none: don't build or run tests, "
                        "build: build tests but don't run them, "
                        "run: build and run tests, "
                        "changed: run rebuilt tests only",
                   dest='test')

    grp.add_option('--test-v', type='int', default=0,
                   help='verbosity level of test output [default: %default]',
                   dest='test_v')

    grp.add_option('--test-j', type='int', default=4,
                   help='amount of parallel jobs used by the test runner '
                        '[default: %default]. '
                        'This value is independent of the number of jobs '
                        'used by waf itself.',
                   dest='test_j')

    grp.add_option('--show-test-out', action='store_true', default=False,
                   help='show output of tests even if they pass',
                   dest='show_test_out')

    grp.add_option('--test-timeout', type='int', default=200,
                   help='test driver timeout [default: %default]',
                   dest='test_timeout')

    grp.add_option('--test-junit', action='store_true', default=False,
                   help='create jUnit-style test results files for '
                        'test drivers that are executed',
                   dest='test_junit')

    grp.add_option('--coverage-out', type='str', default=None,
                   help='output directory of the test coverage report',
                   dest='coverage_out')

    grp.add_option('--valgrind', action='store_true', default=False,
                   help='use valgrind to run test drivers',
                   dest='valgrind')

    grp.add_option('--valgrind-tool', type='choice', default='memcheck',
                   choices=('memcheck', 'helgrind', 'drd'),
                   help='use valgrind tool (memchk/helgrind/drd) '
                   '[default: %default]',
                   dest='valgrind_tool')

    grp.add_option('--gtest', action='store_true', default=False,
                   help='expect gtest test drivers',
                   dest='gtest')

# -----------------------------------------------------------------------------
# Copyright 2015 Bloomberg Finance L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ----------------------------- END-OF-FILE -----------------------------------
