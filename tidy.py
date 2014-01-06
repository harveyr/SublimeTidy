import sublime
import sublime_plugin
import re
import subprocess
from collections import defaultdict
import os
import threading
import tempfile
import queue


PACKAGE_SETTINGS = sublime.load_settings('tidy.sublime-settings')

MY_BLAME_REGION_KEY = 'sublime_tidy_regions_mine'
OTHERS_BLAME_REGION_KEY = 'sublime_tidy_regions_others'
STATUS_KEY = 'sublime_tidy_status'

PEP8_REX = re.compile(r'\w+:(\d+):(\d+):\s(\w+)\s(.+)$', re.MULTILINE)
PYLINT_REX = re.compile(r'^(\w):\s+(\d+),\s*(\d+):\s(.+)$', re.MULTILINE)
PYFLAKES_REX = re.compile(r'\w+:(\d+):\s(.+)$', re.MULTILINE)
JSHINT_REX = re.compile(r'\w+: line (\d+), col (\d+),\s(.+)$', re.MULTILINE)
BLAME_NAME_REX = re.compile(r'\(([\w\s]+)\d{4}')

MY_NAME_REX = re.compile(
    r'{}|Not Committed Yet'.format(PACKAGE_SETTINGS.get('my_name_rex')),
    re.I
)

# TODO: Provide report of all modified files
# TODO: Intelligently handle executable paths
# TODO: Decide what to do about changing views
# TODO: If panel is up during update, update panel contents


class Issue(object):
    """Represents a single linter issue."""
    def __init__(self, line, column, code, message, reporter):
        self.line = int(line)
        if column:
            self.column = int(column)
        else:
            self.column = column
        self.code = code
        self.message = message
        self.reporter = reporter
        self.region = None

    def __str__(self):
        reporter = '[{}]'.format(self.reporter)
        location = '{}:{}'.format(self.line, self.column)

        return '{:<5} {} {}'.format(
            location,
            reporter,
            self.message
        )

    def blamed_str(self, blame_name):
        reporter = '[{}]'.format(self.reporter)
        location = '{}:{}'.format(self.line, self.column)
        blame_str = '[{}]'.format(blame_name)

        return '{:<5} {:<10} {} {}'.format(
            location,
            reporter,
            blame_str,
            self.message
        )

    def set_region(self, region):
        self.region = region


def run(cmd):
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True
    )
    out, err = proc.communicate()
    return out.decode('utf-8') + err.decode('utf-8')


def pylint(path):
    """Pylint issues."""
    cmd = "/usr/local/bin/pylint --output-format=text '{}'".format(path)
    output = run(cmd)
    hits = PYLINT_REX.findall(output)
    results = []
    for hit in hits:
        results.append(
            Issue(
                line=hit[1],
                column=hit[2],
                message=hit[3],
                code=hit[0],
                reporter='Pylint'
            )
        )
    return results


def pep8(path):
    """PEP8 issues."""
    output = run("/usr/local/bin/pep8 '{}'".format(path))
    hits = PEP8_REX.findall(output)
    results = []
    for hit in hits:
        results.append(
            Issue(
                line=hit[0],
                column=hit[1],
                code=hit[2],
                message=hit[3],
                reporter='PEP8'
            )
        )
    return results


def pyflakes(path):
    """PyFlakes issues."""
    cmd = "/usr/local/bin/pyflakes '{}'".format(path)
    output = run(cmd)
    hits = PYFLAKES_REX.findall(output)
    results = []
    for hit in hits:
        results.append(
            Issue(
                line=hit[0],
                column='',
                code='',
                message=hit[1],
                reporter='Pyflakes'
            )
        )
    return results


def jshint(path):
    """JsHint issues."""
    cmd = 'jshint {}'.format(path)
    output = run(cmd)
    hits = JSHINT_REX.findall(output)
    results = []
    for hit in hits:
        results.append(
            Issue(
                line=hit[0],
                column=hit[1],
                code='',
                message=hit[2],
                reporter='JSHint'
            )
        )
    return results


def diff_files():
    output = (
        subprocess.check_output(['git', 'diff', '--name-only', 'master..']) +
        subprocess.check_output(['git', 'diff', '--name-only'])
    )
    return [i.decode('utf-8') for i in output.splitlines() if i]


def git_name():
    return subprocess.check_output(['git', 'config', 'user.name']).strip()


def blame(path):
    working_dir = os.path.split(path)[0]
    proc = subprocess.Popen(
        ['git', 'blame', path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=working_dir
    )
    out, err = proc.communicate()
    blame_lines = (out + err).splitlines()
    result = {}
    for i, line in enumerate(blame_lines):
        match = BLAME_NAME_REX.search(line.decode('utf-8'))
        if match:
            result[i + 1] = match.group(1).strip()
        else:
            result[i + 1] = None
    return result


class Issues(object):
    """Collection that holds all lint issues."""
    def __init__(self):
        self.path = None
        self.issues = []
        self.set_out_of_date(True)
        self.queue = queue.Queue()

    def set_path(self, path, lint_override_target=None):
        self.update_issues(lint_override_target or path)
        self.blame_by_line = blame(path)

    def _append_issues(self, issues_func, path):
        self.issues += issues_func(path)

    def update_issues(self, path):
        """Run linters and save results."""
        self.issues = []

        root, ext = os.path.splitext(path)
        if ext == '.py':
            issue_funcs = [pep8, pylint, pyflakes]
        elif ext in ['.js', '.json', '.sublime-settings']:
            issue_funcs = [jshint]

        threads = []
        for func in issue_funcs:
            t = threading.Thread(
                target=self._append_issues,
                args=[func, path]
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join(10)

        self.set_out_of_date(False)

    def issues_by_line(self):
        d = defaultdict(list)
        for issue in self.issues:
            d[issue.line].append(issue)
        return d

    def issues_by_region(self):
        d = defaultdict(list)
        for issue in self.issues:
            d[issue.region].append(issue)
        return d

    def blame(self, issue):
        return self.blame_by_line.get(issue.line, None)

    @property
    def out_of_date(self):
        return self._out_of_date

    def set_out_of_date(self, out_of_date=True):
        self._out_of_date = out_of_date

issues = Issues()


class ViewUpdateManager(object):
    def __init__(self):
        self.run_thread = None
        self.delayed_run_thread = None
        self.delayed_run_file = None

    @property
    def is_running(self):
        try:
            return self.run_thread.is_alive()
        except AttributeError:
            return False

    def cancel_delayed_run_thread(self):
        """Returns True if successful cancellation before thread is alive."""
        if self.delayed_run_thread:
            self.delayed_run_thread.cancel()

    def run_delayed(
        self,
        view,
        use_buffer=False,
        force=False
    ):
        self.cancel_delayed_run_thread()
        self.delayed_run_thread = threading.Timer(
            4,
            self._run_and_apply_tidy,
            kwargs={
                'view': view,
                'use_buffer': use_buffer,
                'force': force,
            }
        )
        self.delayed_run_thread.start()
        self.delayed_run_file = view.file_name()
        view.set_status(STATUS_KEY, 'Tidy: Updating shortly...')

    def join(self):
        try:
            if self.delayed_run_thread.is_alive():
                self.delayed_run_thread.cancel()

            self.run_thread.join(3.0)
            if self.run_thread.is_alive():
                print('join timeout')
                return False
        except AttributeError:
            pass

        return True

    def run_now(self, view):
        if self.is_running:
            print('Tidy already running.')
            return

        self.cancel_delayed_run_thread()

        self.run_thread = threading.Thread(
            target=self._run_and_apply_tidy,
            kwargs={
                'view': view,
                'force': True,
            }
        )
        self.run_thread.start()

    def _run_and_apply_tidy(self, view, use_buffer=False, force=False):
        print('Tidy: Attempting update...')

        if not view.is_dirty() and not force:
            print('Tidy: Clean and unforced. Aborting.')
            self.clear_view(view)
            return

        current_file = view.file_name()
        if self.delayed_run_file and current_file != self.delayed_run_file:
            print(
                (
                    'Tidy: View file ({}) does not match current '
                    'delayed_run_file ({})'
                ).format(current_file, self.delayed_run_file)
            )
            self.clear_view(view)
            return

        self.clear_view(view)
        view.set_status(STATUS_KEY, 'Tidy: Evaluating...')

        if not current_file:
            return

        if use_buffer:
            root, ext = os.path.splitext(current_file)
            tf = tempfile.NamedTemporaryFile(mode='w', suffix=ext)
            text = view.substr(sublime.Region(0, view.size()))
            tf.write(text)
            issues.set_path(current_file, lint_override_target=tf.name)
            tf.close()
        else:
            issues.set_path(current_file)

        self._update_view(view)

    def _update_view(self, view):
        lines = view.lines(sublime.Region(0, view.size()))

        my_regions = []
        others_regions = []
        for issue in issues.issues:
            line_region = lines[issue.line - 1]
            issue_region = sublime.Region(
                line_region.begin(),
                line_region.begin()
            )
            issue.set_region(issue_region)
            if MY_NAME_REX.search(issues.blame(issue)):
                my_regions.append(issue_region)
            else:
                others_regions.append(issue_region)

        view.add_regions(
            MY_BLAME_REGION_KEY,
            my_regions,
            'keyword',
            'dot'
        )
        view.add_regions(
            OTHERS_BLAME_REGION_KEY,
            others_regions,
            'string',
            'dot'
        )

        count = len(issues.issues)
        if count:
            msg = 'Untidy ({})'.format(count)
        else:
            msg = 'Tidy!'
        view.set_status(STATUS_KEY, msg)
        print('Tidy: Finished update.')

    def clear_view(self, view):
        view.erase_regions(MY_BLAME_REGION_KEY)
        view.erase_regions(OTHERS_BLAME_REGION_KEY)
        view.erase_status(STATUS_KEY)


update_manager = ViewUpdateManager()


class ShowTidyIssuesCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        line_regions = self.view.lines(
            sublime.Region(0, self.view.sel()[0].begin() + 1)
        )
        line_no = len(line_regions)
        issue_strs = [
            i.blamed_str(issues.blame(i)) for i in issues.issues
            if i.line == line_no
        ]

        w = sublime.active_window()
        panel = w.create_output_panel('tidy_issues_panel')
        panel.replace(
            edit,
            sublime.Region(0, panel.size()),
            '\n'.join(issue_strs)
        )
        w.run_command('show_panel', {'panel': 'output.tidy_issues_panel'})

        sel = self.view.sel()
        sel.clear()
        sel.add(line_regions[-1])


class JumpToNextUntidyCommand(sublime_plugin.TextCommand):
    # TODO: Continue to figure out when we need to force an update here
    def run(self, edit):
        if not update_manager.join():
            return

        if not issues.issues:
            return

        line_regions = self.view.lines(sublime.Region(0, self.view.size()))
        if not line_regions:
            # This seems to happen when we're in the quick panel
            return

        current_line = len(
            self.view.lines(sublime.Region(0, self.view.sel()[0].begin() + 1))
        )
        issues_by_line = issues.issues_by_line()
        issues_line_nos = sorted(issues_by_line.keys())
        remainder_line_nos = [l for l in issues_line_nos if l > current_line]

        if remainder_line_nos:
            target_line = remainder_line_nos[0]
        else:
            target_line = issues_line_nos[0]

        line_region = line_regions[target_line - 1]
        self.view.show_at_center(line_region.begin())
        sel = self.view.sel()
        sel.clear()
        sel.add(line_region)
        self.view.run_command('show_tidy_issues')


class RunTidyDiffCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        print('diff_files(): {0}'.format(diff_files()))


class RunTidyCommand(sublime_plugin.TextCommand):
    """Run all linters and apply results."""
    def run(self, edit):
        update_manager.run_now(self.view)


class TidyListener(sublime_plugin.EventListener):
    """Determines when to update/clear results."""
    def on_post_save_async(self, view):
        update_manager.run_now(view)

    def on_load_async(self, view):
        update_manager.run_now(view)

    def on_modified_async(self, view):
        update_manager.run_delayed(view, use_buffer=True)

    def on_activated_async(self, view):
        update_manager.run_delayed(view)
