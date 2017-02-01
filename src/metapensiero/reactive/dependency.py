# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- dependency class
# :Created:   mar 26 gen 2016 18:15:10 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Alberto Berti
#

import asyncio
import collections
import enum
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

DEPLETED_TOKEN = object()

TEE_STATUS = enum.IntEnum('TeeStatus', 'INITIAL STARTED STOPPED DEPLETED ERROR')
TEE_MODE = enum.IntEnum('TeeMode', 'PULL PUSH')


class Tee:
    """An object clones an asynchronous iterator. It is not meant to give each
    consumer the same stream of values no matter when the consumer starts the
    iteration like the tee in itertools. Here 'when' matters. Each consumer
    will receive any value collected **after** it started iterating over the
    Tee object.

    Another feature is that this object will start consuming its source only
    when consumers start iterating over and stops doing it as soon as it is
    not consumed anymore. This is to lower the price in terms of task
    switches.

    It can also work in 'push' mode, where it doesn't iterates over any source
    but any value is passed in using the `push` method and the Tee is
    permanently stopped using the `close` method.
    """

    def __init__(self, source=None, *, push_mode=False, loop=None):
        """
        :param aiterable source: The object to async iterate. Can be an a
          direct async-iterable (which should implement an ``__aiter__``
          method) or a callable that should return an async-iterable.
        :param bool push_mode: True if the Tee should operate in push mode.
        :param loop: The optional loop.
        :type loop: `asyncio.BaseEventLoop`
        """
        self.loop = loop or asyncio.get_event_loop()
        self._mode = TEE_MODE.PUSH if push_mode else TEE_MODE.PULL
        if self._mode == TEE_MODE.PULL:
            self._status = TEE_STATUS.INITIAL
        else:
            self._status = TEE_STATUS.STARTED
        self._source = source
        self._queues = {}
        self._run_fut = None

    def __aiter__(self):
        next_value_avail, queue = self._add_queue()
        return self.gen(next_value_avail, queue)

    def _add_queue(self):
        """Add a queue to the group that will receive the incoming values"""
        q = collections.deque()
        e = asyncio.Event(loop=self.loop)
        self._queues[e] = q
        return e, q

    def _cleanup(self):
        """Sent to the queues a marker value that means that ther will be no more
        values after that.
        """
        self._push(DEPLETED_TOKEN)

    async def _del_queue(self, ev):
        """Remove a queue, called by the generator instance that is driven by a
        consumer when it gets garbage collected. Also, if there are no more
        queues to fill, halt the source consuming task.
        """
        queue = self._queues.pop(ev)
        queue.clear()
        if len(self._queues) == 0:
            if self._run_fut and self._run_fut.cancel():
                try:
                    await self._run_fut
                except asyncio.CancelledError:
                    self._status = TEE_STATUS.STOPPED

    def _push(self, element):
        """Push a new value into the queues and signal that a value is waiting."""
        for event, queue in self._queues.items():
            queue.append(element)
            event.set()

    async def _run(self):
        """Private coroutine that consumes the source."""
        self._status = TEE_STATUS.STARTED
        try:
            if hasattr(self._source, '__aiter__'):
                source = self._source.__aiter__()
            else:
                assert callable(self._source)
                source = self._source()
            async for el in source:
                if len(self._queues) == 0:
                    self._status = TEE_STATUS.STOPPED
                    break
                self._push(el)
            else:
                self._status = TEE_STATUS.DEPLETED
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.push(e)
            self._status = TEE_STATUS.ERROR
        finally:
            self._cleanup()

    def close(self):
        """Close a started tee and mark it as depleted, used in ``push`` mode."""
        assert self._status == TEE_STATUS.STARTED
        self._status = TEE_STATUS.DEPLETED
        self._cleanup()

    async def gen(self, next_value_avail, queue):
        """An async generator instantiated per consumer."""
        if self._status in [TEE_STATUS.INITIAL, TEE_STATUS.STOPPED]:
            self.run()
        elif self._status == TEE_STATUS.DEPLETED and len(queue) == 0:
            return
        try:
            while await next_value_avail.wait():
                if len(queue):
                    v = queue.popleft()
                    if v == DEPLETED_TOKEN:
                        break
                    elif isinstance(v, Exception):
                        raise v
                    else:
                        yield v
                else:
                    next_value_avail.clear()
        finally:
            await self._del_queue(next_value_avail)

    def push(self, value):
        """Public api to push a value."""
        assert self._status == TEE_STATUS.STARTED
        self._push(value)

    def run(self):
        """Starts the source-consuming task."""
        assert self._source is not None
        self._run_fut = asyncio.ensure_future(self._run(), loop=self.loop)

    @property
    def source(self):
        return self._source

    @source.setter
    def source(self, value):
        assert self._source is None and self._mode == TEE_MODE.PULL
        self._source = value
