# Copyright (c) 2017 Christoph Landgraf. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import cui
import cui_pydevd
import functools
import itertools

from cui_pydevd import constants

def _with_session_raw(optional):
    def _with_session(fn):
        @functools.wraps(fn)
        def _fn(*args, **kwargs):
            buf = cui.current_buffer()
            session = None
            try:
                session = buf.session
            except AttributeError:
                try:
                    session = buf.thread.session
                except AttributeError:
                    pass

            if session or optional:
                return fn(session, *args, **kwargs)

            return None
        return _fn
    return _with_session


with_session = _with_session_raw(optional=False)
with_optional_session = _with_session_raw(optional=True)


class BreakpointFileHandler(cui.buffers.NodeHandler(is_expanded_=True, has_children_=True)):
    def __init__(self, session, *args, **kwargs):
        super(BreakpointFileHandler, self).__init__(session, *args, **kwargs)
        self._breakpoints = cui.get_variable(constants.ST_BREAKPOINTS)

    def matches(self, item):
        return isinstance(item, str)

    def get_children(self, item):
        return list(zip(itertools.repeat(item),
                        self._breakpoints.breakpoints(item)))

    def render(self, window, item, depth, width):
        return [item]


class BreakpointLineHandler(cui.buffers.NodeHandler(is_expanded_=True, has_children_=True)):
    def __init__(self, session, *args, **kwargs):
        super(BreakpointLineHandler, self).__init__(session, *args, **kwargs)
        self._session = session
        self._breakpoints = cui.get_variable(constants.ST_BREAKPOINTS)

    def matches(self, item):
        return isinstance(item, tuple) and type(item[1]) is int

    def get_children(self, item):
        return [] if self._session else list(self._breakpoints.sessions(item[0], item[1]).items())

    def render(self, window, item, depth, width):
        active = self._session is None or self._breakpoints.sessions(item[0], item[1])[str(self._session)]
        if self._session:
            return [{'content': '[%s] %s' % ('!' if active else ' ', str(item[1] + 1)),
                     'foreground': ('default' if active \
                                    else 'inactive')}]
        else:
            return [str(item[1] + 1)]


class BreakpointSessionHandler(cui.buffers.NodeHandler(is_expanded_=True)):
    def matches(self, item):
        return isinstance(item, tuple) and type(item[1]) is bool

    def render(self, window, item, depth, width):
        return [{'content': item[0],
                 'foreground': 'default' if item[1] else 'inactive'}]


@cui.buffers.node_handlers(BreakpointFileHandler,
                           BreakpointLineHandler,
                           BreakpointSessionHandler)
class BreakpointBuffer(cui.buffers.DefaultTreeBuffer):
    """
    Display Python breakpoints.

    Displays all breakpoints defined in cui-pydevd, as well as the
    sessions for which they are and are not active.
    If this buffer is opened in the context of a session, the
    sessions will not be displayed.
    """
    @classmethod
    def name(cls, session):
        return ("pydevd Breakpoints %s"
                % ('' if session is None else ('(%s)' % session)))

    def __init__(self, session):
        super(BreakpointBuffer, self).__init__(session)
        self._session = session
        self._breakpoints = cui.get_variable(constants.ST_BREAKPOINTS)

    def get_roots(self):
        return self._breakpoints.paths()


def py_display_all_breakpoints(session):
    cui.buffer_visible(BreakpointBuffer, None)


@with_session
def py_display_session_breakpoints(session):
    cui.buffer_visible(BreakpointBuffer, session)


class SessionBuffer(cui.buffers.ListBuffer):
    """
    Display a list of active pydevd sessions.
    """
    @classmethod
    def name(cls):
        return "pydevd Sessions"

    def on_item_selected(self):
        cui.switch_buffer(ThreadBuffer, self.selected_item())

    def on_pre_render(self):
        self._flattened = cui_pydevd.pydevd_sessions()

    def items(self):
        return self._flattened

    def render_item(self, window, item, index):
        return [str(item)]
