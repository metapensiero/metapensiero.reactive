# -*- coding: utf-8 -*-
# :Project:  metapensiero.reactive -- reactivity tracker
# :Created:    mar 26 gen 2016 18:11:11 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
#

from __future__ import unicode_literals, absolute_import

import six

import contextlib
import logging

from metapensiero import signal

from .computation import Computation
from .dependency import Dependency

logger = logging.getLogger(__name__)


@six.add_metaclass(signal.SignalAndHandlerInitMeta)
class Tracker(object):

    FLUSHER_FACTORY = None

    on_after_compute = signal.Signal()

    def __init__(self, flusher_factory=None):
        self._computations = set()
        self.non_suspendable = False
        """Flag that is True when running an operation that should not be
        suspended (by something like asyncio or gevent)"""
        self.current_computation = None
        """Contains the current computation while in_compute is True"""
        flusher_factory = flusher_factory or self.FLUSHER_FACTORY
        self.flusher = flusher_factory(self)
        self.in_compute = False
        """Flag that is True when a Computation is... calculating"""

    @property
    def active(self):
        return self.current_computation is not None

    @contextlib.contextmanager
    def no_suspend(self):
        """Mark an operation non interruptable by task management systems like
        gevent or asyncio"""
        try:
            self.non_suspendable = True
            logger.debug('non_interruptable begins')
            yield
        finally:
            self.non_suspendable = False
            logger.debug('non_interruptable ends')

    @contextlib.contextmanager
    def while_compute(self, computation):
        try:
            old_computation = self.current_computation
            self.current_computation = computation
            old_in_compute = self.in_compute
            self.in_compute = True
            with self.no_suspend():
                yield
        finally:
            self.current_computation = old_computation
            self.in_compute = old_in_compute

    def reactive(self, func, on_error=None):
        comp = Computation(self, self.current_computation, func, on_error)
        return comp

    def on_invalidate(self, func):
        if self.active:
            self.current_computation.on_invalidate.connect(func)

    def on_stop(self, func):
        if self.active:
            self.current_computation.on_stop.connect(func)

    def on_after_flush(self, func):
        self.flusher.on_after_flush.connect(func)

    def flush(self):
        self.flusher.require_flush(immediate=True)

    def dependency(self):
        return Dependency(self)
