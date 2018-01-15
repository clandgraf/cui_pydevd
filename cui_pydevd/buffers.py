# Copyright (c) 2017 Christoph Landgraf. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import cui
import cui.keymap
import cui_pydevd
import cui_source
import functools
import itertools

from cui_pydevd import constants
from cui.util import truncate_left


def with_session(fn):
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

        if session:
            return fn(session, *args, **kwargs)

        return None
    return _fn


def with_thread(fn):
    @functools.wraps(fn)
    def _fn(*args, **kwargs):
        thread = cui.current_buffer().thread
        if thread.state == constants.THREAD_STATE_SUSPENDED:
            return fn(thread, *args, **kwargs)
        else:
            cui.message('Thread %s must be suspended.' % thread.name)
    return _fn


def with_frame(fn):
    @functools.wraps(fn)
    def _fn(*args, **kwargs):
        frame = cui.current_buffer().selected_frame()
        if frame:
            return fn(frame.thread, frame, *args, **kwargs)
    return _fn


@with_session
def py_display_session_breakpoints(session):
    cui.buffer_visible(BreakpointBuffer, session)


@with_thread
def py_step_into(thread):
    """Step into next expression in current thread."""
    thread.step_into()


@with_thread
def py_step_over(thread):
    """Step over next expression in current thread."""
    thread.step_over()


@with_thread
def py_step_return(thread):
    """Execute until function returns."""
    thread.step_return()


@with_thread
def py_resume(thread):
    """Continue execution until next breakpoint is hit."""
    thread.resume()


@with_frame
def py_open_eval(thread, frame):
    """Open a buffer to evaluate expressions in thread."""
    cui.exec_in_buffer_visible(lambda b: b.set_frame(frame),
                               EvalBuffer, thread,
                               to_window=True)


class ThreadBufferKeymap(cui.keymap.WithKeymap):
    __keymap__ = {
        '<f5>': py_step_into,
        '<f6>': py_step_over,
        '<f7>': py_step_return,
        '<f8>': py_resume,
        'C-x b': py_display_session_breakpoints
    }

class ThreadBufferMixin(ThreadBufferKeymap):
    @classmethod
    def name(cls, thread):
        return ('%s (%s:%s/%s)'
                % (cls.__buffer_name__,
                   thread.session.address[0],
                   thread.session.address[1],
                   thread.id))

    @property
    def thread(self):
        return self._thread

class EvalBuffer(ThreadBufferMixin, cui.buffers.ConsoleBuffer):
    """Evaluate expressions in the current frame."""

    __buffer_name__ = 'Eval'

    def __init__(self, thread):
        super(EvalBuffer, self).__init__(thread)
        self._thread = thread
        self._frame = None

    def set_frame(self, frame):
        self._frame = frame

    def on_send_current_buffer(self, b):
        self._thread.eval(self._frame, b)


class FrameBuffer(ThreadBufferMixin, cui.buffers.TreeBuffer):
    """Display frame contents."""

    __buffer_name__ = 'Frame'

    def __init__(self, thread):
        super(FrameBuffer, self).__init__(thread, show_handles=True)
        self._thread = thread
        self._frame = None

    def set_frame(self, frame):
        self._frame = frame

    def get_roots(self):
        return self._frame.variables if self._frame and self._frame.variables else []

    def is_expanded(self, item):
        return item['expanded']

    def set_expanded(self, item, expanded):
        item['expanded'] = expanded

    def has_children(self, item):
        return item['has_children']

    def fetch_children(self, item):
        self._frame.request_variable(item)

    def get_children(self, item):
        return item['variables']

    def render_node(self, window, item, depth, width):
        return ['%s = {%s} %s' % (item['name'],
                                  item['vtype'],
                                  item['value'])]


class CodeBuffer(ThreadBufferMixin, cui_source.BaseFileBuffer):
    """
    Display the source of the file being currently debugged.
    """

    __buffer_name__ = 'Code'
    __keymap__ = {
        'C-b':  lambda: cui.current_buffer().center_break()
    }

    def __init__(self, thread):
        super(CodeBuffer, self).__init__(thread)
        self._thread = thread
        self._line = None

    def center_break(self):
        if self._line is not None:
            self.set_variable(['win/buf', 'selected-item'], self._line - 1)
            self.recenter()

    def set_file(self, file_path=None, line=None):
        if file_path:
            super(CodeBuffer, self).set_file(file_path)
            self._line = line
        else:
            self._line = None
        self.center_break()

    def hide_selection(self):
        return self._line == self.get_variable(['win/buf', 'selected-item']) + 1

    def render_item(self, window, item, index):
        item = super(CodeBuffer, self).render_item(window, item, index)
        if self._line is not None and index + 1 == self._line:
            return [{'content':    item[0],
                     'foreground': 'special',
                     'background': 'special'}]
        return item


thread_state_str = {
    constants.THREAD_STATE_INITIAL:   'INI',
    constants.THREAD_STATE_SUSPENDED: 'SUS',
    constants.THREAD_STATE_RUNNING:   'RUN'
}

thread_state_col = {
    constants.THREAD_STATE_INITIAL:   'default',
    constants.THREAD_STATE_SUSPENDED: 'error',
    constants.THREAD_STATE_RUNNING:   'info'
}

class ThreadBuffer(ThreadBufferKeymap, cui.buffers.TreeBuffer):
    """Display all existing threads in the current session."""

    __keymap__ = {
        'C-c':  py_open_eval
    }

    @classmethod
    def name(cls, session):
        return 'pydevd Threads(%s:%s)' % session.address

    def __init__(self, session):
        super(ThreadBuffer, self).__init__(session)
        self.session = session

    @property
    def thread(self):
        return self.selected_thread()

    def selected_thread(self):
        item = self.selected_item()
        if isinstance(item, cui_pydevd.D_Thread):
            return item
        elif isinstance(item, cui_pydevd.D_Frame):
            return item.thread

    def selected_frame(self):
        item = self.selected_item()
        return item           if isinstance(item, cui_pydevd.D_Frame) else \
               item.frames[0] if isinstance(item, cui_pydevd.D_Thread) and \
                                 item.state == constants.THREAD_STATE_SUSPENDED else \
               None

    def on_item_selected(self):
        frame = self.selected_frame()
        if frame:
            frame.thread.display_frame(frame)

    def get_roots(self):
        return list(self.session.threads.values())

    def get_children(self, item):
        return item.frames

    def has_children(self, item):
        return isinstance(item, cui_pydevd.D_Thread) and item.frames

    def is_expanded(self, item):
        return True

    def set_expanded(self, item):
        pass

    def render_node(self, window, item, depth, width):
        if isinstance(item, cui_pydevd.D_Thread):
            return [[{'content':    '%s' % thread_state_str[item.state],
                      'foreground': thread_state_col[item.state]},
                     ' %s ' % item.name,
                     {'content':    '(%s)' % item.id,
                      'foreground': 'inactive'}]]
        elif isinstance(item, cui_pydevd.D_Frame):
            return [truncate_left(width,
                                  '%s:%s' % (item.file, item.line))]


class BreakpointBuffer(cui.buffers.TreeBuffer):
    """
    Displays all breakpoints loaded in pydevd, as well as the
    sessions for which they are and are not active.
    """
    @classmethod
    def name(cls, session):
        return ("pydevd Breakpoints %s"
                % ('' if session is None else ('(%s)' % session)))

    def __init__(self, session):
        super(BreakpointBuffer, self).__init__(session)
        self._session = session
        self._breakpoints = cui.get_variable(constants.ST_BREAKPOINTS)

    def is_expanded(self, item):
        return True

    def get_roots(self):
        return self._breakpoints.paths()

    def has_children(self, item):
        return not (isinstance(item, tuple) and isinstance(item[1], bool))

    def get_children(self, item):
        # Files: str
        if isinstance(item, str):
            return list(zip(itertools.repeat(item),
                            self._breakpoints.breakpoints(item)))
        # Sessions
        elif isinstance(item, tuple) and isinstance(item[1], bool):
            return []
        # Lines: (str, int) (only have children when no session is provided)
        elif not self._session and isinstance(item, tuple) and isinstance(item[1], int):
            return list(self._breakpoints.sessions(item[0], item[1]).items())

        return []

    def render_node(self, window, item, depth, width):
        if isinstance(item, str):
            return [item]
        elif isinstance(item, tuple) and isinstance(item[1], bool):
            return [{'content': item[0],
                     'foreground': 'default' if item[1] else 'inactive'}]
        elif isinstance(item, tuple) and isinstance(item[1], int):
            active = self._session is None or self._breakpoints.sessions(item[0], item[1])[str(self._session)]
            if self._session:
                return [{'content': str(item[1] + 1),
                         'foreground': ('default' if active \
                                        else 'inactive')}]
            else:
                return [str(item[1] + 1)]


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
