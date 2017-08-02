import cui
import socket
import threading

from pydevds import constants

ST_SESSIONS = ['pydevds', 'sessions']
ST_PORT =     ['pydevds', 'port']


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
                print 'Debugger ended connection'
                if len(self.read_buffer) > 0:
                    self.session.debugger.logger.log('Received incomplete message: %s' % self.read_buffer)
                return None

            self.read_buffer += r
            while self.read_buffer.find('\n') != -1:
                response, self.read_buffer = self.read_buffer.split('\n', 1)
                self.session.debugger.logger.log('\nReceived response: \n  %s\n\n' % (response,))
                responses.append(Command.from_string(response))
        except socket.error, e:
            if e.args[0] not in [errno.EAGAIN, errno.EWOULDBLOCK]:
                raise e

        return responses


class ResponseReaderThread(threading.Thread):
    def __init__(self, session):
        super(ResponseReaderThread, self).__init__()
        self.session = session
        self.response_reader = ResponseReader(session)
        self.is_running = False

    def run(self):
        try:
            self.is_running = True
            while True:
                responses = self.response_reader.read_responses()
                if responses is None:
                    return
                for response in responses:
                    self.session.dispatch(response)
        except Exception, e:
            self.session.debugger.logger.log('ResponseReader: %s' % e.message)
        finally:
            self.is_running = False


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
        self.frames.clear()
        for frame_info in frame_infos:
            self.frames.append(D_Frame(frame_info.id,
                                       frame_info.file_,
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
    def __init__(self, socket, address):
        self.socket = socket
        self.address = address
        self.response_reader_thread = ResponseReaderThread(self)
        self.command_sender = CommandSender(self)
        self.threads = {}

    def start(self):
        self.response_reader_thread.start()
        self.command_sender.send(constants.CMD_LIST_THREADS)
        self.command_sender.send(constants.CMD_RUN)

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
        return '%s' % (self.address,)


class DebugServer(threading.Thread):
    def __init__(self, core):
        self.core = core
        self.port = self.core.state(ST_PORT)

    def run():
        hostname = socket.gethostname()
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((host, port))
        server.listen(5)
        self.core.logger.log('Listening on %s:%s' % (host, port))
        while 1:
            sock, addr = server.accept()
            try:
                self.core.logger.log('Connection received from %s' % (addr,))
                session = Session(s, address)
                self.core.state(ST_SESSIONS).append(session)
                session.start()

            except socket.error, e:
                self.core.logger.log('Received socket error: %s' % e.message)
            except Exception, e:
                self.core.logger.log(traceback.format_exc())
            finally:
                s.close()
                self.core.state(ST_SESSIONS).remove(session)


@cui.init_func
def init_pydevds(core):
    core.set_state(ST_PORT,     4040)
    core.set_state(ST_SESSIONS, [])
    core.logger.log('Hallo Welt')
