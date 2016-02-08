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

    def __init__(self, generator=undefined,  initial_value=undefined,
                 equal=None):
        self._equal = equal or operator.eq
        self._tracker = t = get_tracker()
        self._descriptor_initialized = False
        if callable(generator):
            # suppose it's used as a method decorator
            self._generator = generator
            self._value = initial_value
        elif generator is not undefined:
            self._generator = None
            self._value = generator
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

    def _get_value(self, instance=None):
        if self._tracker.active:
            dep = self._get_member('dep', instance)
            if dep is undefined or dep is None:
                dep =  self._tracker.dependency()
                self._set_member('dep', dep, instance)
            dep.depend()
        value = self._get_member('value', instance)
        if self._generator and value is undefined:
            raise ReactiveError("Value hasn't been calculated yet..why?")
        elif not self._generator and value is undefined:
            if instance:
                # access via __get__
                raise AttributeError("Value is undefined")
            else:
                raise ValueError('You have to set a value first')
        return value

    @property
    def value(self):
        if self._generator:
            self._trigger_generator()
        return self._get_value()

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

    def _get_member(self, name, instance=None):
        member = getattr(self, '_' + name)
        if instance:
            member = member.get(instance, undefined)
        return member

    def _set_member(self, name, value, instance=None):
        if instance:
            member = getattr(self, '_' + name)
            member[instance] = value
        else:
            setattr(self, '_' + name, value)

    def _trigger_generator(self, instance=None):
        if self._generator:
            tracker = self._tracker
            func = functools.partial(self._auto, instance, self._generator)
            comp = self._get_member('comp', instance)
            if comp is undefined or comp is None:
                comp = tracker.reactive(func, with_parent=False)
                comp.guard = functools.partial(
                    self._comp_recompute_guard, instance
                )
                self._set_member('comp', comp, instance)
            if comp.invalidated:
                comp._recompute()

    def __call__(self, v=undefined):
        if v is not undefined:
            self.value = v
        else:
            return self.value

    def __get__(self, instance, owner):
        if not self._descriptor_initialized:
            self._init_descriptor_environment()
        if self._generator:
            self._trigger_generator(instance)
        return self._get_value(instance)

    def __set__(self, instance, value):
        if not self._descriptor_initialized:
            self._init_descriptor_environment()
        if self._generator:
            raise ReactiveError("Cannot set the value in a descriptor defined with"
                                " generator function")
        return self._set_instance_value(instance)

    def stop(self, instance=None):
        if self._generator:
            if instance:
                comp = self._comp.pop(instance, None)
            else:
                comp = self._comp
                self._comp = None
            if comp:
                comp.stop()
            else:
                if instance:
                    self._value[instance] = undefined
                else:
                    self.value = undefined

    def invalidate(self, instance=None):
        if self._generator:
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

    def __delete__(self, instance):
        self.invalidate(instance)

    def _comp_recompute_guard(self, instance, comp):
        dep = self._get_member('dep', instance)
        return dep and (dep is not undefined) and dep.has_dependents
