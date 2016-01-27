# -*- coding: utf-8 -*-
# :Project:  metapensiero.reactive -- basic reactive value implementation
# :Created:    mar 26 gen 2016 19:23:55 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
#

from __future__ import unicode_literals, absolute_import

import six

import logging
import operator

from metapensiero import signal

from . import tracker

logger = logging.getLogger(__name__)

undefined = object()

class Value(object):

    def __init__(self, initial_value=undefined, equal=None):
        self._equal = equal or operator.eq
        self._value = initial_value
        self._dep = tracker().dependency()

    def value(self):
        if tracker().active:
            self._dep()
        return self._value

    def value(self, v):
        if not self._equal(self._value, v):
            self._value = v
            self._dep.changed()
