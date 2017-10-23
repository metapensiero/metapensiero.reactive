# -*- coding: utf-8 -*-
# :Project:  metapensiero.reactive -- basic reactive value implementation
# :Created:    mar 26 gen 2016 19:23:55 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
#

import functools
import logging
import operator

from weakref import WeakKeyDictionary

from . import undefined
from .base import Tracked
from .exception import ReactiveError

logger = logging.getLogger(__name__)


class Value(Tracked):
    """A simple reactive value container to demonstrate how all this
    package works.

    It works as a single value container or as a class descriptor or as a
    function or method decorator.

    When used as a single value container, the value can be get/set using its
    ``value`` member or by calling the `Value` instance itself, passing a
    parameter will set its value.

    When used as a class descriptor it can be used like normal instance value
    member.

    When used as a function or method decorator, it will use the
    function/method to calculate its value and will work as a single value
    container in the case of function decoration and like a normal instance
    value member in the case of method decoration.

    When a Value's value is accessed, a dependency is triggered.
    """

    def __init__(self, generator=undefined,  initial_value=undefined,
                 equal=None, always_recompute=False, *, tracker=None):
        super().__init__(tracker=tracker)
        self._equal = equal or operator.eq
        self._descriptor_initialized = False
        self._single_value_initialized = False
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
        self._always_recompute = always_recompute

    def _init_descriptor_environment(self):
        """There's no way to distinguish between description and simple
        generator mode, so the initialization of the necessary
        per-instance mappings is done at the first __get__
        execution.
        """
        self._dep = WeakKeyDictionary()
        self._value = WeakKeyDictionary()
        self._comp = WeakKeyDictionary()
        self._descriptor_initialized = True

    def _init_single_value_environment(self):
        self._dep = self.tracker.dependency()
        self._single_value_initialized = True

    def _auto(self, instance, generator, comp=None):
        if instance:
            self._set_instance_value(instance, generator(instance))
        else:
            self.value = generator()

    def _get_value(self, instance=None):
        if self.tracker.active:
            dep = self._get_member('dep', instance)
            if dep is undefined or dep is None:
                dep = self.tracker.dependency()
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
        if not self._single_value_initialized:
            self._init_single_value_environment()
        if self._generator:
            self._trigger_generator()
        return self._get_value()

    @value.setter
    def value(self, new):
        old = self._value
        self._value = new
        if not self._single_value_initialized:
            self._init_single_value_environment()
        if not ((old is undefined) or self._equal(old, new)):
            self._dep.changed()

    def _set_instance_value(self, instance, new):
        old = self._value.get(instance, undefined)
        self._value[instance] = new
        if not ((old is undefined) or self._equal(old, new)):
            if instance not in self._dep:
                self._dep[instance] = self.tracker.dependency()
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
            tracker = self.tracker
            comp = self._get_member('comp', instance)
            if comp is undefined or comp is None:
                func = functools.partial(self._auto, instance, self._generator)
                comp = tracker.reactive(func, with_parent=False)
                if not self._always_recompute:
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
            raise ReactiveError("Cannot set the value in a descriptor defined"
                                " with generator function")
        return self._set_instance_value(instance, value)

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
        if not self._descriptor_initialized:
            self._init_descriptor_environment()
        self.stop(instance)

    def _comp_recompute_guard(self, instance, comp):
        """Compute guard to halt recalculation if the value of a certain
        instance has no dependent computations."""
        dep = self._get_member('dep', instance)
        return dep and (dep is not undefined) and dep.has_dependents
