from urllib.parse import unquote
from xml.etree import ElementTree as et

from . import constants

def parse_object(payload):
    if payload.tag == 'xml':
        return [parse_object(child) for child in payload]
    elif payload.tag == 'thread':
        return {'type': 'thread_info',
                'id':   payload.attrib['id'],
                'name': payload.attrib['name']}
    elif payload.tag == 'frame':
        return {'type': 'frame',
                'id':   payload.attrib['id'],
                'file': unquote(unquote(payload.attrib['file'])),
                'name': payload.attrib['name'],
                'line': int(payload.attrib['line'])}
    elif payload.tag == 'var':
        return {'type':  'variable',
                'name':  payload.attrib['name'],
                'vtype': payload.attrib['type'],
                'value': unquote(unquote(payload.attrib['value']))}

def parse_return(payload):
    return parse_object(et.fromstring(payload))

def parse_thread_suspend(payload):
    return [{'type':   'thread_suspend',
             'id':     thread.attrib['id'],
             'frames': [parse_object(frame) for frame in thread.iter('frame')]}
            for thread in et.fromstring(payload).iter('thread')]

def parse_thread_resume(payload):
    the_id, reason = payload.split('\t', 1)
    return {'type':   'thread_resume',
            'id':     the_id,
            'reason': reason}

payload_factory_map = {
    constants.CMD_THREAD_SUSPEND: parse_thread_suspend,
    constants.CMD_THREAD_RESUME: parse_thread_resume,
    constants.CMD_GET_FRAME: parse_return,
    constants.CMD_RETURN: parse_return,
    constants.CMD_EVAL_EXPR: parse_return
}

def create_payload(command_id, payload):
    payload_factory = payload_factory_map.get(command_id)
    if payload_factory:
        return payload_factory(payload)

    return None
