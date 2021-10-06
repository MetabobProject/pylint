from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.interfaces import IAstroidChecker


class ModuleUpdate(BaseChecker):
    __implements__ = IAstroidChecker

    name = "module_update"
    msgs = {
        "M0004": (
            "Prefer importing %r instead of %r [Category 4]",
            "update-module",
            "Used when a module imported has a preferred replacement module.",
        )
    }
    options = ()
    priority = -2  # low priority


    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        """triggered when a from statement is seen"""
        basename = node.modname
        name = node.names
        self._check_update_module(node, basename, name)

    def _check_update_module(self, node, mod_path, name):
        if mod_path == 'logging' and name[0][0] == 'getLogger':
            args = ('logging', 'getLogger')
        """elif 'syft.messaging.plan.plan' in mod_path and \
                name[0][0] == 'Plan':
            args = ('execution', 'messaging')"""
        self.add_message(
                "update-module",
                node=node,
                args=args,
        )


def register(linter):
    linter.register_checker(ModuleUpdate(linter))
