SublimeTidy
===========

Executive Summary: This is [probably] not the linter you are looking for. Check out [SublimeLinter](https://github.com/SublimeLinter/SublimeLinter).

Still reading? If you're interested in using this, let me know. It's not portable at the moment, but it could be. Definitely a WIP.

**Compelling historical context.**

This is my latest attempt at a linting tool. For some reason I like spending time on this problem. It follows:

1. my [Python command-line version](https://github.com/harveyr/lintblame),
1. my [Go command-line version](https://github.com/harveyr/golintblame), and
1. my [webapp version](https://github.com/harveyr/thunderbox).

**Why reinvent this wheel?**

1. Other linters can clutter up your editor with feedback. Particularly, for example, if you're editing a file written by someone who isn't a huge PEP8 fan. I want to make the initial feedback as minimal as possible.
1. I want to combine the results of several linters (PEP8, PyFlakes, and Pylint, etc.).
1. I want to cross-reference each issue with git/hg blaming in order to highlight which style uglies *you* have made. Policing others' coding style is not always appreciated.
1. Because.

**Epic screenshot.**

Each line with an issue gets a little dot. If you committed the line, it's a red dot. (Though the colors will vary depending on the color scheme.)

You can pull up the list of issues with a user-defined keyboard shortcut.
![screenshot](https://raw.github.com/harveyr/SublimeTidy/master/screenshot.png)


