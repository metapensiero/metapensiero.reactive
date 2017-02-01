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

    class Gen:

        def __init__(self, count, func, delay, initial_delay=None,
                     gen_exc=False):
            self.count = count
            self.func = func
            self.delay = delay
            self.initial_delay = initial_delay
            self.gen_exc = gen_exc
            self.ix = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.ix == 0 and self.initial_delay:
                await asyncio.sleep(self.initial_delay)
            elif self.ix + 1 == self.count:
                raise StopAsyncIteration()
            elif self.gen_exc and self.ix > self.count/2:
                a = 1/0
            await asyncio.sleep(self.delay)
            v = self.func(self.ix)
            self.ix += 1
            return v


    tee = Tee(partial(gen, 10, lambda i: i, 0.1))
    ch1 = tee.__aiter__()
    ch2 = tee.__aiter__()
    data1 = [e async for e in ch1]
    data2 = [e async for e in ch2]

    assert len(data1) == len(data2) == 10
    assert len(tee._queues) == 0
    assert tee._status == TEE_STATUS.DEPLETED

    # in this round use a resumable source

    tee = Tee(Gen(10, lambda i: i, 0.1))
    ch1 = tee.__aiter__()
    ch2 = tee.__aiter__()
    data1 = []
    data2 = []
    async for e in ch1:
        if e >= 5:
            break
        else:
            data1.append(e)
    # emulate gc action
    try:
        await ch1.aclose()
    except GeneratorExit:
        pass
    async for e in ch2:
        if e >= 5:
            break
        else:
            data2.append(e)
    # emulate gc action
    try:
        await ch2.aclose()
    except GeneratorExit:
        pass

    assert len(data1) == len(data2) == 5
    assert data1 == data2
    assert len(tee._queues) == 0
    assert tee._status == TEE_STATUS.STOPPED

    # resumed operation
    ch1 = tee.__aiter__()
    ch2 = tee.__aiter__()
    data1 = [e async for e in ch1]
    data2 = [e async for e in ch2]

    # one value gets lost in the for cycles above, one on the internal tee
    # workhorse

    assert len(data1) == len(data2) == 3
    assert data1 == data2
    assert len(tee._queues) == 0
    assert tee._status == TEE_STATUS.DEPLETED

    ch1 = tee.__aiter__()
    ch2 = tee.__aiter__()
    data1 = [e async for e in ch1]
    data2 = [e async for e in ch2]

    assert len(data1) == len(data2) == 0

    tee = Tee(Gen(10, lambda i: i, 0.1, gen_exc=True))
    ch1 = tee.__aiter__()
    ch2 = tee.__aiter__()
    with pytest.raises(ZeroDivisionError):
        data1 = [e async for e in ch1]
    with pytest.raises(ZeroDivisionError):
        data2 = [e async for e in ch2]

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
    assert tee._status == TEE_STATUS.DEPLETED

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
