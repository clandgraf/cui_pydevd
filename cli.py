from . import constants

class CommandLine(object):
    def __init__(self, session):
        self.session = session

    def run(self):
        while True:
            ss = raw_input('%s\n> ' % self.session).strip().split(' ')
            if len(ss[0]) == 0:
                pass
            elif ss[0] in ['r', 'run']:
                self.session.command_sender.send(constants.CMD_RUN)
            elif ss[0] in ['t', 'threads']:
                self.session.command_sender.send(constants.CMD_LIST_THREADS)
            elif ss[0] in ['f', 'get-frame']:
                # Requires thread_id\tframe_id\tscope
                self.session.command_sender.send(constants.CMD_GET_FRAME)
            elif ss[0] in ['ts', 'thread-suspend']:
                self.session.command_sender.send(constants.CMD_THREAD_SUSPEND, ss[1])
            else:
                print 'Unknown command: %s' % (s,)
