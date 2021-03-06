# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- a unobtrusive and light reactive system
# :Created:   dom 09 ago 2015 12:57:35 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2015 Alberto Berti
#

import logging

logger = logging.getLogger(__name__)

DEFAULTS = dict(flusher_factory=None, tracker_instance=None)


def get_flusher_factory():
    """Get the registered flusher factory or default to
    :class:`~.flush.base.BaseFlushManager`.
    """
    global DEFAULTS
    ff = DEFAULTS.get('flusher_factory')
    if ff is None:
        DEFAULTS['flusher_factory'] = ff = AsyncioFlushManager
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
        ff = get_flusher_factory()
        ti = Tracker(flusher_factory=ff)
        DEFAULTS['tracker_instance'] = ti
    return ti


def set_tracker(tracker_or_factory):
    DEFAULTS['tracker_instance'] = tracker_or_factory


class Undefined:
    """Marker class for undefined value."""

    def __bool__(self):
        return False

undefined = Undefined()
"Marker instance used for unspecified or missing values."


from .tracker import Tracker
from .value import Value
from .flush import AsyncioFlushManager
from .nlist import reactivenamedlist as namedlist
from .computation import BaseComputation, Computation, computation
from .dict import ReactiveDict, ReactiveChainMap
