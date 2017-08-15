
from . import constants

class ThreadInfo(object):
    def __init__(self, the_id, name):
        self.id = the_id
        self.name = name

    def __str__(self):
        return '%s: %s' % (self.id, self.name)

    @staticmethod
    def from_payload(payload):
        ti = ThreadInfo(payload.attrib['id'],
                        payload.attrib['name'])
        return ti

class ThreadSuspend(object):
    def __init__(self, the_id, frames):
        self.id = the_id
        self.frames = frames

    @staticmethod
    def from_payload(payload):
        return ThreadSuspend(payload.attrib['id'],
                             [parse_object(child) for child in payload.iter('frame')])

class FrameInfo(object):
    def __init__(self, the_id, the_file, name, line):
        self.id = the_id
        self.file = the_file
        self.name = name
        self.line = line

    @staticmethod
    def from_payload(payload):
        return FrameInfo(payload.attrib['id'],
                         payload.attrib['file'],
                         payload.attrib['name'],
                         payload.attrib['line'])


def parse_object(payload):
    if payload.tag == 'xml':
        return [parse_object(child) for child in payload]
    elif payload.tag == 'thread':
        return ThreadInfo.from_payload(payload)
    elif payload.tag == 'frame':
        return FrameInfo.from_payload(payload)


def parse_thread_suspend(payload):
    return [ThreadSuspend.from_payload(child) for child in payload.iter('thread')]

payload_factory_map = {
    constants.CMD_THREAD_SUSPEND: parse_thread_suspend,
    constants.CMD_RETURN: parse_object
}

def create_payload(command_id, payload):
    payload_factory = payload_factory_map.get(command_id)
    if payload_factory:
        return payload_factory(payload)

    return None
