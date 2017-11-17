# Copyright (c) 2017 Christoph Landgraf. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import cui
import socket
import errno

from cui.tools import server

from cui_pydevd import buffers
from cui_pydevd import constants
from cui_pydevd import payload
from cui_pydevd import highlighter

cui.def_foreground('comment',         'yellow')
cui.def_foreground('keyword',         'magenta')
cui.def_foreground('function',        'cyan')
cui.def_foreground('string',          'green')
cui.def_foreground('string_escape',   'yellow')
cui.def_foreground('string_interpol', 'yellow')

cui.def_variable(constants.ST_HOST,      'localhost')
cui.def_variable(constants.ST_PORT,      4040)
cui.def_variable(constants.ST_SERVER,    None)
cui.def_variable(constants.ST_SOURCES,   None)
cui.def_variable(constants.ST_DEBUG_LOG, False)

cui.def_hook(constants.ST_ON_SET_FRAME)
cui.def_hook(constants.ST_ON_SUSPEND)
cui.def_hook(constants.ST_ON_RESUME)
cui.def_hook(constants.ST_ON_KILL_THREAD)
cui.def_hook(constants.ST_ON_KILL_SESSION)


class Command(object):
    def __init__(self, command, sequence_no, payload):
        self.command = command
        self.sequence_no = sequence_no
        self.payload = payload

    @staticmethod
    def from_string(s):
        command, sequence_no, payload_raw = s.split('\t', 2)
        return Command(int(command), int(sequence_no), payload.create_payload(int(command), payload_raw))


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
                raise server.ConnectionTerminated('received 0 bytes')

            self._read_buffer += r.decode('utf-8')
            while self._read_buffer.find('\n') != -1:
                response, self._read_buffer = self._read_buffer.split('\n', 1)
                if cui.get_variable(constants.ST_DEBUG_LOG):
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

    def _init_window_set(self):
        name = '%s %s' % (constants.WINDOW_SET_NAME, self.id)
        if not cui.has_window_set(name):
            cui.new_window_set(name)
            cui.buffer_visible(buffers.ThreadBuffer, self.session,
                               split_method=None)
            cui.buffer_visible(buffers.CodeBuffer, self,
                               split_method=cui.split_window_below)
            cui.buffer_visible(buffers.FrameBuffer, self,
                               split_method=cui.split_window_right)

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

    def on_eval(self, sequence_no, variables):
        if sequence_no in self.evals:
            self.evals.remove(sequence_no)
            cui.exec_if_buffer_exists(lambda b: b.extend(*[v['value'] for v in variables]),
                                      buffers.EvalBuffer, self)

    def update_thread(self, thread_info):
        if thread_info['type'] == 'thread_suspend':
            self.state = constants.THREAD_STATE_SUSPENDED
            self._init_frames(thread_info['frames'])
        elif thread_info['type'] == 'thread_resume':
            self.state = constants.THREAD_STATE_RUNNING
            self.frames = []
            cui.exec_if_buffer_exists(lambda b: b.set_file(),
                                      buffers.CodeBuffer, self)
            cui.run_hook(constants.ST_ON_RESUME, self)

    def _init_frames(self, frame_infos):
        self.frames = []
        for frame_info in frame_infos:
            self.frames.append(D_Frame(self,
                                       frame_info['id'],
                                       frame_info['file'],
                                       frame_info['name'],
                                       frame_info['line']))
        frame = self.frames[0]
        cui.run_hook(constants.ST_ON_SUSPEND, self, frame.file, frame.line)
        self.display_frame(frame)

    def display_frame(self, frame):
        self._init_window_set()
        frame.display()

    def update_frame(self, sequence_no, variables):
        for frame in self.frames:
            if frame.pending == sequence_no:
                frame.init_variables(variables)
                cui.exec_if_buffer_exists(lambda b: b.set_frame(frame),
                                          buffers.FrameBuffer, self)

    def update_variable(self, sequence_no, variables):
        for frame in self.frames:
            if sequence_no in frame.pending_vars:
                frame.update_variable(sequence_no, variables)

    def close(self):
        for b in [buffers.CodeBuffer, buffers.FrameBuffer, buffers.EvalBuffer]:
            cui.kill_buffer(b, self)
        cui.delete_window_set_by_name('%s %s' % (constants.WINDOW_SET_NAME, self.id))
        cui.run_hook(constants.ST_ON_KILL_THREAD, self)

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
        self.pending_vars = {}

    def display(self):
        if self.variables is None and self.pending is None:
            self.pending = self.thread.session.send_command(constants.CMD_GET_FRAME,
                                                            '%s\t%s\t%s'
                                                            % (self.thread.id, self.id, ''))

        cui.exec_in_buffer_window(lambda b: b.set_file(self.file, self.line),
                                  buffers.CodeBuffer, self.thread)
        cui.exec_if_buffer_exists(lambda b: b.set_frame(self),
                                  buffers.FrameBuffer, self.thread)
        cui.exec_if_buffer_exists(lambda b: b.set_frame(self),
                                  buffers.EvalBuffer, self.thread)
        cui.run_hook(constants.ST_ON_SET_FRAME, self.thread, self.file, self.line)

    def _extend_variables(self, variables, parent=None):
        for variable in variables:
            variable['pending'] = None
            variable['has_children'] = variable['isContainer']
            variable['parent'] = parent
            variable['variables'] = []
            variable['expanded'] = False
        return variables

    def _get_path(self, variable):
        path = []
        while variable:
            path.insert(0, variable['name'])
            variable = variable['parent']
        return path

    def init_variables(self, variables):
        self.variables = self._extend_variables(variables)
        self.pending = None

    def request_variable(self, variable):
        if variable['pending']:
            return

        path = self._get_path(variable)
        joined_path = ' '.join(path)
        arg_string = '%(thread)s\t%(frame)s\tFRAME\t%(path)s' % {
            'thread': self.thread.id,
            'frame': self.id,
            'path': '\t'.join(path)
        }
        sequence_no = self.thread.session.send_command(constants.CMD_GET_VAR,
                                                       arg_string)
        variable['pending'] = sequence_no
        self.pending_vars[sequence_no] = variable

    def update_variable(self, sequence_no, variables):
        variable = self.pending_vars.pop(sequence_no)
        if variables:
            variable['variables'] = self._extend_variables(variables, variable)
        else:
            variable['has_children'] = False
        variable['pending'] = None


class Session(server.Session):
    def __init__(self, socket):
        super(Session, self).__init__(socket)
        self.threads = collections.OrderedDict()
        self._response_reader = ResponseReader(self)
        self._sequence_no = 1
        self.send_command(constants.CMD_LIST_THREADS)
        self.send_command(constants.CMD_RUN)

    def send_command(self, command, argument=''):
        sequence_no = self._sequence_no
        self.send_all(('%s\t%s\t%s\n'
                       % (command, sequence_no, argument)).encode('utf-8'))
        self._sequence_no += 2
        return sequence_no

    def handle(self):
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
                    self.threads[item['id']].update_thread(item)
        elif response.command == constants.CMD_THREAD_RESUME:
            self.threads[response.payload['id']].update_thread(response.payload)
        elif response.command == constants.CMD_GET_FRAME:
            for thread in self.threads.values():
                thread.update_frame(response.sequence_no, response.payload)
        elif response.command == constants.CMD_GET_VAR:
            for thread in self.threads.values():
                thread.update_variable(response.sequence_no, response.payload)
        elif response.command == constants.CMD_EVAL_EXPR:
            for thread in self.threads.values():
                thread.on_eval(response.sequence_no, response.payload)

    def close(self):
        for thread in self.threads.values():
            thread.close()
        cui.kill_buffer(buffers.ThreadBuffer, self)
        cui.run_hook(constants.ST_ON_KILL_SESSION)
        super(Session, self).close()


@cui.init_func
def initialize():
    srv = server.Server(Session, constants.ST_HOST, constants.ST_PORT)
    cui.set_variable(constants.ST_SERVER, srv)
    srv.start()

    cui.set_variable(constants.ST_SOURCES, highlighter.SourceManager())
    cui.buffer_visible(buffers.SessionBuffer)
