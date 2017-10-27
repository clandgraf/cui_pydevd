# Copyright (c) 2017 Christoph Landgraf. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

WINDOW_SET_NAME = 'pydevd'

ST_HOST =            ['pydevds', 'host']
ST_PORT =            ['pydevds', 'port']
ST_SERVER =          ['pydevds', 'debugger']
ST_SOURCES =         ['pydevds', 'sources']
ST_ON_SET_FRAME =    ['pydevds', 'on-set-frame']
ST_ON_SUSPEND =      ['pydevds', 'on-suspend']
ST_ON_RESUME =       ['pydevds', 'on-resume']
ST_ON_KILL_THREAD =  ['pydevds', 'on-kill-thread']
ST_ON_KILL_SESSION = ['pydevds', 'on-kill-session']
ST_DEBUG_LOG =       ['logging', 'pydevds-comm']

CMD_RUN = 101
CMD_LIST_THREADS = 102
CMD_THREAD_CREATE = 103
CMD_THREAD_SUSPEND = 105
CMD_THREAD_RESUME = 106
CMD_STEP_INTO = 107
CMD_STEP_OVER = 108
CMD_STEP_RETURN = 109
CMD_GET_VAR = 110
CMD_EVAL_EXPR = 113
CMD_GET_FRAME = 114

CMD_RETURN = 502

THREAD_STATE_INITIAL   = 1
THREAD_STATE_SUSPENDED = 2
THREAD_STATE_RUNNING   = 3

cmd_labels = {
    CMD_RETURN: 'Return'
}
