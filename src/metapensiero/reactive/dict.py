# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- reactive dict object
# :Created:   ven 27 gen 2017 02:32:41 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2017 Alberto Berti
#

import collections
from functools import partial
import logging
import operator

from .dependency import EventDependency, StopFollowingValue
from . import get_tracker


logger = logging.getLogger(__name__)


class Undefined:

    def __bool__(self):
        return False

undefined = Undefined()
missing = Undefined()


class ReactiveContainerBase:
    """Base class for reactive containers. It initializes and exports three kind
    of dependencies to track changes to either immutable values, reactive
    values or changes in the structure. It also exposes an `all` member to
    track all of them.
    """

    UNDEFINED = undefined

    def __init__(self, equal=None, tracker=None):
        self._tracker = tracker or get_tracker()
        self._equal = equal or operator.eq
        self._all_reactives = EventDependency(self._tracker)
        self._all_immutables = EventDependency(self._tracker)
        self._all_values = EventDependency(self._tracker)
        self._all_values.follow(self._all_reactives, self._all_immutables)
        self._structure = EventDependency(self._tracker)
        self._all_structures = EventDependency(self._tracker)
        self._all = EventDependency(self._tracker)
        self._all.follow(self._all_structures, self._all_reactives,
                         self._all_immutables)
        self._all_structures.follow(self._structure)

    def _build_follow_transformation(self, rvalue, **kwargs):
        return None

    def _follow_reactive(self, rvalue, stop=False, **kwargs):
        """Follow the events of another reactive container. Or stop following if the
        `stop` parameter is ``True``.
        """
        assert isinstance(rvalue, ReactiveContainerBase), \
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
            if stop:
                getattr(local_dep, mname)(follow_dep)
            else:
                getattr(local_dep, mname)(follow_dep,
                    ftrans=self._build_follow_transformation(rvalue, **kwargs))

    def _is_immutable(self, value):
        return isinstance(value, collections.abc.Hashable)

    @property
    def all(self):
        """Returns the dependency that tracks all the changes."""
        return self._all

    @property
    def immutables(self):
        """Returns the dependency that track the changes to all the immutable
        values."""
        return self._all_immutables

    @property
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
        self._key_dependencies = {}
        ReactiveContainerBase.__init__(self, equal, tracker)
        collections.UserDict.__init__(self, *args, **kwargs)

    def __contains__(self, key):
        self._structure.depend()
        return super().__contains__(key)

    def __delitem__(self, key):
        if key in self.data:
            oldv = self.data[key]
        else:
            oldv = missing
        super().__delitem__(key)
        self._change(key, oldv, missing)

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self._key_dependencies[key].depend()
        return value

    def __iter__(self):
        self._structure.depend()
        return super().__iter__()

    def __setitem__(self, key, value):
        if key in self.data:
            oldv = self.data[key]
        else:
            oldv = missing
        super().__setitem__(key, value)
        self._change(key, oldv, value)

    def _build_follow_transformation(self, rvalue, *, key=None):
        return partial(self._follow_transform, rvalue, key)

    def _change(self, key, oldv, newv):
        """Analyze changed values and trigger changed events on dependencies."""
        if oldv is missing:
            # add
            vdep = EventDependency(self._tracker)
            self._key_dependencies[key] = vdep
            if self._is_immutable(newv):
                self._all_immutables.follow(vdep)
            else:
                self._follow_reactive(newv, key=key)
            change = (operator.setitem, (self, key, newv))
            vdep.changed(change)
            self._structure.changed(change)
        elif newv is missing:
            # delete
            vdep = self._key_dependencies.pop(key)
            change = (operator.delitem, (self, key))
            vdep.changed(change)
            self._structure.changed(change)
            if self._is_immutable(oldv):
                self._all_immutables.unfollow(vdep)
            else:
                self._follow_reactive(oldv, stop=True)
        else:
            # change
            is_immu = self._is_immutable(newv)
            if oldv is newv or (is_immu and self._equal(oldv, newv)):
                return
            was_reactive = isinstance(oldv, ReactiveContainerBase)
            is_reactive = isinstance(newv, ReactiveContainerBase)

            dep = self._key_dependencies[key]
            if was_reactive:
                self._follow_reactive(oldv, stop=True)
            if is_reactive:
                self._follow_reactive(newv)
            dep.changed((operator.setitem, (self, key, newv)))

    def _follow_transform(self, followed, key,  *changes):
        change = (operator.setitem, (self, key, followed))
        return (change,) + changes

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


class ReactiveChainMap(collections.ChainMap, ReactiveContainerBase):
    """A collections.ChainMap subclass made of ReactiveDicts.

    As of now it lacks the filtering of changes in structure when the key is
    already present in a dict at a lower level.
    """

    def __init__(self, *maps, equal=None, tracker=None):
        ReactiveContainerBase.__init__(self, equal, tracker)
        if maps:
            maps = [m if type(m) is ReactiveDict else ReactiveDict(m) for m in
                    maps]
        else:
            maps = [ReactiveDict()]
        collections.ChainMap.__init__(self, *maps)
        self.setup_follow(*maps)

    def _build_follow_transformation(self, rvalue, **kwargs):
        return partial(self._follow_map, rvalue)

    def _follow_map(self, map, *changes):
        fg_map = self.maps[0]
        root, *inner = changes
        action, (m, k, *v) = root
        assert m is map
        assert m in self.maps
        if map is not fg_map:
            if k in fg_map:
                raise StopFollowingValue()
        # reassemble root using this instance as the object
        root = (action, (self, k) + tuple(v))
        changes = (root,) + tuple(inner)
        return changes

    def setup_follow(self, *maps):
        for m in maps:
            self._follow_reactive(m)
