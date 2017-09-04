import collections
import cui
import select
import socket
import threading
import errno

from xml.etree import ElementTree as et

from pydevds import constants
from pydevds import payload

ST_HOST =           ['pydevds', 'host']
ST_PORT =           ['pydevds', 'port']
ST_SERVER =         ['pydevds', 'debugger']

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
        pl = None if payload_raw == '' else et.fromstring(payload_raw)
        return Command(int(command), int(sequence_no), payload.create_payload(int(command), pl))


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

            self.read_buffer += r
            while self.read_buffer.find('\n') != -1:
                response, self.read_buffer = self.read_buffer.split('\n', 1)
                cui.message('Received response: \n%s' % (response,))
                responses.append(Command.from_string(response))
        except socket.error as e:
            if e.args[0] not in [errno.EAGAIN, errno.EWOULDBLOCK]:
                raise e

        return responses


class CommandSender():
    def __init__(self, session):
        self.session = session
        self.sequence_no = 1

    def send(self, command, argument=''):
        self.session.socket.send('%s\t%s\t%s\n' %
                                 (command, self.sequence_no, argument))
        self.sequence_no += 2


class D_Thread(object):
    def __init__(self, the_id, name, state=constants.THREAD_STATE_INITIAL):
        self.id = the_id
        self.name = name
        self.state = state
        self.frames = []

    def update(self, thread_info):
        if isinstance(thread_info, payload.ThreadSuspend):
            self.state = constants.THREAD_STATE_SUSPENDED
            self._update_frames(thread_info.frames)

    def _update_frames(self, frame_infos):
        self.frames = []
        for frame_info in frame_infos:
            self.frames.append(D_Frame(frame_info.id,
                                       frame_info.file,
                                       frame_info.name,
                                       frame_info.line))

    @staticmethod
    def from_thread_info(thread_info):
        return D_Thread(thread_info.id, thread_info.name)


class D_Frame(object):
    def __init__(self, id_, file_, name, line):
        self.id = id_
        self.file = file_
        self.name = name
        self.line = line


class Session(object):
    def __init__(self, socket):
        self.socket = socket
        self.address = socket.getsockname()
        self.response_reader = ResponseReader(self)
        self.command_sender = CommandSender(self)
        self.command_sender.send(constants.CMD_LIST_THREADS)
        self.command_sender.send(constants.CMD_RUN)
        self.threads = {}

    def process_responses(self):
        responses = self.response_reader.read_responses()
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
                        self.threads[item.id] = D_Thread.from_thread_info(item)
                elif isinstance(item, payload.ThreadSuspend):
                    self.threads[item.id].update(item)
        elif response.command == constants.CMD_THREAD_SUSPEND:
            item = response.payload[0]
            if isinstance(item, payload.ThreadSuspend):
                self.threads[item.id].update(item)

    def __str__(self):
        return self.key()

    def key(self):
        return '%s:%s' % self.address

    @staticmethod
    def key_from_socket(socket):
        return '%s:%s' % socket.getsockname()




thread_state_str = {
    constants.THREAD_STATE_INITIAL:   'INI',
    constants.THREAD_STATE_SUSPENDED: 'SUS',
    constants.THREAD_STATE_RUNNING:   'RUN'
}


class ThreadBuffer(cui.buffers.ListBuffer):
    __keymap__ = {
        'C-s': lambda b: b.suspend_thread()
    }

    @classmethod
    def name(cls, session):
        return 'Threads(%s:%s)' % session.address

    def __init__(self, session):
        super(ThreadBuffer, self).__init__(session)
        self.session = session
        self.selected_thread = 0

    def suspend_thread(self):
        self.session.command_sender.send()

    def item_count(self):
        return len(self.session.threads)

    def render_item(self, index):
        thread = self.session.threads.values()[index]
        return '%s %s' % (thread_state_str[thread.state], thread.name)


class SessionBuffer(cui.buffers.ListBuffer):
    @classmethod
    def name(cls):
        return "Sessions"

    def on_item_selected(self):
        selected_session = cui.get_variable(ST_SERVER).clients.values()[self.selected_item]
        cui.switch_buffer(ThreadBuffer, selected_session)

    def item_count(self):
        return len(cui.get_variable(ST_SERVER).clients.values())

    def render_item(self, index):
        return cui.get_variable(ST_SERVER).clients.values()[index].__str__()


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
    cui.def_variable(ST_HOST, 'localhost')
    cui.def_variable(ST_PORT, 4040)
    cui.def_variable(ST_SERVER, DebugServer())
    cui.switch_buffer(SessionBuffer)
