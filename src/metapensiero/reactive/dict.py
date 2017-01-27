# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- reactive dict object
# :Created:   ven 27 gen 2017 02:32:41 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Alberto Berti
#

import abc
import collections
import logging
import operator

from .exception import ReactiveError
from .dependency import Dependency
from . import get_tracker


logger = logging.getLogger(__name__)

undefined = object()


class ReactiveContainerBase:
    """Base class for reactive containers. It initializes and exports three kind
    of dependencies to track changes to either immutable values, reactive values
    or changes in the structure. It also exposes an `all` member to track all of
    them."""

    def __init__(self, equal=None, tracker=None):
        self._tracker = tracker or get_tracker()
        self._equal or operator.eq
        self._all_reactives = Dependency(self._tracker)
        self._all_immutables = Dependency(self._tracker)
        self._all_values = Dependency(self._tracker)
        self._all_values.follow(self._all_reactives, self._all_immutables)
        self._structure = Dependency(self._tracker)
        self._all_structures = Dependency(self._tracker)
        self._all = Dependency(self._tracker)
        self._all.follow(self._all_structures, self._all_reactives,
                         self._all_immutables)
        self._all_structures.follow(self._structure)

    def _follow_reactive(self, rvalue, stop=False):
        """Follow the events of another reactive container. Or stop following if the
        `stop` parameter is ``True``."""
        assert isinstance(rvalue, ReactiveBase), \
            "Containers must be reactive"
        if stop:
            mname = 'unfollow'
        else:
            mname = 'follow'

        for propname, depname in (('immutables', '_all_immutables'),
                                  ('reactives', '_all_reactives'),
                                  ('structure', '_all_structures')):
            local_dep = getattr(self, depname)
            follow_dep = getattr(rvalue, propname)
            getattr(local_dep, mname)(follow_dep)

    def _is_immutable(self, value):
        return isinstance(value, collections.abc.Hashable)

    @property
    def all(self):
        """Returns the dependency that tracks all the changes."""
        return self._all

    @property
    def immutables(self):
        """Returns the dependency that track the changes to all the immutable values."""
        return self._all_immutables

    def reactives(self):
        """Returns a dependency that tracks all the reactive values."""
        return self._all_reactives

    @property
    def structure(self):
        """Returns the dependecy that tracks the changes to the structure."""
        return self._all_structures



class ReactiveDict(collections.UserDict, ReactiveContainerBase):
    """A reactive dictionary. The `structure` dependency here tracks
    addition/deletion of keys. It also connects to contained child reactive
    structure changes."""

    def __init__(self, *args, equal=None, tracker=None, **kwargs):
        collections.UserDict.__init__(self, *args, **kwargs)
        ReactiveContainerBase.__init__(self, equal, tracker)
        self._key_dependencies = {}

    def __contains__(self, key):
        self._structure.depend()
        return super().__contains__(key)

    def __delitem__(self, key):
        if key in self.data:
            oldv = self.data[key]
        else:
            oldv = undefined
        super().__delitem__(key)
        self._change(oldv, undefined)

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self._key_dependencies[key].depend()

    def __iter__(self):
        self._structure.depend()
        return super().__iter__()

    def __setitem__(self, key, value):
        if key in self.data:
            oldv = self.data[key]
        else:
            oldv = undefined
        super().__setitem__(key, value)
        self._change(key, oldv, value)

    def _change(self, key, oldv, newv):
        """Analyze changed values and trigger changed events on dependencies."""
        if oldv is undefined:
            # add
            vdep = Dependency(self._tracker)
            self._key_dependencies[key] = vdep
            if self._is_immutable(newv):
                self._all_immutables.follow(vdep)
            else:
                self._follow_reactive(newv)
            vdep.changed()
            self._structure.changed()
        elif newv is undefined:
            # delete
            vdep = self._key_dependencies.pop(key)
            if self._is_immutable(oldv):
                self._all_immutables.unfollow(vdep)
            else:
                self._follow_reactive(oldv, stop=True)
            vdep.changed()
            self._structure.changed()
        else:
            # change
            is_immu = self._is_immutable(newv)
            if oldv is newv or (is_immu and self._equal(oldv, newv)):
                return
            was_immu = key in self._key_dependencies
            was_reactive = isinstance(oldv, ReactiveBase)
            is_reactive = isinstance(newv, ReactiveBase)

            dep = self._key_dependencies[key]
            if was_reactive:
                self._follow_reactive(oldv, stop=True)
            if is_reactive:
                self._follow_reactive(newv)
            dep.changed()

    def keys(self):
        self._structure.depend()
        return super().keys()

    def values(self):
        self._all_values.depend()
        return super().values()

    def items(self):
        self._structure.depend()
        self._all_values.depend()
        return super().items()
