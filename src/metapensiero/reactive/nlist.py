# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- namedlist subclass
# :Created:   mer 03 feb 2016 14:55:20 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Alberto Berti
#

import operator

import namedlist

from . import get_tracker, undefined


class ReactiveNamedListMixin:
    """A namedlist mixin to let it support reactiveness"""

    def __init__(self, *args, **kwargs):
        self._deps = {}
        super().__init__(*args, **kwargs)

    def __getattribute__(self, name):
        fields = super().__getattribute__('_fields')
        if name in fields:
            tracker = get_tracker()
            deps = super().__getattribute__('_deps')
            if name not in deps:
                deps[name] = tracker.dependency()
            deps[name].depend()
        return super().__getattribute__(name)

    def __setattr__(self, name, new):
        fields = super().__getattribute__('_fields')
        if name in fields:
            try:
                old = super().__getattribute__(name)
            except AttributeError:
                old = undefined
            res = super().__setattr__(name, new)
            deps = super().__getattribute__('_deps')
            if name in deps:
                eq = super().__getattribute__('_field_eq')
                if old is undefined or not eq(old, new):
                    deps[name].changed()
        else:
            res = super().__setattr__(name, new)
        return res

    def _field_eq(self, old, new):
        return operator.eq(old, new)


def reactivenamedlist(name, *args, **kwargs):
    "Coerce a :class:`namedlist` to be reactive."
    nlist = namedlist.namedlist('_nl_' + name, *args, **kwargs)
    rnl = type(str(name), (ReactiveNamedListMixin, nlist,), {})
    return rnl


__all__ = ('reactivenamedlist',)
