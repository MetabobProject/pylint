# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/PyCQA/pylint/blob/main/LICENSE

import sys
from io import TextIOWrapper
from typing import TYPE_CHECKING, Any, List, Optional, TextIO, Tuple, Union

from astroid import nodes

from pylint.constants import (
    _SCOPE_EXEMPT,
    MAIN_CHECKER_NAME,
    MSG_STATE_CONFIDENCE,
    MSG_STATE_SCOPE_CONFIG,
    MSG_STATE_SCOPE_MODULE,
    MSG_TYPES,
    MSG_TYPES_LONG,
    MSG_TYPES_STATUS,
    WarningScope,
)
from pylint.exceptions import (
    InvalidMessageError,
    NoLineSuppliedError,
    UnknownMessageError,
)
from pylint.interfaces import UNDEFINED, Confidence
from pylint.message.message import Message
from pylint.utils import get_module_and_frameid, get_rst_section, get_rst_title

if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter
    from pylint.message import MessageDefinition


class MessagesHandlerMixIn:
    """A mix-in class containing all the messages related methods for the main lint class."""

    __by_id_managed_msgs: List[Tuple[str, str, str, int, bool]] = []

    def __init__(self):
        self._msgs_state = {}
        self.msg_status = 0

    def _checker_messages(self, checker):
        for known_checker in self._checkers[checker.lower()]:
            yield from known_checker.msgs

    @classmethod
    def clear_by_id_managed_msgs(cls):
        cls.__by_id_managed_msgs.clear()

    @classmethod
    def get_by_id_managed_msgs(cls):
        return cls.__by_id_managed_msgs

    def _register_by_id_managed_msg(self, msgid_or_symbol: str, line, is_disabled=True):
        """If the msgid is a numeric one, then register it to inform the user
        it could furnish instead a symbolic msgid."""
        if msgid_or_symbol[1:].isdigit():
            try:
                symbol = self.msgs_store.message_id_store.get_symbol(msgid=msgid_or_symbol)  # type: ignore
            except UnknownMessageError:
                return
            managed = (self.current_name, msgid_or_symbol, symbol, line, is_disabled)  # type: ignore
            MessagesHandlerMixIn.__by_id_managed_msgs.append(managed)

    def disable(self, msgid, scope="package", line=None, ignore_unknown=False):
        self._set_msg_status(
            msgid, enable=False, scope=scope, line=line, ignore_unknown=ignore_unknown
        )
        self._register_by_id_managed_msg(msgid, line)

    def disable_next(
        self,
        msgid: str,
        scope: str = "package",
        line: Union[bool, int] = None,
        ignore_unknown: bool = False,
    ):
        if not line:
            raise NoLineSuppliedError
        self._set_msg_status(
            msgid,
            enable=False,
            scope=scope,
            line=line + 1,
            ignore_unknown=ignore_unknown,
        )
        self._register_by_id_managed_msg(msgid, line + 1)

    def enable(self, msgid, scope="package", line=None, ignore_unknown=False):
        self._set_msg_status(
            msgid, enable=True, scope=scope, line=line, ignore_unknown=ignore_unknown
        )
        self._register_by_id_managed_msg(msgid, line, is_disabled=False)

    def _set_msg_status(
        self, msgid, enable, scope="package", line=None, ignore_unknown=False
    ):
        assert scope in ("package", "module")
        if msgid == "all":
            for _msgid in MSG_TYPES:
                self._set_msg_status(_msgid, enable, scope, line, ignore_unknown)
            return

        # msgid is a category?
        category_id = msgid.upper()
        if category_id not in MSG_TYPES:
            category_id = MSG_TYPES_LONG.get(category_id)
        if category_id is not None:
            for _msgid in self.msgs_store._msgs_by_category.get(category_id):
                self._set_msg_status(_msgid, enable, scope, line)
            return

        # msgid is a checker name?
        if msgid.lower() in self._checkers:
            for checker in self._checkers[msgid.lower()]:
                for _msgid in checker.msgs:
                    self._set_msg_status(_msgid, enable, scope, line)
            return

        # msgid is report id?
        if msgid.lower().startswith("rp"):
            if enable:
                self.enable_report(msgid)
            else:
                self.disable_report(msgid)
            return

        try:
            # msgid is a symbolic or numeric msgid.
            message_definitions = self.msgs_store.get_message_definitions(msgid)
        except UnknownMessageError:
            if ignore_unknown:
                return
            raise
        for message_definition in message_definitions:
            self._set_one_msg_status(scope, message_definition, line, enable)

    def _set_one_msg_status(self, scope, msg, line, enable):
        if scope == "module":
            self.file_state.set_msg_status(msg, line, enable)
            if not enable and msg.symbol != "locally-disabled":
                self.add_message(
                    "locally-disabled", line=line, args=(msg.symbol, msg.msgid)
                )
        else:
            msgs = self._msgs_state
            msgs[msg.msgid] = enable
            # sync configuration object
            self.config.enable = [
                self._message_symbol(mid) for mid, val in sorted(msgs.items()) if val
            ]
            self.config.disable = [
                self._message_symbol(mid)
                for mid, val in sorted(msgs.items())
                if not val
            ]

    def _message_symbol(self, msgid):
        """Get the message symbol of the given message id

        Return the original message id if the message does not
        exist.
        """
        try:
            return [md.symbol for md in self.msgs_store.get_message_definitions(msgid)]
        except UnknownMessageError:
            return msgid

    def get_message_state_scope(self, msgid, line=None, confidence=UNDEFINED):
        """Returns the scope at which a message was enabled/disabled."""
        if self.config.confidence and confidence.name not in self.config.confidence:
            return MSG_STATE_CONFIDENCE
        try:
            if line in self.file_state._module_msgs_state[msgid]:
                return MSG_STATE_SCOPE_MODULE
        except (KeyError, TypeError):
            return MSG_STATE_SCOPE_CONFIG
        return None

    def is_message_enabled(self, msg_descr, line=None, confidence=None):
        """return true if the message associated to the given message id is
        enabled

        msgid may be either a numeric or symbolic message id.
        """
        if self.config.confidence and confidence:
            if confidence.name not in self.config.confidence:
                return False
        try:
            message_definitions = self.msgs_store.get_message_definitions(msg_descr)
            msgids = [md.msgid for md in message_definitions]
        except UnknownMessageError:
            # The linter checks for messages that are not registered
            # due to version mismatch, just treat them as message IDs
            # for now.
            msgids = [msg_descr]
        for msgid in msgids:
            if self.is_one_message_enabled(msgid, line):
                return True
        return False

    def is_one_message_enabled(self, msgid, line):
        if line is None:
            return self._msgs_state.get(msgid, True)
        try:
            return self.file_state._module_msgs_state[msgid][line]
        except KeyError:
            # Check if the message's line is after the maximum line existing in ast tree.
            # This line won't appear in the ast tree and won't be referred in
            # self.file_state._module_msgs_state
            # This happens for example with a commented line at the end of a module.
            max_line_number = self.file_state.get_effective_max_line_number()
            if max_line_number and line > max_line_number:
                fallback = True
                lines = self.file_state._raw_module_msgs_state.get(msgid, {})

                # Doesn't consider scopes, as a disable can be in a different scope
                # than that of the current line.
                closest_lines = reversed(
                    [
                        (message_line, enable)
                        for message_line, enable in lines.items()
                        if message_line <= line
                    ]
                )
                last_line, is_enabled = next(closest_lines, (None, None))
                if last_line is not None:
                    fallback = is_enabled

                return self._msgs_state.get(msgid, fallback)
            return self._msgs_state.get(msgid, True)

    def add_message(  # type: ignore # MessagesHandlerMixIn is always mixed with PyLinter
        self: "PyLinter",
        msgid: str,
        line: Optional[int] = None,
        node: Optional[nodes.NodeNG] = None,
        args: Any = None,
        confidence: Optional[Confidence] = None,
        col_offset: Optional[int] = None,
    ) -> None:
        """Adds a message given by ID or name.

        If provided, the message string is expanded using args.

        AST checkers must provide the node argument (but may optionally
        provide line if the line number is different), raw and token checkers
        must provide the line argument.
        """
        if confidence is None:
            confidence = UNDEFINED
        message_definitions = self.msgs_store.get_message_definitions(msgid)
        for message_definition in message_definitions:
            self.add_one_message(
                message_definition, line, node, args, confidence, col_offset
            )

    @staticmethod
    def check_message_definition(message_definition, line, node):
        if message_definition.msgid[0] not in _SCOPE_EXEMPT:
            # Fatal messages and reports are special, the node/scope distinction
            # does not apply to them.
            if message_definition.scope == WarningScope.LINE:
                if line is None:
                    raise InvalidMessageError(
                        f"Message {message_definition.msgid} must provide line, got None"
                    )
                if node is not None:
                    raise InvalidMessageError(
                        f"Message {message_definition.msgid} must only provide line, "
                        f"got line={line}, node={node}"
                    )
            elif message_definition.scope == WarningScope.NODE:
                # Node-based warnings may provide an override line.
                if node is None:
                    raise InvalidMessageError(
                        f"Message {message_definition.msgid} must provide Node, got None"
                    )

    def add_one_message(  # type: ignore # MessagesHandlerMixIn is always mixed with PyLinter
        self: "PyLinter",
        message_definition: "MessageDefinition",
        line: Optional[int],
        node: Optional[nodes.NodeNG],
        args: Any,
        confidence: Optional[Confidence],
        col_offset: Optional[int],
    ) -> None:
        self.check_message_definition(message_definition, line, node)
        if line is None and node is not None:
            line = node.fromlineno
        if col_offset is None and hasattr(node, "col_offset"):
            col_offset = node.col_offset  # type: ignore

        # should this message be displayed
        if not self.is_message_enabled(message_definition.msgid, line, confidence):
            self.file_state.handle_ignored_message(
                self.get_message_state_scope(
                    message_definition.msgid, line, confidence
                ),
                message_definition.msgid,
                line,
                node,
                args,
                confidence,
            )
            return
        # update stats
        msg_cat = MSG_TYPES[message_definition.msgid[0]]
        self.msg_status |= MSG_TYPES_STATUS[message_definition.msgid[0]]
        if self.stats is None:
            # pylint: disable=fixme
            # TODO self.stats should make sense,
            # class should make sense as soon as instantiated
            # This is not true for Linter and Reporter at least
            # pylint: enable=fixme
            self.stats = {
                msg_cat: 0,
                "by_module": {self.current_name: {msg_cat: 0}},
                "by_msg": {},
            }
        self.stats[msg_cat] += 1  # type: ignore
        self.stats["by_module"][self.current_name][msg_cat] += 1  # type: ignore
        try:
            self.stats["by_msg"][message_definition.symbol] += 1  # type: ignore
        except KeyError:
            self.stats["by_msg"][message_definition.symbol] = 1  # type: ignore
        # Interpolate arguments into message string
        msg = message_definition.msg
        if args:
            msg %= args
        # get module and object
        if node is None:
            module, obj = self.current_name, ""
            abspath = self.current_file
        else:
            module, obj = get_module_and_frameid(node)
            abspath = node.root().file
        if abspath is not None:
            path = abspath.replace(self.reporter.path_strip_prefix, "", 1)
        else:
            path = "configuration"
        # add the message
        self.reporter.handle_message(
            Message(
                message_definition.msgid,
                message_definition.symbol,
                (abspath, path, module, obj, line or 1, col_offset or 0),
                msg,
                confidence,
            )
        )

    def _get_checkers_infos(self):
        by_checker = {}
        for checker in self.get_checkers():
            name = checker.name
            if name != "master":
                try:
                    by_checker[name]["checker"] = checker
                    by_checker[name]["options"] += checker.options_and_values()
                    by_checker[name]["msgs"].update(checker.msgs)
                    by_checker[name]["reports"] += checker.reports
                except KeyError:
                    by_checker[name] = {
                        "checker": checker,
                        "options": list(checker.options_and_values()),
                        "msgs": dict(checker.msgs),
                        "reports": list(checker.reports),
                    }
        return by_checker

    def get_checkers_documentation(self):
        result = get_rst_title("Pylint global options and switches", "-")
        result += """
Pylint provides global options and switches.

"""
        for checker in self.get_checkers():
            name = checker.name
            if name == MAIN_CHECKER_NAME:
                if checker.options:
                    for section, options in checker.options_by_section():
                        if section is None:
                            title = "General options"
                        else:
                            title = f"{section.capitalize()} options"
                        result += get_rst_title(title, "~")
                        result += f"{get_rst_section(None, options)}\n"
        result += get_rst_title("Pylint checkers' options and switches", "-")
        result += """\

Pylint checkers can provide three set of features:

* options that control their execution,
* messages that they can raise,
* reports that they can generate.

Below is a list of all checkers and their features.

"""
        by_checker = self._get_checkers_infos()
        for checker in sorted(by_checker):
            information = by_checker[checker]
            checker = information["checker"]
            del information["checker"]
            result += checker.get_full_documentation(**information)
        return result

    def print_full_documentation(self, stream: TextIO = sys.stdout) -> None:
        """output a full documentation in ReST format"""
        print(self.get_checkers_documentation()[:-1], file=stream)

    @staticmethod
    def _print_checker_doc(information, stream: TextIOWrapper) -> None:
        """Helper method used by doc/exts/pylint_extensions.py."""
        checker = information["checker"]
        del information["checker"]
        print(checker.get_full_documentation(**information)[:-1], file=stream)
