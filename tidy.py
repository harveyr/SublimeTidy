import sublime
import sublime_plugin
import re
import subprocess
from collections import defaultdict

REGION_KEY = 'sublime_tidy_regions'
STATUS_KEY = 'sublime_tidy_status'

PEP8_REX = re.compile(r'\w+:(\d+):(\d+):\s(\w+)\s(.+)$', re.MULTILINE)
PYLINT_REX = re.compile(r'^(\w):\s+(\d+),\s*(\d+):\s(.+)$', re.MULTILINE)
PYFLAKES_REX = re.compile(r'\w+:(\d+):\s(.+)$', re.MULTILINE)
JSHINT_REX = re.compile(r'\w+: line (\d+), col (\d+),\s(.+)$', re.MULTILINE)

# TODO: Add blaming

class Issue(object):
    def __init__(self, line, column, code, message, reporter):
        self.line = int(line)
        if column:
            self.column = int(column)
        else:
            self.column = column
        self.code = code
        self.message = message
        self.reporter = reporter

    def __str__(self):
        reporter = '[{}]'.format(self.reporter)
        return '{:<10} {}:{} {}'.format(
            reporter,
            self.line,
            self.column,
            self.message
        )


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
    # TODO: Find pylint path properly
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
            'code': hit[0],
            'line': int(hit[1]),
            'column': int(hit[2]),
            'message': hit[3],
            'reporter': 'Pylint',
        })
    return results


def pep8(path):
    """Returns pep8 results."""
    output = run("/usr/local/bin/pep8 '{}'".format(path))
    hits = PEP8_REX.findall(output)
    results = []
    for hit in hits:
        results.append({
            'line': int(hit[0]),
            'column': int(hit[1]),
            'code': hit[2],
            'message': hit[3],
            'reporter': 'PEP8',
        })
    return results


def pyflakes(path):
    output = run('/usr/local/bin/pyflakes {}'.format(path))
    hits = PYFLAKES_REX.findall(output)
    results = []
    for hit in hits:
        results.append({
            'line': hit[0],
            'column': '',
            'code': '',
            'message': hit[1],
            'reporter': 'Pyflakes'
        })
    return results


class Issues(object):

    def __init__(self):
        self.path = None
        self.issues = []

    def set_path(self, path):
        self.path = path
        self.update_issues()

    def update_issues(self):
        if not self.path:
            return
        self.issues = []

        if self.path.endswith('.py'):
            self.issues = (
                pylint(self.path) +
                pep8(self.path) +
                pyflakes(self.path)
            )

    def get_issue(self, line):
        for issue in self.issues:
            if issue['line'] == line:
                return issue

    @property
    def issues_by_line(self):
        d = defaultdict(list)
        for issue in self.issues:
            d[issue['line']].append(issue)
        return d


issues = Issues()


class ShowTidyIssuesOLDCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        line_no = len(
            self.view.lines(sublime.Region(0, self.view.sel()[0].begin() + 1))
        )
        str_ = lambda x: '[{}] {}'.format(x['reporter'], x['message'])
        issue_strs = [str_(i) for i in issues.issues if i['line'] == line_no]
        self.view.show_popup_menu(issue_strs, None)


class ShowTidyIssuesCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        line_no = len(
            self.view.lines(sublime.Region(0, self.view.sel()[0].begin() + 1))
        )
        issue_strs = [str_(i) for i in issues.issues if i['line'] == line_no]
        w = sublime.active_window()
        panel = w.create_output_panel('tidy_issues_panel')
        panel.replace(
            edit,
            sublime.Region(0, panel.size()),
            '\n'.join(issue_strs)
        )
        w.run_command('show_panel', {'panel': 'output.tidy_issues_panel'})


class JumpToNextUntidyCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        current_line = len(
            self.view.lines(sublime.Region(0, self.view.sel()[0].begin() + 1))
        )
        issues_by_line = issues.issues_by_line
        issues_line_nos = sorted(issues_by_line.keys())
        remainder_line_nos = [l for l in issues_line_nos if l > current_line]
        if remainder_line_nos:
            target_line = remainder_line_nos[0]
        else:
            target_line = issues_line_nos[0]

        line_regions = self.view.lines(sublime.Region(0, self.view.size()))
        line_region = line_regions[target_line - 1]
        self.view.show_at_center(line_region.begin())
        sel = self.view.sel()
        sel.clear()
        sel.add(line_region)
        self.view.run_command('show_tidy_issues')


class TidyListener(sublime_plugin.EventListener):

    def _apply(self, view):
        view.erase_regions(REGION_KEY)
        issues.set_path(view.file_name())

        lines = view.lines(sublime.Region(0, view.size()))

        regions = []
        for issue in issues.issues:
            line_region = lines[issue['line'] - 1]
            regions.append(
                sublime.Region(line_region.begin(), line_region.begin())
            )

        view.add_regions(
            REGION_KEY,
            regions,
            'string',
            'dot'
        )

        msg = '{} untidies'.format(len(regions))
        if len(regions) > 0:
            msg = msg.upper()
        view.set_status(STATUS_KEY, msg)
        
    def on_post_save_async(self, view):
        self._apply(view)
