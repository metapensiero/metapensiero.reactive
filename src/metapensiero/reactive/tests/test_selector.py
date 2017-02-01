# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- selector tests
# :Created:   lun 30 gen 2017 16:28:18 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Alberto Berti
#

import asyncio
from functools import partial

import pytest

from metapensiero.reactive.dependency import Selector, Tee, TEE_STATUS


@pytest.mark.asyncio
async def test_selector(event_loop):

    async def gen(count, func, delay, initial_delay=None, gen_exc=False):
        if initial_delay:
            await asyncio.sleep(initial_delay)
        for i in range(count):
            yield func(i)
            if gen_exc and i > count/2:
                a = 1/0
            await asyncio.sleep(delay)

    # results = []
    # async for el in partial(gen, 10, lambda i: i, 0.1)():
    #     results.append(el)

    # assert len(results) == 10

    # results = []
    # async for el in partial(gen, 10, lambda i: i*2, 0.1)():
    #     results.append(el)

    # assert len(results) == 10

    s = Selector(
        partial(gen, 10, lambda i: i, 0.1),
        partial(gen, 10, lambda i: chr(i+64), 0.1),
    )

    results = []
    async for el in s:
        results.append(el)
    assert len(results) == 20


    s = Selector(
        partial(gen, 10, lambda i: i, 0.1),
        partial(gen, 10, lambda i: chr(i+64), 0.1, gen_exc=True),
    )

    with pytest.raises(ZeroDivisionError):
        results = []
        async for el in s:
            results.append(el)

@pytest.mark.asyncio
async def test_tee(event_loop):

    async def gen(count, func, delay, initial_delay=None, gen_exc=False):
        if initial_delay:
            await asyncio.sleep(initial_delay)
        for i in range(count):
            yield func(i)
            if gen_exc and i > count/2:
                a = 1/0
            await asyncio.sleep(delay)

    tee = Tee(partial(gen, 10, lambda i: i, 0.1))
    ch1 = tee.__aiter__()
    ch2 = tee.__aiter__()
    data1 = [e async for e in ch1]
    data2 = [e async for e in ch2]

    assert len(data1) == len(data2) == 10
    assert len(tee._queues) == 0
    assert tee._status == TEE_STATUS.STOPPED

    ch1 = tee.__aiter__()
    ch2 = tee.__aiter__()
    data1 = [e async for e in ch1]
    data2 = [e async for e in ch2]

    assert len(data1) == len(data2) == 10

    tee = Tee(gen(10, lambda i: i, 0.1, gen_exc=True))
    ch1 = tee.__aiter__()
    ch2 = tee.__aiter__()
    with pytest.raises(ZeroDivisionError):
        data1 = [e async for e in ch1]
    with pytest.raises(ZeroDivisionError):
        data2 = [e async for e in ch2]

@pytest.mark.asyncio
async def test_tee_send(event_loop):

    async def echo_gen():
        v = yield 'initial'
        while v != 'done':
            v = yield v

    tee = Tee(echo_gen, remove_none=True, await_send=True)
    ch1 = tee.__aiter__()
    ch2 = tee.__aiter__()

    # setup
    v1 = await ch1.asend(None)
    v2 = await ch2.asend(None)

    assert v1 == v2 == 'initial'

    data1 = []
    data2 = []
    data1.append(await ch1.asend(1))
    data2.append(await ch2.asend('a'))
    data1.append(await ch1.asend('done'))
    data2.append(await ch2.asend('done'))

    with pytest.raises(StopAsyncIteration):
        data1.append(await ch1.asend(None))
    with pytest.raises(StopAsyncIteration):
        data1.append(await ch2.asend(None))

    assert data1 == data2 == [1, 'a']

    assert tee._status == TEE_STATUS.STOPPED


@pytest.mark.asyncio
async def test_tee_push_mode(event_loop):

    tee = Tee(push_mode=True)
    ch1 = tee.__aiter__()
    ch2 = tee.__aiter__()

    tee.push('a')
    tee.push('b')
    tee.close()

    data1 = [e async for e in ch1]
    data2 = [e async for e in ch2]

    assert len(data1) == len(data2) == 2
    assert data1 == data2 == ['a', 'b']
    assert tee._status == TEE_STATUS.CLOSED

    tee = Tee(push_mode=True)
    ch1 = tee.__aiter__()
    ch2 = tee.__aiter__()

    tee.push('a')
    tee.push('b')
    tee.push(ZeroDivisionError())
    tee.close()

    with pytest.raises(ZeroDivisionError):
        data1 = [e async for e in ch1]
    with pytest.raises(ZeroDivisionError):
        data2 = [e async for e in ch2]

    sent_values = []

    async def sent(value):
        sent_values.append(value)

    tee = Tee(push_mode=sent)
    ch1 = tee.__aiter__()
    ch2 = tee.__aiter__()

    tee.push('a')
    v1 = await ch1.asend(None)
    v2 = await ch2.asend(None)

    assert v1 == v2 == 'a'

    data1 = []
    data2 = []
    tee.push('b')
    data1.append(await ch1.asend(1))
    data2.append(await ch2.asend('c'))


    assert data1 == data2 == ['b']
    assert sent_values == [1, 'c']
    tee.close()
