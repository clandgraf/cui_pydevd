# Copyright (c) 2017 Christoph Landgraf. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

WINDOW_SET_NAME = 'pydevd'

######################
## cui Variable Names
######################

ST_HOST =                  ['pydevds', 'host']
ST_PORT =                  ['pydevds', 'port']
ST_SERVER =                ['pydevds', 'debugger']
ST_BREAKPOINTS =           ['pydevds', 'breakpoints']
ST_ON_SET_FRAME =          ['pydevds', 'on-set-frame']
ST_ON_SUSPEND =            ['pydevds', 'on-suspend']
ST_ON_RESUME =             ['pydevds', 'on-resume']
ST_ON_KILL_THREAD =        ['pydevds', 'on-kill-thread']
ST_ON_KILL_SESSION =       ['pydevds', 'on-kill-session']
ST_FILE_MAPPING =          ['pydevds', 'file-mapping']
ST_SERIALIZE_BREAKPOINTS = ['pydevds', 'serialize-breakpoints']
ST_DEBUG_LOG =             ['logging', 'pydevds-comm']

#####################
## Debugger Commands
#####################

CMD_RUN = 101
CMD_LIST_THREADS = 102

# CMD_THREAD_CREATE
# -----------------
#
# Sent from the debugger to the frontend when a new thread
# has been created.
#
# Payload:
#
#
CMD_THREAD_CREATE = 103
CMD_THREAD_KILL = 104
CMD_THREAD_SUSPEND = 105
CMD_THREAD_RESUME = 106
CMD_STEP_INTO = 107
CMD_STEP_OVER = 108
CMD_STEP_RETURN = 109
CMD_GET_VAR = 110

# CMD_SET_BREAK
# -------------
#
CMD_SET_BREAK = 111

# CMD_REMOVE_BREAK
# ----------------
#
# Remove a breakpoint from a file
#
# Payload:
#
#   111/t<SEQ_NO>\t<TYPE>\t<FILE>\t<ID>
#
# Variables:
#
#   <SEQ_NO> -> Debugger Sequence Number
#   <TYPE> -> Breakpoint type (we support only 'python-line')
#   <FILE> -> The path to the file in which to set the breakpoint
#
CMD_REMOVE_BREAK = 112
CMD_EVAL_EXPR = 113
CMD_GET_FRAME = 114
CMD_EXEC_EXPR = 115

# CMD_VERSION
# -----------
#
# Sent to debugger to initialize and request its version
# If IDE_OS is omitted it defaults to 'WINDOWS', if
# BREAKPOINTS_BY is omitted it defaults to 'LINE'.
#
# Debugger responds with CMD_VERSION.
#
# Payload:
#   501\t<SEQ>\t<LOCAL_VERSION>\t[<IDE_OS>\t[<BREAKPOINTS_BY>]]
#
# Variables:
#   LOCAL_VERSION -> arbitrary?
#   IDE_OS -> 'WINDOWS' | 'UNIX'
#   BREAKPOINTS_BY -> 'LINE' | 'ID'
#
# Response:
#   501\t<SEQ>\t<VERSION_STRING>
#
CMD_VERSION = 501
CMD_RETURN = 502

# CMD_ERROR
# ---------
#
# TODO implement CMD_ERROR
#
# Sent from debugger to frontend to inform about an error
# that occurred.
#
CMD_ERROR = 901

#################
## Thread States
#################

THREAD_STATE_INITIAL   = 1
THREAD_STATE_SUSPENDED = 2
THREAD_STATE_RUNNING   = 3
