# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- a unobtrusive and light reactive system
# :Created:   dom 09 ago 2015 12:57:35 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2015 Alberto Berti
#

from __future__ import unicode_literals, absolute_import

import logging

logger = logging.getLogger(__name__)

DEFAULTS = dict(flusher_factory=None, tracker_instance=None)

def get_flusher_factory():
    """Get the registered flusher factory or default to
    BaseFlushManager.
    """
    global DEFAULTS
    ff = DEFAULTS.get('flusher_factory')
    if ff is None:
        from .flush import BaseFlushManager
        DEFAULTS['flusher_factory'] = ff =  BaseFlushManager
    return ff

def set_flusher_factory(ff):
    DEFAULTS['flusher_factory'] = ff

def get_tracker():
    """Get the default tracker instance or create one. If the registered
    tracker instance is registered, it is supposed to be a factory for
    tracker instances.
    """
    global DEFAULTS
    ti = DEFAULTS.get('tracker_instance')
    if ti is not None and callable(ti):
        ti = ti()
    elif ti is None:
        from .tracker import Tracker
        ff = default_flusher_factory()
        ti = Tracker(flusher_factory=ff)
        DEFAULTS['tracker_instance'] = ti
    return ti

def set_tracker(tracker_or_factory):
    DEFAULTS['tracker_instance'] = tracker_or_factory
