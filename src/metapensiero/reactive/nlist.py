# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- namedlist subclass
# :Created:   mer 03 feb 2016 14:55:20 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Alberto Berti
#

from __future__ import unicode_literals, absolute_import

import operator

import namedlist

from . import get_tracker


undefined = object()

class ReactiveNamedListMixin(object):
    """A namedlist mixin to let it support reactiveness"""

    def __init__(self, *args, **kwargs):
        self._deps = {}
        super(ReactiveNamedListMixin, self).__init__(*args, **kwargs)

    def __getattribute__(self, name):
        fields = super(ReactiveNamedListMixin, self).__getattribute__('_fields')
        if name in fields:
            tracker = get_tracker()
            deps = super(ReactiveNamedListMixin, self).__getattribute__('_deps')
            if name not in deps:
                deps[name] = tracker.dependency()
            deps[name].depend()
        return super(ReactiveNamedListMixin, self).__getattribute__(name)

    def __setattr__(self, name, new):
        fields = super(ReactiveNamedListMixin, self).__getattribute__('_fields')
        if name in fields:
            try:
                old = super(ReactiveNamedListMixin, self).__getattribute__(name)
            except AttributeError:
                old = undefined
            res = super(ReactiveNamedListMixin, self).__setattr__(name, new)
            deps = super(ReactiveNamedListMixin, self).__getattribute__('_deps')
            if name in deps:
                eq = super(ReactiveNamedListMixin, self).__getattribute__('_field_eq')
                if old is undefined or not eq(old, new):
                    deps[name].changed()
        else:
            res = super(ReactiveNamedListMixin, self).__setattr__(name, new)
        return res

    def _field_eq(self, old, new):
        return operator.eq(old, new)


def reactivenamedlist(name, *args, **kwargs):
    nlist = namedlist.namedlist('_nl_' + name, *args, **kwargs)
    rnl = type(str(name), (ReactiveNamedListMixin, nlist,), {})
    return rnl

__all__ = ('reactivenamedlist',)
