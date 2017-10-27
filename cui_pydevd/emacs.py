# Copyright (c) 2017 Christoph Landgraf. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import cui

from cui_emacs import highlight_line
from cui_pydevd import constants

def overlay_id(thread):
    return 'pydevds/%s/%s' % (thread.session, thread.id)

def on_set_frame(thread, file, line):
    highlight_line.highlight_line(overlay_id(thread), file, line)

def on_resume(thread):
    highlight_line.unhighlight_line(overlay_id(thread))

def on_kill_thread(thread):
    highlight_line.remove_overlay(overlay_id(thread))

@cui.init_func
def init_emacs_bindings():
    cui.add_hook(constants.ST_ON_SET_FRAME, on_set_frame)
    cui.add_hook(constants.ST_ON_RESUME, on_resume)
    cui.add_hook(constants.ST_ON_KILL_THREAD, on_kill_thread)
