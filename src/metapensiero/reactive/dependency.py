# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- dependency class
# :Created:   mar 26 gen 2016 18:15:10 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Alberto Berti
#

import asyncio
import collections
from contextlib import suppress
import enum
import functools
import logging
import inspect

from metapensiero import signal


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


SELECTOR_STATUS = enum.IntEnum('SelectorStatus', 'INITIAL STARTED STOPPED CLOSED')
STOPPED_TOKEN = object()


class Selector:
    """An object that accepts multiple async iterables and *unifies* them. It is
    itself an async iterable."""

    def __init__(self, *sources, loop=None, await_send=False, remove_none=False):
        self.loop = loop or asyncio.get_event_loop()
        self._status = SELECTOR_STATUS.INITIAL
        self._sources = set(sources)
        self._result_avail = asyncio.Event(loop=self.loop)
        self._results = collections.deque()
        self._await_send = await_send
        self._remove_none = remove_none
        self._source_data = collections.defaultdict(dict)
        self._gen = None

    def __aiter__(self):
        if self._gen:
            raise RuntimeError('This Selector already has a consumer, there can'
                               ' be only one.')
        else:
            self._gen = g = self.gen()
        return g

    def _cleanup(self, source):
        self._source_status(source, SELECTOR_STATUS.STOPPED)
        data = self._source_data[source]
        data['task'] = None
        if data['send_capable']:
            data['queue'].clear()
            data['send_event'].clear()
        all_stopped = all(sd['status'] == SELECTOR_STATUS.STOPPED for sd in
                          self._source_data.values())
        if all_stopped:
            self._push(STOPPED_TOKEN)

    async def _iterate_source(self, source, agen, send_value_avail=None,
                              queue=None):
        self._source_status(source, SELECTOR_STATUS.STARTED)
        send_capable = queue is not None
        send_value = None
        try:
            while True:
                if send_capable:
                    el = await agen.asend(send_value)
                else:
                    el = await agen.__anext__()
                self._push(el)
                if send_capable:
                    if self._await_send:
                        await send_value_avail.wait()
                        send_value = queue.popleft()
                        if len(queue) == 0:
                            send_value_avail.clear()
                    else:
                        if len(queue) > 0:
                            send_value = queue.popleft()
                        else:
                            send_value = None
        except StopAsyncIteration:
            pass
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._push(e)
        finally:
            self._cleanup(source)

    def _push(self, el):
        """Check the result of the future. If the exception is an instance of
        ``StopAsyncIteration`` it means that the corresponding source is
        exhausted.

        The exception is not raised here because it will be swallowed. Instead
        it is raised on the :meth:`gen` method.
        """
        if self._remove_none:
            if el is not None:
                self._results.append(el)
                self._result_avail.set()
        else:
            self._results.append(el)
            self._result_avail.set()

    def _run(self):
        for s in self._sources:
            self._start_source_loop(s)
        self._status = SELECTOR_STATUS.STARTED

    def _send(self, value):
        assert value is not None
        for sd in self._source_data.values():
            queue = sd['queue']
            event = sd['send_event']
            if queue is not None:
                queue.append(value)
                event.set()

    def _source_status(self, source, status=None):
        if status:
            self._source_data[source]['status'] = status
        else:
            status = self._source_data[source]['status']
        return status

    def _start_source_loop(self, source):
        """start a coroutine that will follow on source data"""
        if hasattr(source, '__aiter__'):
            agen = source.__aiter__()
        else:
            assert callable(source)
            agen = source()
        is_new = source not in self._source_data
        self._source_status(source, SELECTOR_STATUS.INITIAL)
        if is_new:
            send_capable = hasattr(agen, 'asend')
            self._source_data[source]['send_capable'] = send_capable
            if send_capable:
                queue = collections.deque()
                send_value_avail = asyncio.Event(loop=self.loop)
            else:
                send_value_avail, queue = None, None
            self._source_data[source]['queue'] = queue
            self._source_data[source]['send_event'] = send_value_avail
        else:
            queue = self._source_data[source]['queue']
            send_value_avail = self._source_data[source]['send_event']

        source_fut = asyncio.ensure_future(self._iterate_source(source, agen,
                                                                send_value_avail,
                                                                queue),
                                           loop=self.loop)
        self._source_data[source]['task'] = source_fut

    async def _stop(self):
        for s, data in self._source_data.items():
            if data['status'] == SELECTOR_STATUS.STARTED:
                data['task'].cancel()
                with suppress(asyncio.CancelledError):
                    await data['task']
        self._gen = None
        self._results.clear()
        self._result_avail.clear()
        self._status = SELECTOR_STATUS.STOPPED

    def add(self, source):
        """Add a new source to the group of those followed."""
        if source not in self._sources:
            self._sources.add(source)
            if self._status == SELECTOR_STATUS.STARTED:
                self._start_source_loop(source)

    async def gen(self):
        """Generator workhorse."""
        assert self._status in [SELECTOR_STATUS.INITIAL, SELECTOR_STATUS.STOPPED]
        self._run()
        try:
            while await self._result_avail.wait():
                if len(self._results):
                    v = self._results.popleft()
                    if v == STOPPED_TOKEN:
                        break
                    elif isinstance(v, Exception):
                        raise v
                    else:
                        sent_value = yield v
                    if sent_value is not None:
                        self._send(sent_value)
                else:
                    self._result_avail.clear()
        finally:
            await self._stop()


TEE_STATUS = enum.IntEnum('TeeStatus', 'INITIAL STARTED STOPPED CLOSED')
TEE_MODE = enum.IntEnum('TeeMode', 'PULL PUSH')


class Tee:
    """An object clones an asynchronous iterator. It is not meant to give each
    consumer the same stream of values no matter when the consumer starts the
    iteration like the tee in itertools. Here *when* matters: each consumer
    will receive any value collected **after** it started iterating over the
    Tee object.

    Another feature is that this object will start consuming its source only
    when consumers start iterating over. This is to lower the price in terms of
    task switches.

    It can also work in *push* mode, where it doesn't iterates over any source
    but any value is passed in using the :meth:`push` method and the Tee is
    permanently stopped using the :meth:`close` method.

    :param aiterable source: The object to async iterate. Can be a
      direct async-iterable (which should implement an ``__aiter__``
      method) or a callable that should return an async-iterable.
    :param bool push_mode: ``True`` if the Tee should operate in push mode.
      If it's a callable it will be used as an async callback.
    :param bool remove_none: Remove occurring ``None`` values from the
      stream.
    :param bool await_send: Await the availability of a sent value before
      consuming another value from the source.
    :param loop: The optional loop.
    :type loop: `asyncio.BaseEventLoop`
    """

    def __init__(self, source=None, *, push_mode=False, loop=None,
                 remove_none=False, await_send=False):
        self.loop = loop or asyncio.get_event_loop()
        self._mode = TEE_MODE.PUSH if push_mode else TEE_MODE.PULL
        if self._mode == TEE_MODE.PULL:
            self._status = TEE_STATUS.INITIAL
        else:
            self._status = TEE_STATUS.STARTED
        self._source = source
        self._queues = {}
        self._run_fut = None
        self._send_queue = collections.deque()
        self._send_cback = push_mode
        self._send_avail = asyncio.Event(loop=self.loop)
        self._remove_none = remove_none
        self._await_send = await_send

    def __aiter__(self):
        next_value_avail, queue = self._add_queue()
        return self.gen(next_value_avail, queue)

    def _add_queue(self):
        """Add a queue to the group that will receive the incoming values."""
        q = collections.deque()
        e = asyncio.Event(loop=self.loop)
        self._queues[e] = q
        return e, q

    def _cleanup(self):
        """Sent to the queues a marker value that means that ther will be no more
        values after that.
        """
        self._push(STOPPED_TOKEN)
        self._send_queue.clear()

    async def _del_queue(self, ev):
        """Remove a queue, called by the generator instance that is driven by a
        consumer when it gets garbage collected. Also, if there are no more
        queues to fill, halt the source consuming task.
        """
        queue = self._queues.pop(ev)
        queue.clear()
        if len(self._queues) == 0:
            if self._run_fut and self._run_fut.cancel():
                with suppress(asyncio.CancelledError):
                    await self._run_fut
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
            send_value = None
            while True:
                el = await source.asend(send_value)
                self._push(el)
                if self._await_send:
                    await self._send_avail.wait()
                if len(self._send_queue) > 0:
                    send_value = self._send_queue.popleft()
                    if self._await_send and len(self._send_queue) == 0:
                        self._send_avail.clear()
                else:
                    send_value = None
        except StopAsyncIteration:
            self._status = TEE_STATUS.STOPPED
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.push(e)
            self._status = TEE_STATUS.STOPPED
        finally:
            self._cleanup()

    async def _send(self, value):
        """Send a value coming from one of the consumers."""
        assert value is not None
        if self._mode == TEE_MODE.PUSH and callable(self._send_cback):
            await self._send_cback(value)
        else:
            self._send_queue.append(value)
            self._send_avail.set()

    def close(self):
        """Close a started tee and mark it as depleted, used in ``push`` mode."""
        assert self._status == TEE_STATUS.STARTED
        self._status = TEE_STATUS.CLOSED
        self._cleanup()

    async def gen(self, next_value_avail, queue):
        """An async generator instantiated per consumer."""
        if self._status in [TEE_STATUS.INITIAL, TEE_STATUS.STOPPED]:
            self.run()
        elif self._status == TEE_STATUS.CLOSED and len(queue) == 0:
            return
        try:
            while await next_value_avail.wait():
                if len(queue):
                    v = queue.popleft()
                    if v == STOPPED_TOKEN:
                        break
                    elif isinstance(v, Exception):
                        raise v
                    else:
                        sent_value = yield v
                    if sent_value is not None:
                        await self._send(sent_value)
                else:
                    next_value_avail.clear()
        finally:
            await self._del_queue(next_value_avail)

    def push(self, value):
        """Public api to push a value."""
        assert self._status == TEE_STATUS.STARTED
        if self._remove_none:
            if value is not None:
                self._push(value)
        else:
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
