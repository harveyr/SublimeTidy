import sublime
import sublime_plugin
import re
import subprocess
from collections import defaultdict
import os


PACKAGE_SETTINGS = sublime.load_settings('tidy.sublime-settings')

MY_BLAME_REGION_KEY = 'sublime_tidy_regions_mine'
OTHERS_BLAME_REGION_KEY = 'sublime_tidy_regions_others'
STATUS_KEY = 'sublime_tidy_status'

PEP8_REX = re.compile(r'\w+:(\d+):(\d+):\s(\w+)\s(.+)$', re.MULTILINE)
PYLINT_REX = re.compile(r'^(\w):\s+(\d+),\s*(\d+):\s(.+)$', re.MULTILINE)
PYFLAKES_REX = re.compile(r'\w+:(\d+):\s(.+)$', re.MULTILINE)
JSHINT_REX = re.compile(r'\w+: line (\d+), col (\d+),\s(.+)$', re.MULTILINE)
BLAME_NAME_REX = re.compile(r'\(([\w\s]+)\d{4}')

MY_NAME_REX = re.compile(PACKAGE_SETTINGS.get('my_name_rex'), re.I)


# TODO: Move executable paths into settings
# TODO: Use scope instead of extension to determine what to run?

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
        location = '{}:{}'.format(self.line, self.column)
        return '{:<10} {:<5} {}'.format(
            reporter,
            location,
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


def git_name():
    return subprocess.check_output(["git", "config", "user.name"]).strip()


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

    def __init__(self):
        self.path = None
        self.issues = []

    def set_path(self, path):
        self.path = path
        self.update_issues()
        self.blame_by_line = blame(path)

    def update_issues(self):
        if not self.path:
            return
        self.issues = []

        root, ext = os.path.splitext(self.path)
        print('ext: {0}'.format(ext))
        if ext == '.py':
            self.issues = (
                pylint(self.path) +
                pep8(self.path) +
                pyflakes(self.path)
            )
        elif ext in ['.js', '.json', '.sublime-settings']:
            self.issues = jshint(self.path)

    def issues_by_line(self):
        d = defaultdict(list)
        for issue in self.issues:
            d[issue.line].append(issue)
        return d

    def blame(self, issue):
        return self.blame_by_line.get(issue.line, None)

issues = Issues()


class ShowTidyIssuesCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        line_no = len(
            self.view.lines(sublime.Region(0, self.view.sel()[0].begin() + 1))
        )
        issue_strs = [str(i) for i in issues.issues if i.line == line_no]
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
        issues_by_line = issues.issues_by_line()
        issues_line_nos = sorted(issues_by_line.keys())
        remainder_line_nos = [l for l in issues_line_nos if l > current_line]
        try:
            if remainder_line_nos:
                target_line = remainder_line_nos[0]
            else:
                target_line = issues_line_nos[0]
        except IndexError as e:
            print(
                'Failed to find target_line {} in:\n{}\n{}'.format(
                    0,
                    remainder_line_nos,
                    issues_line_nos
                )
            )
            raise e



        line_regions = self.view.lines(sublime.Region(0, self.view.size()))
        line_region = line_regions[target_line - 1]
        self.view.show_at_center(line_region.begin())
        sel = self.view.sel()
        sel.clear()
        sel.add(line_region)
        self.view.run_command('show_tidy_issues')


class TidyListener(sublime_plugin.EventListener):
    def on_post_save_async(self, view):
        view.set_status(STATUS_KEY, 'Evaluating tidiness...')

        view.erase_regions(MY_BLAME_REGION_KEY)
        view.erase_regions(OTHERS_BLAME_REGION_KEY)
        issues.set_path(view.file_name())

        lines = view.lines(sublime.Region(0, view.size()))

        my_regions = []
        others_regions = []
        for issue in issues.issues:
            line_region = lines[issue.line - 1]
            issue_region = sublime.Region(
                line_region.begin(),
                line_region.begin()
            )
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
        msg = '{} untidies'.format(count)
        if count > 0:
            msg = msg.upper()
        view.set_status(STATUS_KEY, msg)    
