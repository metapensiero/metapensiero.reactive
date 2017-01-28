# -*- coding: utf-8 -*-
# :Project:  metapensiero.reactive -- gevent compatible flusher
# :Created:    mer 27 gen 2016 20:42:41 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
#

import logging

import gevent

from .base import BaseFlushManager

logger = logging.getLogger(__name__)


class GeventFlushManager(BaseFlushManager):
    """A Flush manager that uses gevent to schedule the flush operations."""

    HAS_SUSPEND_CAPABILITY = True

    def __init__(self, tracker):
        super(GeventFlushManager,self).__init__(tracker)
        self._flush_greenlet = None

    def _schedule_flush(self):
        self._flush_greenlet = gevent.spawn(self._run_flush)
        logger.debug("Scheduled gevent flush")

    def _run_flush(self):
        super(GeventFlushManager, self)._run_flush()
        logger.debug("Gevent flush completed")
