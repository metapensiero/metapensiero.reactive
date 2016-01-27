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

from . import tracker

logger = logging.getLogger(__name__)

undefined = object()

class Value(object):
    """A simple reactive value container to demonstrate how all this
    package works.
    """

    def __init__(self, initial_value=undefined, equal=None):
        self._equal = equal or operator.eq
        self._value = initial_value
        self._dep = tracker().dependency()

    @property
    def value(self):
        if tracker().active:
            self._dep()
        return self._value

    @value.setter
    def value(self, v):
        if not self._equal(self._value, v):
            self._value = v
            self._dep.changed()

    def __call__(self, v=undefined):
        if v is not undefined:
            self.value = v
        else:
            return self.value
