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
from .exception import ReactiveError

logger = logging.getLogger(__name__)

undefined = object()


class Value(object):
    """A simple reactive value container to demonstrate how all this
    package works.
    """

    def __init__(self, initial_value=undefined, equal=None):
        self._equal = equal or operator.eq
        self._tracker = t = get_tracker()
        self._descriptor_initialized = False
        if callable(initial_value):
            # suppose it's used as a method decorator
            self._generator = initial_value
            self._value = undefined
        else:
            self._generator = None
            self._value = initial_value
        self._comp = None
        self._dep = t.dependency()

    def _init_descriptor_environment(self):
        """There's no way to distinguis between description and simple
        generator mode, so the initialization of the necessary
        per-instance mappings is done at the first __get__
        execution.
        """
        self._dep = WeakKeyDictionary()
        self._value = WeakKeyDictionary()
        self._comp = WeakKeyDictionary()
        self._descriptor_initialized = True

    def _auto(self, instance, generator, comp=None):
        if instance:
            self._set_instance_value(instance, generator(instance))
        else:
            self.value = generator()

    def _get_instance_value(self, instance):
        if self._tracker.active:
            if instance not in self._dep:
                self._dep[instance] = self._tracker.dependency()
            self._dep[instance].depend()
        if instance not in self._value:
            raise ReactiveError("Value hasn't been calculated yet..why?")
        return self._value[instance]

    @property
    def value(self):
        tracker = self._tracker
        if self._generator:
            func = functools.partial(self._auto, None, self._generator)
            if tracker.active:
                comp = self._comp
                if not comp:
                    comp = self._comp = tracker.reactive(func, with_parent=False)
                    comp.guard = functools.partial(
                        self._comp_recompute_guard, None
                    )
                if comp.invalidated:
                    comp._recompute()
            else:
                if self._value is undefined:
                    func()
        if tracker.active:
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
        if not self._descriptor_initialized:
            self._init_descriptor_environment()
        tracker = self._tracker
        func = functools.partial(self._auto, instance, self._generator)
        if tracker.active:
            comp = self._comp.get(instance)
            if not comp:
                comp = self._comp[instance] = self._tracker.reactive(func,
                                                                     with_parent=False)
                comp.guard = functools.partial(
                    self._comp_recompute_guard, instance
                )
            if comp.invalidated:
                comp._recompute()
        else:
            if not (instance in self._value):
                func()
        return self._get_instance_value(instance)

    def invalidate(self, instance=None):
        if instance:
            comp = self._comp.get(instance)
        else:
            comp = self._comp
        if comp:
            comp.invalidate()
        else:
            if instance:
                self._value[instance] = undefined
            else:
                self.value = undefined

    def __del__(self, instance, owner):
        self.invalidate(instance)

    def _comp_recompute_guard(self, instance, comp):
        if instance:
            dep = self._dep.get(instance)
        else:
            dep = self._dep
        return dep and dep.has_dependents
