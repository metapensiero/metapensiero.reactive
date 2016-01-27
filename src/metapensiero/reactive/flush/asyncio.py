# -*- coding: utf-8 -*-
# :Project:  metapensiero.reactive -- asyncio compatible flusher
# :Created:    mer 27 gen 2016 20:25:42 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
#

import asyncio
import logging

from .base import BaseFlushManager

logger = logging.getLogger(__name__)


class AsyncioFlushManager(BaseFlushManager):

    HAS_SUSPEND_CAPABILITY = True

    def __init__(self, tracker, loop=None):
        super(AsyncioFlushManager, self).__init__(tracker)
        self.loop = loop or asyncio.get_event_loop()

    def _schedule_flush(self):
        self.loop.call_soon(self._run_flush)
        logger.debug("Scheduled asyncio flush")
