import collections
import cui
import select
import socket
import threading
import errno

from pydevds import constants
from pydevds import payload
from pydevds import highlighter

ST_HOST =           ['pydevds', 'host']
ST_PORT =           ['pydevds', 'port']
ST_SERVER =         ['pydevds', 'debugger']
ST_SOURCES =        ['pydevds', 'sources']

class Command(object):
    def __init__(self, command, sequence_no, payload):
        self.command = command
        self.sequence_no = sequence_no
        self.payload = payload

    def __str__(self):
        command_string = constants.cmd_labels.get(self.command, 'Unknown Command')
        string = command_string + '\n'
        if self.payload:
            for obj in self.payload:
                string += '\t%s' % obj + '\n'
        return string

    @staticmethod
    def from_string(s):
        command, sequence_no, payload_raw = s.split('\t', 2)
        return Command(int(command), int(sequence_no), payload.create_payload(int(command), payload_raw))


class ResponseReader(object):
    def __init__(self, session):
        self.session = session
        self.read_buffer = ''

    def read_responses(self):
        responses = []
        try:
            r = self.session.socket.recv(4096)

            if len(r) == 0:
                cui.message('Debugger ended connection')
                if len(self.read_buffer) > 0:
                    cui.message('Received incomplete message: %s' % self.read_buffer)
                return None

            self.read_buffer += r.decode('utf-8')
            while self.read_buffer.find('\n') != -1:
                response, self.read_buffer = self.read_buffer.split('\n', 1)
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

    def step_into(self):
        self.session.send_command(constants.CMD_STEP_INTO, self.id)

    def step_over(self):
        self.session.send_command(constants.CMD_STEP_OVER, self.id)

    def step_return(self):
        self.session.send_command(constants.CMD_STEP_RETURN, self.id)

    def resume(self):
        self.session.send_command(constants.CMD_THREAD_RESUME, self.id)

    def update(self, thread_info):
        if isinstance(thread_info, payload.ThreadSuspend):
            self.state = constants.THREAD_STATE_SUSPENDED
            self._update_frames(thread_info.frames)
        elif isinstance(thread_info, payload.ThreadResume):
            self.state = constants.THREAD_STATE_RUNNING
            self.frames = []

    def _update_frames(self, frame_infos):
        self.frames = []
        for frame_info in frame_infos:
            self.frames.append(D_Frame(self,
                                       frame_info.id,
                                       frame_info.file,
                                       frame_info.name,
                                       frame_info.line))
        self.display_frame(self.frames[0])

    def display_frame(self, frame):
        # Display line in
        window, buffer_object = cui.buffer_visible(CodeBuffer, self.session, self)
        with cui.window_selected(window):
            buffer_object.set_file(frame.file, frame.line)

    @staticmethod
    def from_thread_info(session, thread_info):
        return D_Thread(session, thread_info.id, thread_info.name)


class D_Frame(object):
    def __init__(self, thread, id_, file_, name, line):
        self.thread = thread
        self.id = id_
        self.file = file_
        self.name = name
        self.line = line

    def get_info():
        self.session.send_command(constants.CMD_GET_FRAME,
                                  '%s\t%s\t%s' % (self.thread.id, self.id, ''))

class Session(object):
    def __init__(self, socket):
        self.socket = socket
        self.address = socket.getsockname()
        self.threads = {}
        self._response_reader = ResponseReader(self)
        self._sequence_no = 1
        self.send_command(constants.CMD_LIST_THREADS)
        self.send_command(constants.CMD_RUN)

    def send_command(self, command, argument=''):
        self.socket.send(('%s\t%s\t%s\n'
                          % (command, self._sequence_no, argument)).encode('utf-8'))
        self._sequence_no += 2

    def process_responses(self):
        responses = self._response_reader.read_responses()
        if responses is None:
            return
        for response in responses:
            self.dispatch(response)

    def dispatch(self, response):
        if response.command == constants.CMD_RETURN:
            for item in response.payload:
                if isinstance(item, payload.ThreadInfo):
                    if item.id in self.threads:
                        self.threads[item.id].update(item)
                    else:
                        self.threads[item.id] = D_Thread.from_thread_info(self, item)
                elif isinstance(item, payload.ThreadSuspend):
                    self.threads[item.id].update(item)
        elif response.command == constants.CMD_THREAD_SUSPEND:
            item = response.payload[0]
            if isinstance(item, payload.ThreadSuspend):
                self.threads[item.id].update(item)
        elif response.command == constants.CMD_THREAD_RESUME:
            self.threads[response.payload.id].update(response.payload)

    def __str__(self):
        return self.key()

    def key(self):
        return '%s:%s' % self.address

    @staticmethod
    def key_from_socket(socket):
        return '%s:%s' % socket.getsockname()


def with_thread(fn):
    def _fn(*args, **kwargs):
        return fn(cui.current_buffer().thread,
                  *args,
                  **kwargs)
    return _fn

def with_frame(fn):
    def _fn(*args, **kwargs):
        frame = cui.current_buffer().selected_frame()
        if frame:
            return fn(frame.thread, frame, *args, **kwargs)


class CodeBuffer(cui.buffers.ListBuffer):
    __keymap__ = {
        '<f5>': with_thread(lambda thr: thr.step_into()),
        '<f6>': with_thread(lambda thr: thr.step_over()),
        '<f7>': with_thread(lambda thr: thr.step_return()),
        '<f8>': with_thread(lambda thr: thr.resume()),
        'C-b':  lambda: cui.current_buffer().center_break()
    }

    @classmethod
    def name(cls, session, thread):
        return ('Code (%s:%s/%s)'
                % (session.address[0], session.address[1], thread.id))

    def __init__(self, session, thread):
        super(CodeBuffer, self).__init__(session, thread)
        self._session = session
        self._thread = thread
        self._rows = []
        self._line = 0

    @property
    def thread(self):
        return self._thread

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
            return [{'content': indexed_item,
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

class ThreadBuffer(cui.buffers.TreeBuffer):
    __keymap__ = {
        '<f5>': with_thread(lambda thr: thr.step_into()),
        '<f6>': with_thread(lambda thr: thr.step_over()),
        '<f7>': with_thread(lambda thr: thr.step_return()),
        '<f8>': with_thread(lambda thr: thr.resume())
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
        return item if isinstance(item, D_Frame) else None

    def on_item_selected(self):
        thread = self.selected_thread()
        frame = self.selected_frame()
        if frame:
            self.thread.display_frame(frame)

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
    @classmethod
    def name(cls):
        return "pydevd Sessions"

    def on_item_selected(self):
        cui.switch_buffer(ThreadBuffer, self.selected_item())

    def prepare(self):
        self._flattened = list(cui.get_variable(ST_SERVER).clients.values())

    def items(self):
        return self._flattened

    def render_item(self, window, item, index):
        return [str(item)]


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
                except socket.error as e:
                    key = session.key()
                    cui.message('Connection from %s terminated' % key)
                    s.close()
                    del self.clients[key]


@cui.update_func
def handle_sockets():
    cui.get_variable(ST_SERVER).process_sockets()


@cui.init_func
def init_pydevds():
    cui.def_foreground('keyword', 'red')
    cui.def_variable(ST_HOST, 'localhost')
    cui.def_variable(ST_PORT, 4040)
    cui.def_variable(ST_SERVER, DebugServer())
    cui.def_variable(ST_SOURCES, highlighter.SourceManager())
    cui.switch_buffer(SessionBuffer)
