# Copyright (c) 2017 Christoph Landgraf. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
This module turns mean xml payloads to nice Python Dicts for easier
handling in application code.
"""

from urllib.parse import unquote
from xml.etree import ElementTree as et

from . import constants

def unescape(string):
    return unquote(unquote(string).replace('&lt;', '<') \
                                  .replace('&gt;', '>') \
                                  .replace('&quot;', '"'))

def parse_object(file_mapping, payload):
    if payload.tag == 'xml':
        return [parse_object(file_mapping, child) for child in payload]
    elif payload.tag == 'thread':
        return {'type': 'thread_info',
                'id':   payload.attrib['id'],
                'name': payload.attrib['name']}
    elif payload.tag == 'frame':
        return {'type': 'frame',
                'id':   payload.attrib['id'],
                'file': file_mapping.to_this(unquote(unquote(payload.attrib['file'])).replace('\\', '/')),
                'name': payload.attrib['name'],
                'line': int(payload.attrib['line'])}
    elif payload.tag == 'var':
        return {'type':  'variable',
                'name':  payload.attrib['name'],
                'vtype': payload.attrib['type'],
                'value': unescape(payload.attrib['value']),
                'isContainer': payload.attrib.get('isContainer', 'False') == 'True'}

def parse_return(file_mapping, payload):
    return parse_object(file_mapping, et.fromstring(payload))

def parse_version_response(file_mapping, payload):
    return payload

def parse_thread_create(file_mapping, payload):
    return parse_object(file_mapping, et.fromstring(payload))

def parse_thread_suspend(file_mapping, payload):
    return [{'type':   'thread_suspend',
             'id':     thread.attrib['id'],
             'frames': [parse_object(file_mapping, frame)
                        for frame in thread.iter('frame')]}
            for thread in et.fromstring(payload).iter('thread')]

def parse_thread_resume(file_mapping, payload):
    the_id, reason = payload.split('\t', 1)
    return {'type':   'thread_resume',
            'id':     the_id,
            'reason': reason}

def parse_error(file_mapping, payload):
    return unescape(payload)

payload_factory_map = {
    constants.CMD_THREAD_CREATE: parse_thread_create,
    constants.CMD_THREAD_SUSPEND: parse_thread_suspend,
    constants.CMD_THREAD_RESUME: parse_thread_resume,
    constants.CMD_VERSION: parse_version_response,
    constants.CMD_GET_FRAME: parse_return,
    constants.CMD_GET_VAR: parse_return,
    constants.CMD_RETURN: parse_return,
    constants.CMD_EVAL_EXPR: parse_return,
    constants.CMD_ERROR: parse_error,
}

def create_payload(file_mapping, command_id, payload):
    payload_factory = payload_factory_map.get(command_id)
    if payload_factory:
        return payload_factory(file_mapping, payload)

    return None
