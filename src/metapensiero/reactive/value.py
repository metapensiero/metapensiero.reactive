# -*- coding: utf-8 -*-
# :Project:  metapensiero.reactive -- basic reactive value implementation
# :Created:    mar 26 gen 2016 19:23:55 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
#

from __future__ import unicode_literals, absolute_import

import six

import functools
import logging
import operator

from weakref import WeakKeyDictionary

from . import get_tracker

logger = logging.getLogger(__name__)

undefined = object()


class Value(object):
    """A simple reactive value container to demonstrate how all this
    package works.
    """

    def __init__(self, initial_value=undefined, equal=None):
        self._equal = equal or operator.eq
        self._tracker = t = get_tracker()
        if callable(initial_value):
            # suppose it's used as a method decorator
            self._generator = initial_value
            self._dep = WeakKeyDictionary()
            self._comp = WeakKeyDictionary()
            self._value = WeakKeyDictionary()
        else:
            self._dep = t.dependency()
            self._value = initial_value
            self._comp = None

    def _auto(self, instance, generator, comp):
        self._set_instance_value(instance, generator(instance))

    def _get_instance_value(self, instance):
        if self._tracker.active:
            if instance not in self._dep:
                self._dep[instance] = self._tracker.dependency()
            self._dep[instance].depend()
        if instance not in self._value:
            raise RuntimeError("Value hasn't been calculated yet..why?")
        return self._value[instance]

    @property
    def value(self):
        if self._tracker.active:
            self._dep.depend()
        if self._value is undefined:
            raise ValueError('You have to set a value first')
        else:
            return self._value

    @value.setter
    def value(self, new):
        old = self._value
        self._value = new
        if not ((old is undefined) or self._equal(old, new)):
            self._dep.changed()

    def _set_instance_value(self, instance, new):
        old = self._value.get(instance, undefined)
        self._value[instance] = new
        if not ((old is undefined) or self._equal(old, new)):
            if instance not in self._dep:
                self._dep[instance] = self._tracker.dependency()
            self._dep[instance].changed()

    def __call__(self, v=undefined):
        if v is not undefined:
            self.value = v
        else:
            return self.value

    def __get__(self, instance, owner):
        comp = self._comp.get(instance)
        if not comp:
            self._comp[instance] = self._tracker.reactive(
                functools.partial(self._auto, instance, self._generator)
            )
        return self._get_instance_value(instance)
