import re
from astroid import nodes

from pylint.checkers import BaseChecker, utils
from pylint.interfaces import IRawChecker


class CheckException(BaseChecker):
    """Check syntax warning"""

    __implements__ = IRawChecker
    name = "cgi-escape-exception"
    priority = -1  # low priority
    msgs = {
        "W9991": (
            "Warning: Use html.escape, than cgi.escape [Category 2]",
            "cgi-escape-exception",
            (
                "Use html.escape, than cgi.escape"
            ),
        )
    }

    options = ()

    @utils.check_messages("cgi-escape-exception")
    def process_module(self, node: nodes.Module) -> None:
        with node.stream() as stream:
            for (lineno, line) in enumerate(stream):
                line = line.rstrip()
                if re.search(b"cgi.escape", line):
                    self.add_message("cgi-escape-exception", line=lineno + 1)


def register(linter):
    """
    This required method auto registers the checker.
    """
    linter.register_checker(CheckException(linter))
