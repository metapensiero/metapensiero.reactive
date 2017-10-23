# -*- coding: utf-8 -*-
# :Project:  metapensiero.reactive -- test fixtures
# :Created:    ven 05 feb 2016 00:07:13 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
#

import pytest

from metapensiero.reactive import set_tracker
from metapensiero.reactive.tracker import Tracker
from metapensiero.reactive.flush.asyncio import AsyncioFlushManager

FLUSHER_FACTORIES = [AsyncioFlushManager]


class Environment(object):

    def __init__(self, flush_factory, loop):
        self.ff = flush_factory
        self.loop = loop
        self.tracker = t = Tracker(flush_factory)
        t.flusher.loop = loop
        set_tracker(self.tracker)

    def wait_for_flush(self):
        if self.tracker.flusher._flush_future:
            self.loop.run_until_complete(self.tracker.flusher._flush_future)

    def run_comp(self, func):
        return self.tracker.reactive(func)

@pytest.fixture(scope='function', params=FLUSHER_FACTORIES)
def env(request, event_loop):
    flush_factory = request.param
    yield Environment(flush_factory, event_loop)
    set_tracker(None)
