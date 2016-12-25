# -*- coding: utf-8 -*-
# :Project:  metapensiero.reactive -- computation object
# :Created:    mar 26 gen 2016 18:13:41 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
#

from __future__ import unicode_literals, absolute_import

import functools
import logging
import weakref

import six
from metapensiero import signal

from .exception import ReactiveError

logger = logging.getLogger(__name__)


@six.add_metaclass(signal.SignalAndHandlerInitMeta)
class BaseComputation(object):

    invalidated = False
    """If it's invalidated, it needs re-computing"""
    stopped = False
    """Is this computation completely disabled"""

    @signal.Signal
    def on_invalidate(self, subscribers, notify):
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
        """Optional method called by the dependencies that are collected. It does
        nothing here. A subclass may find useful to collect them.
        """
        pass

    def invalidate(self, dependency=None):
        """Invalidate the current state of this computation"""
        self.invalidated = True

    def suspend(self):
        """Context manager to suspend tracking"""
        return self._tracker.supsend_computation()

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
    """A callable that is called when invalidation triggers. It the result
       is False, then the computation will not be added to the
       to-be-recomputed list in the flusher."""

    on_error = signal.Signal()
    """A signal that is notified when a computation results in an error."""

    def __init__(self, tracker, parent, func, on_error=None):
        super(Computation, self).__init__(tracker, parent)
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
            logger.exception("Error while runnning computation")
            raise
        finally:
            if errored:
                self.stop()

        if not self.stopped and parent:
            parent.on_invalidate.connect(self._on_parent_invalidated)

    def _compute(self, first_run=False):
        """Run the computation and reset the invalidation"""
        self.first_run = first_run
        self.invalidated = False
        with self._tracker.while_compute(self):
            self._func(self)

    def _recompute(self):
        """Re-run the compute function and handle errors"""
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
        """Invalidate the current state of this computation"""
        guard = self.guard
        if guard and self._parent:
            raise ReactiveError("The guard cannot be used with parent")
        elif guard:
            recomputing_allowed = self.guard(self)
        else:
            recomputing_allowed = True
        if (not (self.invalidated or guard)) or (guard and recomputing_allowed):
            if not (self._recomputing or self.stopped):
                flusher = self._tracker.flusher
                flusher.add_computation(self)

            self.on_invalidate.notify()
        super(Computation, self).invalidate(dependency)

class _Wrapper(object):
    """A small class to help wrapping methods and to keep computations"""

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
