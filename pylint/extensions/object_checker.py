import re
from astroid import nodes

from pylint.checkers import BaseChecker, utils
from pylint.interfaces import IRawChecker


class CheckException(BaseChecker):
    """Check syntax warning"""

    __implements__ = IRawChecker
    name = "class-object-exception"
    priority = -2  # low priority
    msgs = {
        "W1871": (
            "Use obj.__class__ method, instead of type(obj) [Category 3]",
            "class-object-exception",
            (
                "Use obj.__class__ method, instead of type(obj)"
            ),
        )
    }

    options = ()

    @utils.check_messages("class-object-exception")
    def process_module(self, node: nodes.Module) -> None:
        with node.stream() as stream:
            for (lineno, line) in enumerate(stream):
                line = line.rstrip()
                if re.match(b"#" or "\\'" or '\"', line):
                    print("Comment found!")
                    break
                elif re.search(b"type\\(", line):
                    self.add_message("class-object-exception", line=lineno + 1)


def register(linter):
    """
    This required method auto registers the checker.
    """
    linter.register_checker(CheckException(linter))
