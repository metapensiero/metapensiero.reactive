# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- reactivity tracker
# :Created:   mar 26 gen 2016 18:11:11 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Alberto Berti
#

import contextlib
import logging

from metapensiero import signal

from .computation import AsyncComputation, Computation
from .dependency import Dependency
from .exception import ReactiveError

from . import undefined


logger = logging.getLogger(__name__)


class Tracker(metaclass=signal.SignalAndHandlerInitMeta):
    """The manager of the dependency tracking process."""

    FLUSHER_FACTORY = None
    """Member containing the default flusher class."""

    on_after_compute = signal.Signal()
    """Signal emitted at the end of a computation."""

    def __init__(self, flusher_factory=None):
        self._computations = set()
        self.non_suspendable = False
        """Flag that is ``True`` when running an operation that should not be
        suspended (by something like asyncio or gevent)."""
        self.current_computation = None
        """Contains the current computation while in_compute is ``True``."""
        flusher_factory = flusher_factory or self.FLUSHER_FACTORY
        self.flusher = flusher_factory(self)
        self.in_compute = False
        """Flag that is ``True`` when a Computation is... calculating."""

    @property
    def active(self):
        """Flag that is ``True`` when a computation is in progress."""
        return self.current_computation is not None

    @property
    def loop(self):
        """This is only needed in Python3, for the signal machinery.
        Try to follow the flusher on the value. The flusher may be an
        asyncio-enabled one that has this detail set already.
        """
        return getattr(self.flusher, 'loop', None)

    @contextlib.contextmanager
    def no_suspend(self):
        """Mark an operation non interruptable by task management systems like
        gevent or asyncio."""
        try:
            self.non_suspendable = True
            logger.debug('non_interruptable begins')
            yield
        finally:
            self.non_suspendable = False
            logger.debug('non_interruptable ends')

    @contextlib.contextmanager
    def while_compute(self, computation):
        """Context manager to help manage the current computation."""
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
        if not self.in_compute:
            self.on_after_compute.notify()
            self.on_after_compute.subscribers.clear()

    def reactive(self, func, on_error=None, with_parent=True):
        """Wrap the provided function inside an `Computation` instance and
        track its execution.

        :param func: the function to be computed
        :param on_error: an optional callback that will be called if an
          error is raised during computation
        :param with_parent: optional flag. If ``False`` do not track parent
          computation
        :returns: an instance of :class:`~.computation.Computation`
        """
        if with_parent:
            cc = self.current_computation
        else:
            cc = None
        comp = Computation(self, cc, func, on_error)
        return comp

    def async_reactive(self, func, on_error=None, with_parent=True, equal=None,
                       initial_value=undefined):
        """Wrap the provided function inside an
        :class:`~.computation.AsyncComputation` instance and track its
        execution.

        :param func: the function to be computed
        :param on_error: an optional callback that will be called if an
          error is raised during computation
        :param with_parent: optional flag. If ``False`` do not track parent
          computation
        :param equal: an optional equality comparison function to be used
          instead of the default `operator.eq`
        :param initial_value: an optional initial value, by default
          :data:`~.computation.undefined`, a marker value that will be
          replaced with the first calculated value without generating any item
        :returns: an instance of :class:`~.computation.AsyncComputation`
        """
        if with_parent:
            cc = self.current_computation
        else:
            cc = None
        comp = AsyncComputation(self, cc, func, on_error, equal, initial_value)
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

    def dependency(self, source=None):
        return Dependency(self, source)

    @contextlib.contextmanager
    def suspend_computation(self):
        """Adapt to suspend computation."""
        if not self.active:
            raise ReactiveError("Can suspend only if active")
        try:
            old_computation = self.current_computation
            self.current_computation = None
            old_in_compute = self.in_compute
            self.in_compute = False
            old_non_suspendable = self.non_suspendable
            self.non_suspendable = False
            yield
        finally:
            self.current_computation = old_computation
            self.in_compute = old_in_compute
            self.non_suspendable = old_non_suspendable
