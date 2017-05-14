# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- computation object
# :Created:   mar 26 gen 2016 18:13:41 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Alberto Berti
#

import functools
import logging
import operator
import weakref

from metapensiero import signal

from .exception import ReactiveError

logger = logging.getLogger(__name__)


class BaseComputation(metaclass=signal.SignalAndHandlerInitMeta):

    invalidated = False
    """If it's invalidated, it needs re-computing"""

    stopped = False
    """Is this computation completely disabled"""

    @signal.Signal
    def on_invalidate(self, subscribers, notify):
        if self._tracker is not None:
            self._notify(self.on_invalidate, notify)

    @on_invalidate.on_connect
    def on_invalidate(self, handler, subscribers, connect):
        if self.invalidated:
            with self._tracker.no_suspend():
                handler(self)
        else:
            connect(handler)

    @signal.Signal
    def on_stop(self, subscribers, notify):
        if self._tracker is not None:
            self._notify(self.on_invalidate, notify)

    @on_stop.on_connect
    def on_stop(self, handler, subscribers, connect):
        if self.stopped:
            with self._tracker.no_suspend():
                handler(self)
        else:
            connect(handler)

    def __init__(self, tracker, parent=None):
        self._tracker = tracker
        """The associated Tracker"""
        self._tracker._computations.add(self)
        self._parent = parent
        """The parent computation"""

    def __repr__(self):
        return '<{}.{} for {} at {}>'.format(self.__module__,
                                             self.__class__.__name__,
                                             repr(self._func),
                                             id(self))

    @property
    def _needs_recompute(self):
        return self.invalidated and not self.stopped

    def _notify(self, signal, fnotify):
        try:
            with self._tracker.no_suspend():
                fnotify(self)
        finally:
            signal.clear()

    def _on_parent_invalidated(self, parent):
        """Handler that runs when a parent is invalidated. Currently it stops
        this computation.
        """
        self.stop()

    def add_dependency(self, dependency):
        """Optional method called by the dependencies that are collected. It
        does nothing here. A subclass may find useful to collect them.
        """
        pass

    def invalidate(self, dependency=None):
        """Invalidate the current state of this computation"""
        self.invalidated = True

    def suspend(self):
        """Context manager to suspend tracking"""
        return self._tracker.suspend_computation()

    def stop(self):
        """Cease to re-run the computation function when invalidated and
        remove this instance from the pool of active computations.
        """
        if not self.stopped:
            self.stopped = True
            self.invalidate()
            self._tracker._computations.remove(self)
            self._func = None
            self._tracker = None


class Computation(BaseComputation):
    """A computation is an object runs a function and re-runs it again
    when is invalidated, it does so until it is stopped. It injects
    itself as the first argument to the function being run.
    """

    first_run = False
    """Is this computation the first?"""

    guard = None
    """A callable that is called when invalidation triggers. It the result is
    ``False``, then the computation will not be added to the to-be-recomputed
    list in the flusher.
    """

    on_error = signal.Signal()
    """A signal that is notified when a computation results in an error."""

    def __init__(self, tracker, parent, func, on_error=None):
        super().__init__(tracker, parent)
        self.first_run = True
        self._func = func
        """the function to execute"""
        self._recomputing = False
        """True when a computation is re-running"""
        if on_error:
            self.on_error.connect(on_error)
        errored = False
        try:
            self._compute(first_run=True)
        except:
            errored = True
            logger.exception("Error while running computation")
            raise
        finally:
            if errored:
                self.stop()

        if not self.stopped and parent:
            parent.on_invalidate.connect(self._on_parent_invalidated)

    def _compute(self, first_run=False):
        """Run the computation and reset the invalidation."""
        self.first_run = first_run
        self.invalidated = False
        with self._tracker.while_compute(self):
            self._func(self)

    def _recompute(self):
        """Re-run the compute function and handle errors."""
        if self._needs_recompute:
            try:
                self._recomputing = True
                self._compute()
            except Exception as e:
                if len(self.on_error.subscribers) > 0:
                    self.on_error.notify(self, e)
                else:
                    logger.exception("Error while recomputing")
                    raise
            finally:
                self._recomputing = False

    def invalidate(self, dependency=None):
        """Invalidate the current state of this computation."""
        guard = self.guard
        if guard is not None and self._parent is not None:
            raise ReactiveError("The guard cannot be used with parent")
        elif guard is not None:
            recomputing_allowed = self.guard(self)
        else:
            recomputing_allowed = True
        if not self.invalidated:
            self.on_invalidate.notify()
            if not (self._recomputing or self.stopped) and recomputing_allowed:
                flusher = self._tracker.flusher
                flusher.add_computation(self)
                flusher.require_flush()

        super(Computation, self).invalidate(dependency)


class _Wrapper:
    """A small class to help wrapping methods and to keep computations."""

    def __init__(self, wrapped, tracker):
        self.tracker = tracker
        self.wrapped = wrapped
        self.computations = weakref.WeakKeyDictionary()

    def __get__(self, instance, owner):
        wrap_call = functools.partial(self.__call__, instance)
        return functools.update_wrapper(wrap_call, self.wrapped)

    def __call__(self, instance):
        comp = self.computations.get(instance)
        if comp is None or (comp is not None and comp.stopped()):
            comp = self.tracker.reactive(functools.partial(self.wrapped,
                                                           instance))
        return comp

    def __delete__(self, instance):
        if instance in self.computations:
            comp = self.computations[instance]
            del self.computations[instance]
            comp.stop()


def computation(method_or_tracker):
    """A decorator that helps using computations directly in class
    bodies. Returns a property descriptor that returns a callable to
    start the computation on each instance. It allows also to remove
    the computation for an instance. The computation is executed once
    and returned. It is roughly equivalent to:

    .. code:: python

      class Foo(object):

          def __init__(self):
              self.computation = None

          def start_computation(self, tracker=None):
              tracker = tracker or metapensiero.reactive.get_tracker()
              if not self.computation:
                  self.computation = tracker.reactive(self._worker)
              return self.computation

          def _worker(self):
              # do something useful

    that becomes:

    .. code:: python

      class Foo(object):

          @computation
          def _worker(self):
              # do something useful
    """

    from .tracker import Tracker
    from . import get_tracker

    def decorate(method):
        return _Wrapper(method, tracker)

    if isinstance(method_or_tracker, Tracker):
        tracker = method_or_tracker
        return decorate
    else:
        tracker = get_tracker()
        return _Wrapper(method_or_tracker, tracker)


undefined = object()
"Marker instance used for unspecified or missing values."


class AsyncComputation(Computation):
    """A *streaming* version of a normal computation.

    To create an instance of this class call the
    :meth:`.tracker.Tracker.async_reactive` method.

    As in normal computations, the computing function is executed each time
    any of the dependency it collected changes.

    But, differently from the normal computation where half of the work of the
    computed function is to create *side effects* somewhere else, here the
    computed function is required to return some value.

    This value is then stored by the computation as the `current_value`
    attribute, it is compared with the initial or previous value and made
    available using either the *async iterator* or the *async context manager*
    protocols.

    Using the former protocol the caller (the calling ``async for`` cycle)
    will receive any new value different from the previous.

    The latter protocol together with the `initial_value` parameter can be
    used to obtain a trigger and block of code can be executed only after a
    certain condition expressed by the computing function is met.
    """


    def __init__(self, tracker, parent, func, on_error=None, equal=None,
                 initial_value=undefined):
        """
        :param tracker: an instance of :class:`~.tracker.Tracker` that is
          managing the computing process
        :param parent: a possible parent computation owning this
        :param func: the function to be computed
        :param on_error: an optional callback that will be called if an
          error is raised during computation
        :param equal: an optional equality comparison function to be used
          instead of the default ``operator.eq``
        :param initial_value: an optional initial value. By default it is a
          marker value called ``undefined``, that will be replaced with the
          first calculated value without generating any item.
        """
        func = functools.partial(self._auto, func)
        self._equal = equal or operator.eq
        self.current_value = initial_value
        self._tracker = tracker
        self._init_next_value_container()
        super().__init__(tracker, parent, func, on_error)

    async def __aenter__(self):
        """If this computation is consumed by an ``async with`` statement, the
        computation is considered a one-time trigger."""
        async for el in self:
            return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self.stop()
        return False

    async def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.stopped:
            return await self._next
        else:
            raise StopAsyncIteration()

    def _auto(self, func, computation):
        new = func(computation)
        old = self.current_value
        if not ((old is undefined) or self._equal(old, new)):
           self._next.set_result(new)
           self._init_next_value_container()
        self.current_value = new

    def _init_next_value_container(self):
        self._next = self._tracker.loop.create_future()
