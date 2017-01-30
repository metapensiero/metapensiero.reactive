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

from metapensiero.reactive.dependency import Selector


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
