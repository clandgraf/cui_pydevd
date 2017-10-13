# Copyright (c) 2017 Christoph Landgraf. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import cui
import cui.keymap
import functools
import select
import socket
import threading
import errno

from pydevds import constants
from pydevds import payload
from pydevds import highlighter

ST_HOST =            ['pydevds', 'host']
ST_PORT =            ['pydevds', 'port']
ST_SERVER =          ['pydevds', 'debugger']
ST_SOURCES =         ['pydevds', 'sources']
ST_ON_SET_FRAME =    ['pydevds', 'on-set-frame']
ST_ON_SUSPEND =      ['pydevds', 'on-suspend']
ST_ON_RESUME =       ['pydevds', 'on-resume']
ST_ON_KILL_THREAD =  ['pydevds', 'on-kill-thread']
ST_ON_KILL_SESSION = ['pydevds', 'on-kill-session']

cui.def_foreground('comment',         'yellow')
cui.def_foreground('keyword',         'magenta')
cui.def_foreground('function',        'cyan')
cui.def_foreground('string',          'green')
cui.def_foreground('string_escape',   'yellow')
cui.def_foreground('string_interpol', 'yellow')

cui.def_variable(ST_HOST, 'localhost')
cui.def_variable(ST_PORT, 4040)

cui.def_hook(ST_ON_SET_FRAME)
cui.def_hook(ST_ON_SUSPEND)
cui.def_hook(ST_ON_RESUME)
cui.def_hook(ST_ON_KILL_THREAD)
cui.def_hook(ST_ON_KILL_SESSION)


# ---------------------------- Buffers ----------------------------

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
        '<f8>': py_resume
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


class FrameBuffer(ThreadBufferMixin, cui.buffers.ListBuffer):
    """Display frame contents."""

    __buffer_name__ = 'Frame'

    def __init__(self, thread):
        super(FrameBuffer, self).__init__(thread)
        self._thread = thread
        self._rows = []

    def set_frame(self, frame):
        self._rows = []
        if frame.variables:
            for variable in frame.variables:
                cui.message(str(variable))
                self._rows.append('%s = {%s} %s' % (variable['name'],
                                                    variable['vtype'],
                                                    variable['value']))

    def items(self):
        return self._rows


class CodeBuffer(ThreadBufferMixin, cui.buffers.ListBuffer):
    """Display the source of the file being currently debugged."""

    __buffer_name__ = 'Code'
    __keymap__ = {
        'C-b':  lambda: cui.current_buffer().center_break()
    }

    def __init__(self, thread):
        super(CodeBuffer, self).__init__(thread)
        self._thread = thread
        self._rows = []
        self._line = 0

    def center_break(self):
        self.set_variable(['win/buf', 'selected-item'], self._line - 1)
        self.recenter()

    def set_file(self, file_path, line):
        src_mgr = cui.get_variable(ST_SOURCES)
        self._rows = src_mgr.get_file(file_path)
        self._line = line
        self.center_break()

    def items(self):
        return self._rows

    def hide_selection(self):
        return self._line == self.get_variable(['win/buf', 'selected-item']) + 1

    def render_item(self, window, item, index):
        indexed_item = ['%%%dd' % len(str(len(self._rows))) % (index + 1), ' ', item]
        if index + 1 == self._line:
            return [{'content':    indexed_item,
                     'foreground': 'special',
                     'background': 'special'}]
        else:
            return [indexed_item]


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
        if isinstance(item, D_Thread):
            return item
        elif isinstance(item, D_Frame):
            return item.thread

    def selected_frame(self):
        item = self.selected_item()
        return item           if isinstance(item, D_Frame) else \
               item.frames[0] if isinstance(item, D_Thread) and \
                                 item.state == constants.THREAD_STATE_SUSPENDED else \
               None

    def on_item_selected(self):
        frame = self.selected_frame()
        if frame:
            frame.thread.display_frame(frame)

    def get_roots(self):
        return self.session.threads.values()

    def get_children(self, item):
        if isinstance(item, D_Thread):
            return item.frames
        return []

    def render_node(self, window, item, depth, width):
        if isinstance(item, D_Thread):
            return [[{'content':    '%s' % thread_state_str[item.state],
                      'foreground': thread_state_col[item.state]},
                     ' %s' % item.name]]
        elif isinstance(item, D_Frame):
            return [cui.buffers.pad_left(width,
                                         '%s:%s' % (item.file, item.line))]


class SessionBuffer(cui.buffers.ListBuffer):
    """Display a list of active pydevd sessions."""
    @classmethod
    def name(cls):
        return "pydevd Sessions"

    def on_item_selected(self):
        cui.switch_buffer(ThreadBuffer, self.selected_item())

    def on_pre_render(self):
        self._flattened = list(cui.get_variable(ST_SERVER).clients.values())

    def items(self):
        return self._flattened

    def render_item(self, window, item, index):
        return [str(item)]


# -----------------------------------------------------------------------


class Command(object):
    def __init__(self, command, sequence_no, payload):
        self.command = command
        self.sequence_no = sequence_no
        self.payload = payload

    @staticmethod
    def from_string(s):
        command, sequence_no, payload_raw = s.split('\t', 2)
        return Command(int(command), int(sequence_no), payload.create_payload(int(command), payload_raw))


class ConnectionTerminated(Exception):
    pass


class ResponseReader(object):
    def __init__(self, session):
        self.session = session
        self._read_buffer = ''

    def read_responses(self):
        responses = []
        try:
            r = self.session.socket.recv(4096)

            if len(r) == 0:
                cui.message('Debugger ended connection')
                if len(self._read_buffer) > 0:
                    cui.message('Received incomplete message: %s' % self._read_buffer)
                # TODO raise exception to finish this session
                raise ConnectionTerminated('received 0 bytes')

            self._read_buffer += r.decode('utf-8')
            while self._read_buffer.find('\n') != -1:
                response, self._read_buffer = self._read_buffer.split('\n', 1)
                cui.message('Received response: \n%s' % (response,))
                responses.append(Command.from_string(response))
        except socket.error as e:
            if e.args[0] not in [errno.EAGAIN, errno.EWOULDBLOCK]:
                raise e

        return responses


class D_Thread(object):
    def __init__(self, session, the_id, name, state=constants.THREAD_STATE_INITIAL):
        self.session = session
        self.id = the_id
        self.name = name
        self.state = state
        self.frames = []
        self.evals = set()

    def step_into(self):
        self.session.send_command(constants.CMD_STEP_INTO, self.id)

    def step_over(self):
        self.session.send_command(constants.CMD_STEP_OVER, self.id)

    def step_return(self):
        self.session.send_command(constants.CMD_STEP_RETURN, self.id)

    def resume(self):
        self.session.send_command(constants.CMD_THREAD_RESUME, self.id)

    def eval(self, frame, expr):
        self.evals.add(
            self.session.send_command(constants.CMD_EVAL_EXPR,
                                      "%(thread)s\t%(frame)s\tLOCAL\t%(expr)s\t0"
                                      % {'thread': self.id,
                                         'frame': frame.id,
                                         'expr': expr}))

    def update(self, thread_info):
        if thread_info['type'] == 'thread_suspend':
            self.state = constants.THREAD_STATE_SUSPENDED
            self._update_frames(thread_info['frames'])
        elif thread_info['type'] == 'thread_resume':
            self.state = constants.THREAD_STATE_RUNNING
            self.frames = []
            cui.run_hook(ST_ON_RESUME, self)

    def _update_frames(self, frame_infos):
        self.frames = []
        for frame_info in frame_infos:
            self.frames.append(D_Frame(self,
                                       frame_info['id'],
                                       frame_info['file'],
                                       frame_info['name'],
                                       frame_info['line']))
        frame = self.frames[0]
        cui.run_hook(ST_ON_SUSPEND, self, frame.file, frame.line)
        self.display_frame(frame)

    def on_eval(self, sequence_no, variables):
        if sequence_no in self.evals:
            self.evals.remove(sequence_no)
            cui.exec_if_buffer_exists(lambda b: b.extend(*[v['value'] for v in variables]),
                                      EvalBuffer, self)

    def update_frame(self, sequence_no, variables):
        for frame in self.frames:
            if frame.pending == sequence_no:
                frame.variables = variables
                frame.pending = None
                cui.exec_if_buffer_exists(lambda b: b.set_frame(frame),
                                          FrameBuffer, self)

    def display_frame(self, frame):
        if frame.variables is None and frame.pending is None:
            frame.pending = self.session.send_command(constants.CMD_GET_FRAME,
                                                      '%s\t%s\t%s' % (self.id, frame.id, ''))

        cui.exec_in_buffer_visible(lambda b: b.set_file(frame.file, frame.line),
                                   CodeBuffer, self)
        cui.exec_in_buffer_visible(lambda b: b.set_frame(frame),
                                   FrameBuffer, self,
                                   split_method=cui.split_window_right)
        cui.exec_if_buffer_exists(lambda b: b.set_frame(frame),
                                  EvalBuffer, self)
        cui.run_hook(ST_ON_SET_FRAME, self, frame.file, frame.line)

    def close(self):
        for b in [CodeBuffer, FrameBuffer, EvalBuffer]:
            cui.kill_buffer(b, self)
        cui.delete_all_windows()
        cui.run_hook(ST_ON_KILL_THREAD, self)

    @staticmethod
    def from_thread_info(session, thread_info):
        return D_Thread(session, thread_info['id'], thread_info['name'])


class D_Frame(object):
    def __init__(self, thread, id_, file_, name, line):
        self.thread = thread
        self.id = id_
        self.file = file_
        self.name = name
        self.line = line
        self.variables = None
        self.pending = None


class Session(object):
    def __init__(self, socket):
        self.socket = socket
        self.address = socket.getsockname()
        self.threads = collections.OrderedDict()
        self._response_reader = ResponseReader(self)
        self._sequence_no = 1
        self.send_command(constants.CMD_LIST_THREADS)
        self.send_command(constants.CMD_RUN)

    def send_command(self, command, argument=''):
        sequence_no = self._sequence_no
        self.socket.send(('%s\t%s\t%s\n'
                          % (command, sequence_no, argument)).encode('utf-8'))
        self._sequence_no += 2
        return sequence_no

    def process_responses(self):
        responses = self._response_reader.read_responses()
        if responses is None:
            return
        for response in responses:
            self._dispatch(response)

    def _dispatch(self, response):
        if response.command == constants.CMD_RETURN:
            for item in response.payload:
                if item['type'] == 'thread_info':
                    if item['id'] in self.threads:
                        self.threads[item['id']].update(item)
                    else:
                        self.threads[item['id']] = D_Thread.from_thread_info(self, item)
        elif response.command == constants.CMD_THREAD_SUSPEND:
            for item in response.payload:
                if item['type'] == 'thread_suspend':
                    self.threads[item['id']].update(item)
        elif response.command == constants.CMD_THREAD_RESUME:
            self.threads[response.payload['id']].update(response.payload)
        elif response.command == constants.CMD_GET_FRAME:
            for thread in self.threads.values():
                thread.update_frame(response.sequence_no, response.payload)
        elif response.command == constants.CMD_EVAL_EXPR:
            for thread in self.threads.values():
                thread.on_eval(response.sequence_no, response.payload)

    def close(self):
        for thread in self.threads.values():
            thread.close()
        cui.kill_buffer(ThreadBuffer, session)
        cui.run_hook(ST_ON_KILL_SESSION)
        self.socket.close()

    def __str__(self):
        return self.key()

    def key(self):
        return '%s:%s' % self.address

    @staticmethod
    def key_from_socket(socket):
        return '%s:%s' % socket.getsockname()


class DebugServer(object):
    def __init__(self):
        super(DebugServer, self).__init__()
        self.host = cui.get_variable(ST_HOST)
        self.port = cui.get_variable(ST_PORT)
        self.server = None
        self.clients = collections.OrderedDict()
        self._init_server()

    def _init_server(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(5)
        cui.message('Listening on %s:%s' % (self.host, self.port))

    def _accept_client(self):
        client_socket, client_address = self.server.accept()
        session = Session(client_socket)
        key = session.key()
        cui.message('Connection received from %s' % key)
        self.clients[key] = session

    def process_sockets(self):
        sock_list = []
        if self.server:
            sock_list.append(self.server)
        sock_list.extend(map(lambda session: session.socket,
                             self.clients.values()))

        sock_read, _, _ = select.select(sock_list, [], [], 0)

        for s in sock_read:
            if s is self.server:
                self._accept_client()
            else:
                session = self.clients[Session.key_from_socket(s)]
                try:
                    session.process_responses()
                except (socket.error, ConnectionTerminated) as e:
                    cui.message('Connection from %s terminated' % session)
                    session.close()
                    del self.clients[session.key()]


@cui.update_func
def handle_sockets():
    cui.get_variable(ST_SERVER).process_sockets()


@cui.init_func
def init_pydevds():
    cui.def_variable(ST_SERVER, DebugServer())
    cui.def_variable(ST_SOURCES, highlighter.SourceManager())
    cui.switch_buffer(SessionBuffer)
