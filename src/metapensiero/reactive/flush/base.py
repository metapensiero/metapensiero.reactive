# -*- coding: utf-8 -*-
# :Project:  metapensiero.reactive -- base flush manager class
# :Created:    mer 27 gen 2016 15:38:25 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
#

import logging
import collections

from metapensiero import signal

from ..exception import ReactiveError
from ..computation import Computation

logger = logging.getLogger(__name__)


class BaseFlushManager(metaclass=signal.SignalAndHandlerInitMeta):
    "Base flush manager."

    on_before_flush = signal.Signal()
    """A signal that will notify just before the flush operation
    happens. It will execute the callback passing in the list of the
    pending computations. All the connected callbacks will be
    disconnected after each notify().
    """

    on_after_flush = signal.Signal()
    """A signal that is used to notify when the flush operation has been
    completed. All the connected callbacks will be disconnected after
    each notify().
    """

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
        self._flush_requested = False

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
                if self._tracker.in_compute:
                    self._tracker.on_after_compute.connect(
                        self._schedule_flush_after_compute
                    )
                else:
                    self._schedule_flush()

    def _schedule_flush_after_compute(self):
        self._schedule_flush()

    def _schedule_flush(self):
        """Schedule a flush to be executed asap in another 'task' if something
        like asyncio or gevent is available. This implementation
        just executes '_run_flush' directly.
        """
        if self._in_flush:
            self._flush_requested = True
        else:
            self._run_flush()
            if self._flush_requested:
                self._run_flush()
                self._flush_requested = False

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
            if len(pending) > 0:
                # pending may not contain all the computation flushed
                self.on_before_flush.notify(pending)
                self.on_before_flush.clear()
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

__all__ = ('BaseFlushManager', )
