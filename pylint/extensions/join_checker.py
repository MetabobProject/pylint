import re
from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.interfaces import IRawChecker


def check_line(line):
    """Checks the logic of list conversion to string"""
    check = re.search(b"join", line)
    line = line[check.start() + 1:]
    if re.search(b"%s.*len", line):
        return True
    return False


class JoinList(BaseChecker):
    __implements__ = IRawChecker

    name = "refactoring"
    msgs = {
        "R2999": (
            "Replace the join method arguments with list name [Category 1] ",
            "join-list",
            (
                "Refactoring the logic for converting list to string"
            ),
        )
    }
    options = ()
    priority = -1  # low priority

    def process_module(self, node: nodes.Module) -> None:
        with node.stream() as stream:
            for (line_num, line) in enumerate(stream):
                line = line.rstrip()
                if re.search(b"join", line):
                    if check_line(line[:-1]):
                        self.add_message("join-list", line=line_num + 1)


def register(linter):
    linter.register_checker(JoinList(linter))
