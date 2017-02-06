# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- dependency tests
# :Created:   lun 30 gen 2017 16:28:18 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Alberto Berti
#

import asyncio
from functools import partial

import pytest

from metapensiero import reactive
from metapensiero.reactive.dependency import StreamDependency, Sink


@pytest.mark.asyncio
async def test_stream_dependency(event_loop):

    s = StreamDependency()
    sink = Sink(s)
    await sink.start()
    agen = s.__aiter__()
    v = None
    s.changed('a_value')
    async for el in agen:
        v = el
        break

    assert v == 'a_value'
    try:
        await agen.aclose()
    except StopAsyncIteration:
        pass

    assert list(sink) == ['a_value']
    await sink.stop()

@pytest.mark.asyncio
async def test_stream_following(event_loop):
    s = StreamDependency()
    s1 = StreamDependency()

    def transf(v):
        return s1, v

    s.follow(s1, ftrans=transf)
    sink = Sink(s)
    await sink.start()

    s1.changed('a_value')
    # simulate switch and comeback
    await asyncio.sleep(0.1)
    assert list(sink) == [(s1, 'a_value')]
    await sink.stop()

@pytest.mark.xfail
@pytest.mark.asyncio
async def test_stream_invalidate(event_loop, env):
    s = StreamDependency()
    s1 = StreamDependency()

    def transf(v):
        return s1, v

    s.follow(s1, ftrans=transf)

    c = env.run_comp(lambda c: s.depend())

    sink = Sink(s)
    await sink.start()

    s1.changed('a_value')
    assert c.invalidated
    # simulate switch and comeback
    await asyncio.sleep(0.1)

    assert list(sink) == [(s1, 'a_value')]
    await sink.stop()
