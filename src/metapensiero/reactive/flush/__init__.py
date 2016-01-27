# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- a unobtrusive and light reactive system
# :Created:   dom 09 ago 2015 12:57:35 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2015 Alberto Berti
#

from __future__ import unicode_literals, absolute_import

import six

import logging
import collections

from metapensiero import signal

from .. import ReactiveError
from ..computation import Computation

logger = logging.getLogger(__name__)


@six.add_metaclass(signal.SignalAndHandlerInitMeta)
class BaseFlushManager(object):

    on_after_flush = signal.Signal()

    HAS_SUSPEND_CAPABILITY = False

    def __init__(self, tracker):
        self._tracker = tracker
        self._in_flush = False
        "Marker that is True when a flush is in progress"
        self._pending = collections.deque()
        """Contains the invalidated computations that will be recomputed in
        the next scheduled flush"""
        self._will_flush = False
        """Marker that is True when a flush operation is scheduled"""

        def add_computation(self, comp):
            assert (isinstance(comp, Computation) and
                    comp._tracker is self._tracker)
            if comp not in self._pending:
                self._pending.append(comp)

        def require_flush(self, immediate=False):
            if not self._will_flush:
                self._will_flush = True
                if immediate:
                    self._run_flush()
                else:
                    self._schedule_flush()

        def _schedule_flush(self):
            """Schedule a flush to be executed asap in another 'task' if something
            like asyncio or gevent is available. This implementation
            just executes '_run_flush' directly.
            """
            self._run_flush()

        def _run_flush(self):
            if self._in_flush:
                raise ReactiveError('A flush is in progress already')
            if self._tracker.in_compute:
                raise ReactiveError('Running a flush operation while a '
                                    'calculation is in progress is forbidden')
            logger.debug('Flush operation starts')
            pending = self._pending
            self._in_flush = True
            recalcs = set()
            try:
                while len(pending) > 0:
                    comp = pending.popleft()
                    comp._recompute()
                    if comp._needs_recompute:
                        if comp in recalcs:
                            logger.error('A Computation is still in an '
                                         'invalidated state')
                            raise ReactiveError('Computation in invalidated state')
                        else:
                            # give a chance to a computation to regain
                            # valid state
                            recalcs.add(comp)
                            logger.warning('A computation needs still a recalculaton')
                            pending.append(comp)
                self.on_after_flush.notify()
                self.on_after_flush.clear()
            finally:
                self._in_flush = False
                self._will_flush = False
