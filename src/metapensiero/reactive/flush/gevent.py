# -*- coding: utf-8 -*-
# :Project:  metapensiero.reactive -- gevent compatible flusher
# :Created:    mer 27 gen 2016 20:42:41 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
#

from __future__ import unicode_literals, absolute_import

import six

import logging

import gevent

from .base import BaseFlushManager

logger = logging.getLogger(__name__)


class GeventFlushManager(BaseFlushManager):

    HAS_SUSPEND_CAPABILITY = True

    def _schedule_flush(self):
        gevent.spawn(self._run_flush)
        logger.debug("Scheduled gevent flush")
