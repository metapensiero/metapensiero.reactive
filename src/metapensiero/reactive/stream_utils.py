# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- async generator utilities
# :Created:   sab 24 giu 2017 02:40:52 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: © 2016, 2017 Alberto Berti
#

import abc
import asyncio
import collections
import collections.abc
from contextlib import suppress
import enum
import functools
import inspect


class Pluggable(abc.ABC):

    def __lshift__(self, other):
        self.plug(other)
        return other

    def plug(self, other):
        self._add_plugged(other)
        return self

    @abc.abstractmethod
    def _add_plugged(self, other):
        """Per class implementation of the plug behavior"""


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
            self._run()
            self._gen = g = self.gen()
        return g

    def _cleanup(self, source):
        self._source_status(source, SELECTOR_STATUS.STOPPED)
        data = self._source_data[source]
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
            await agen.aclose()
            raise
        except GeneratorExit:
            pass
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

    def _remove_stopped_source(self, source,  stop_fut):
        if source in self._source_data:
            del self._source_data[source]
        self._sources.remove(source)

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
            await self._stop_iteration_on(s)
        self._gen = None
        self._results.clear()
        self._result_avail.clear()
        self._status = SELECTOR_STATUS.STOPPED

    async def _stop_iteration_on(self, source):
        if self._status > SELECTOR_STATUS.INITIAL:
            data = self._source_data[source]
            if data['status'] == SELECTOR_STATUS.STARTED:
                data['task'].cancel()
            with suppress(asyncio.CancelledError):
                await data['task']
            data['task'] = None


    def add(self, source):
        """Add a new source to the group of those followed."""
        if source not in self._sources:
            self._sources.add(source)
            if self._status == SELECTOR_STATUS.STARTED:
                self._start_source_loop(source)

    async def gen(self):
        """Generator workhorse."""
        assert self._status == SELECTOR_STATUS.STARTED
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

    def remove(self, source):
        if source in self._sources:
            stop_fut = asyncio.ensure_future(self._stop_iteration_on(source),
                                             loop=self.loop)
            stop_fut.add_done_callback(
                functools.partial(self._remove_stopped_source, source))


class SingleSourced(Pluggable):

    active = False
    _source = None

    def __init__(self, source=None):
        self.source = source

    def _add_plugged(self, other):
        self.source = other

    def check_source(self):
        if self._source is None:
            raise RuntimeError("Undefined source")

    def get_source_agen(self):
        return self.get_agen(self._source)

    def get_agen(self, factory):
        self.check_source()
        if isinstance(factory, collections.abc.AsyncIterable):
            result = factory.__aiter__()
        else:
            result = factory()
        assert isinstance(result, collections.abc.AsyncGenerator)
        return result

    @property
    def source(self):
        return self._source

    @source.setter
    def source(self, value):
        if value is self._source:
            return
        if self.active:
            raise RuntimeError("Cannot set the source while active")
        if not (isinstance(value, collections.abc.AsyncIterable) or
                callable(value)):
            raise RuntimeError("The source must be and async iterable or a "
                               "callable returning an async generator")
        self._source = value


TEE_STATUS = enum.IntEnum('TeeStatus', 'INITIAL STARTED STOPPED CLOSED')
TEE_MODE = enum.IntEnum('TeeMode', 'PULL PUSH')


class Tee(SingleSourced):
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

    # Remove the need for the loop
    def __init__(self, source=None, *, push_mode=False, loop=None,
                 remove_none=False, await_send=False):
        self.loop = loop or asyncio.get_event_loop()
        self._mode = TEE_MODE.PUSH if push_mode else TEE_MODE.PULL
        if self._mode == TEE_MODE.PULL:
            self._status = TEE_STATUS.INITIAL
        else:
            self._status = TEE_STATUS.STARTED
        super().__init__(source)
        self._queues = {}
        self._run_fut = None
        self._send_queue = collections.deque()
        self._send_cback = push_mode
        self._send_avail = asyncio.Event(loop=self.loop)
        self._remove_none = remove_none
        self._await_send = await_send

    def __aiter__(self):
        return self._setup()

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
            if self._run_fut is not None:
                if self._status == TEE_STATUS.STARTED:
                    self._run_fut.cancel()
                await self._run_fut
                self._run_fut = None

    def _push(self, element):
        """Push a new value into the queues and signal that a value is waiting."""
        for event, queue in self._queues.items():
            queue.append(element)
            event.set()

    async def _run(self, source):
        """Private coroutine that consumes the source."""
        self._status = TEE_STATUS.STARTED
        try:
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
            pass
        except asyncio.CancelledError:
            await source.aclose()
            raise
        except GeneratorExit:
            pass
        except Exception as e:
            self.push(e)
            self._status = TEE_STATUS.STOPPED
        finally:
            self._status = TEE_STATUS.STOPPED
            self._cleanup()

    async def _send(self, value):
        """Send a value coming from one of the consumers."""
        assert value is not None
        if self._mode == TEE_MODE.PUSH and callable(self._send_cback):
            await self._send_cback(value)
        else:
            self._send_queue.append(value)
            self._send_avail.set()

    def _setup(self):
        if self._status in [TEE_STATUS.INITIAL, TEE_STATUS.STOPPED]:
            self.run()
        next_value_avail, queue = self._add_queue()
        return self.gen(next_value_avail, queue)

    @property
    def active(self):
        return self._status == TEE_STATUS.STARTED

    def close(self):
        """Close a started tee and mark it as depleted, used in ``push`` mode."""
        assert self._status == TEE_STATUS.STARTED
        self._status = TEE_STATUS.CLOSED
        self._cleanup()

    async def gen(self, next_value_avail, queue):
        """An async generator instantiated per consumer."""
        if self._status == TEE_STATUS.CLOSED and len(queue) == 0:
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
        except GeneratorExit:
            pass
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
        agen = self.get_source_agen()
        self._run_fut = asyncio.ensure_future(self._run(agen), loop=self.loop)
        self._status = TEE_STATUS.STARTED


class ExecPossibleAwaitable(abc.ABC):

    async def _exec_possible_awaitable(self, func, *args, **kwargs):
        result = func(*args, **kwargs)
        if inspect.isawaitable(result):
            result = await result
        return result


class Transformer(SingleSourced, ExecPossibleAwaitable):
    """A small utility class to alter a stream of values generated or sent to an
    async iterator.  """

    def __init__(self, fyield=None, fsend=None, source=None):
        self._agen = None
        super().__init__(source)
        self.yield_func = fyield
        self.send_func = fsend

    def __aiter__(self):
        self.check_source()
        if self._agen is not None:
            raise RuntimeError("Already itered on")
        self._agen = self._gen(self.yield_func, self.send_func)
        return self._agen

    async def _gen(self, fyield=None, fsend=None):
        agen = self.get_source_agen()
        send_value = None
        try:
            while True:
                value = await agen.asend(send_value)
                if fyield is not None:
                    value = await self._exec_possible_awaitable(fyield, value)
                send_value = yield value
                if fsend and send_value is not None:
                    send_value = await self._exec_possible_awaitable(fsend,
                                                                     send_value)
        except StopAsyncIteration:
            pass
        except asyncio.CancelledError:
            pass
        finally:
            self._agen = None

    @property
    def active(self):
        return self._agen is not None


class Destination(SingleSourced, ExecPossibleAwaitable):

    def __init__(self, source=None):
        super().__init__(source)
        self._run_fut = None
        self.started = None

    @abc.abstractmethod
    async def _destination(self, element):
        """Do something with each value pulled by the source"""

    async def _run(self):
        send_value = None
        try:
            agen = self.get_source_agen()
            self.started.set_result(None)
            while True:
                value = await agen.asend(send_value)
                send_value = await self._destination(value)
        except StopAsyncIteration:
            pass
        except asyncio.CancelledError:
            await agen.aclose()
        except Exception as e:
            self.started.set_exception(e)
        finally:
            self.active = False

    async def start(self):
        self.check_source()
        if not self.active and not self._run_fut:
            self.active = True
            loop = asyncio.get_event_loop()
            self.started = loop.create_future()
            self._run_fut = asyncio.ensure_future(self._run())
            await self.started

    async def stop(self):
        if self.active and self._run_fut:
            self._run_fut.cancel()
        with suppress(asyncio.CancelledError):
            await self._run_fut


class Sink(Destination):

    def __init__(self, source=None):
        super().__init__(source)
        self.data = collections.deque()

    def __iter__(self):
        return iter(self.data)

    async def _destination(self, element):
        self.data.append(element)
