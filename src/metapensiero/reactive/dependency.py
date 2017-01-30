# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- dependency class
# :Created:   mar 26 gen 2016 18:15:10 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Alberto Berti
#

import asyncio
import collections
import functools
from metapensiero import signal

import logging

logger = logging.getLogger(__name__)


class Dependency(metaclass=signal.SignalAndHandlerInitMeta):

    source = None
    """The source of a dependency, if any."""

    on_change = signal.Signal()

    def __init__(self, tracker, source=None):
        self._tracker = tracker
        self._dependents = set()
        self._source = source
        self._change_fut = None
        self._shift_changed_future()

    def __call__(self, computation=None):
        """Used to declare the dependency of a computation on an instance of this
        class. The dependency can be explicit by passing in a `Computation`
        instance or better it can be implicit, which is the usual way. When in
        implicit mode, the dependency finds the running computation by asking
        the `Tracker`.
        """
        if not (computation or self._tracker.active):
            result = False
        else:
            computation = computation or self._tracker.current_computation
            if computation not in self._dependents:
                self._dependents.add(computation)
                computation.add_dependency(self)
                computation.on_invalidate.connect(
                    self._on_computation_invalidate
                )
                result = True
            else:
                result = False
        return result

    depend = __call__

    async def __aiter__(self):
        while True:
            el = await self._change_fut
            yield el

    def _shift_changed_future(self, result=None):
        if self._change_fut:
            self._change_fut.resolve(result)
        self._change_fut = self._tracker.loop.create_future()

    def _on_computation_invalidate(self, computation):
        self._dependents.remove(computation)

    def _on_change_handler(self, followed_dependency):
        """Handler that will be called from following dependencies."""
        assert isinstance(followed_dependency, Dependency)
        self.changed()

    def changed(self, result=None):
        """This is called to declare that value/state/object that this instance
        rephresents has changed. It will notify every computation that was
        calculating when was called `depend` on it.
        It will also notify any handler connected to its `on_change` Signal.
        """
        deps = self._dependents
        self.on_change.notify(self)
        self._shift_changed_future(result)
        if len(deps) > 0:
            for comp in list(deps):
                comp.invalidate(self)
            self._tracker.flusher.require_flush()

    def follow(self, *others):
        """Follow the changed event of another dependency and change as well."""
        for other in others:
            assert isinstance(other, Dependency)
            other.on_change.connect(self._on_change_handler)

    @property
    def has_dependents(self):
        """True if this dependency has any computation that depends on it."""
        return len(self._dependents) > 0

    @property
    def source(self):
        """Return a possible connected object."""
        return self._source

    def unfollow(self, *others):
        """Stop following another dependency."""
        for other in others:
            assert isinstance(other, Dependency)
            other.on_change.disconnect(self._on_change_handler)



class Selector:
    """An object that accepts multiple async iterables and 'unifies' them. It is
    itself an async iterable."""


    def __init__(self, *sources, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self._sources = set(sources)
        self._result_avail = asyncio.Event(loop=self.loop)
        self._results = collections.deque()
        for s in self._sources:
            self._wait_on(s)

    def __aiter__(self):
        return self.gen()

    def _future_handler(self, source, agen, future):
        """When one of the awaited futures is done, this gets executed"""
        self._waiting_futures.pop(future)
        if self._push(source, future):
            self._wait_on(source, agen)

    def _push(self, source, done_future):
        """Check the result of the future. If the exception is an instance of
        'StopAsyncIteration' it means that the corresponding source is
        exhausted.

        The exception is not raised here because it will be swallowed. Instead
        it is raised on the gen() function.
        """
        exc = done_future.exception()
        if isinstance(exc, StopAsyncIteration):
            self._sources.remove(source)
            res = False
        elif exc is not None:
            self._results.append(exc)
            res = False
        else:
            self._results.append(done_future.result())
            res = True
        self._result_avail.set()
        return res

    def _setup_waiter(self, source, agen, awaitable):
        """Setup callback to track the generator."""
        next_fut = asyncio.ensure_future(awaitable, loop=self.loop)
        next_fut.add_done_callback(functools.partial(self._future_handler,
                                                     source, agen))

    def _wait_on(self, source, agen=None):
        """Get a generator from a source and wait for the next value."""
        if not agen:
            if hasattr(source, '__aiter__'):
                agen = source.__aiter__()
            else:
                assert callable(source)
                agen = source()
        next = agen.__anext__()
        self._setup_waiter(source, agen, next)

    def add(self, source):
        """Add a new source to the group of those followed"""
        if source not in self._sources:
            self._sources.add(source)

    async def gen(self):
        """Generator workhorse."""
        if self.stopped:
            return
        while await self._result_avail.wait():
            if self.stopped:
                break
            if len(self._results):
                value = self._results.popleft()
                if isinstance(value, Exception):
                    raise value
                yield value
            else:
                self._result_avail.clear()

    @property
    def stopped(self):
        return len(self._sources) == 0
