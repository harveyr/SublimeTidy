import sublime
import sublime_plugin
import re
import subprocess

REGION_KEY = 'sublime_tidy'

PEP8_REX = re.compile(r'\w+:(\d+):(\d+):\s(\w+)\s(.+)$', re.MULTILINE)
PYLINT_REX = re.compile(r'^(\w):\s+(\d+),\s*(\d+):\s(.+)$', re.MULTILINE)
PYFLAKES_REX = re.compile(r'\w+:(\d+):\s(.+)$', re.MULTILINE)
JSHINT_REX = re.compile(r'\w+: line (\d+), col (\d+),\s(.+)$', re.MULTILINE)


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
        results.append({
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
                pep8(self.path)
            )

    def get_issue(self, line):
        for issue in self.issues:
            if issue['line'] == line:
                return issue


issues = Issues()


class ShowTidyIssuesCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        line_no = len(
            self.view.lines(sublime.Region(0, self.view.sel()[0].begin() + 1))
        )
        str_ = lambda x: '[{}] {}'.format(x['reporter'], x['message'])
        issue_strs = [str_(i) for i in issues.issues if i['line'] == line_no]
        print('issue_strs: {0}'.format(issue_strs))

        self.view.show_popup_menu(issue_strs, None)


class TidyListener(sublime_plugin.EventListener):
    def on_post_save_async(self, view):
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
