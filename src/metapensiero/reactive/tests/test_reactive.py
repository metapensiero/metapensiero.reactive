# -*- coding: utf-8 -*-
# :Project:  metapensiero.reactive -- tests
# :Created:    mer 27 gen 2016 14:56:03 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
#

from metapensiero import reactive

def test_computation_invalidation():
    t = reactive.get_tracker()
    dep = t.dependency()
    v = "A sample V"
    results = dict(autorun=[], comp_invalidate=False)

    def dep_func():
        dep()
        return v

    def autorun(comp):
        assert t.active is True
        assert t.current_computation is comp
        results['autorun'].append(dep_func())

    def _before_flush_cback(computations):
        results['comp_invalidate'] = comp.invalidated

    comp = t.reactive(autorun)

    assert results == dict(autorun=["A sample V"], comp_invalidate=False)
    assert comp.invalidated is False
    assert t.active is False
    assert t.current_computation is None
    assert len(dep._dependents) == 1
    t.flusher.on_before_flush.connect(_before_flush_cback)
    assert len(dep._dependents) == 1
    dep.changed()
    assert results == dict(autorun=["A sample V", "A sample V"], comp_invalidate=True)
    assert comp.invalidated is False
    assert t.active is False
    assert t.current_computation is None
    assert len(dep._dependents) == 1

def test_computation_stopping():
    t = reactive.get_tracker()
    dep = t.dependency()
    v = "A sample V"
    results = dict(autorun=[], comp_invalidate=False)

    def dep_func():
        dep()
        return v

    def autorun(comp):
        assert t.active is True
        assert t.current_computation is comp
        results['autorun'].append(dep_func())

    comp = t.reactive(autorun)

    assert results == dict(autorun=["A sample V"], comp_invalidate=False)
    assert comp.invalidated is False
    assert t.active is False
    assert t.current_computation is None
    assert len(dep._dependents) == 1
    comp.stop()
    assert len(dep._dependents) == 0
    dep.changed()
    assert results == dict(autorun=["A sample V"], comp_invalidate=False)
    assert comp.invalidated is True
    assert t.active is False
    assert t.current_computation is None
    assert len(dep._dependents) == 0

def test_value():

    t = reactive.get_tracker()
    v = reactive.Value(1)

    results = dict(autorun=[])

    def autorun(comp):
        assert t.active is True
        assert t.current_computation is comp
        results['autorun'].append(v())

    assert v() == 1
    assert results == dict(autorun=[])
    comp = t.reactive(autorun)
    assert results == dict(autorun=[1])
    v(2)
    assert results == dict(autorun=[1,2])


def test_reactivenamedlist():

    t = reactive.get_tracker()
    Point = reactive.namedlist('Point', 'x y', default=0)
    p = Point(10, 15)
    results = []

    def autorun(comp):
        results.append((p.x, p.y))

    assert results == []
    comp = t.reactive(autorun)
    assert len(p._deps) == 2
    assert results == [(10, 15)]
    p.x = 20
    assert results == [(10, 15), (20, 15)]
    p.x = 20
    p.y = 15
    assert results == [(10, 15), (20, 15)]
    p.y = 25
    assert results == [(10, 15), (20, 15), (20, 25)]

def test_reactive_property():

    t = reactive.get_tracker()
    results = dict(ext_autorun=[], int_autorun=[])

    class MyReactive(object):

        def __init__(self, text):
            self._text = text
            self._int_dep = t.dependency()

        @property
        def text(self):
            self._int_dep.depend()
            return self._text

        @text.setter
        def text(self, new):
            old = self._text
            self._text = new
            if old != new:
                self._int_dep.changed()

        @reactive.Value
        def foo_flag(self):
            v = 'foo' in self.text
            results['int_autorun'].append(v)
            return v

    r = MyReactive('No foo in here')

    def ext_autorun(comp):
        results['ext_autorun'].append(r.foo_flag)

    assert results == dict(ext_autorun=[], int_autorun=[])
    comp = t.reactive(ext_autorun)
    assert results == dict(ext_autorun=[True], int_autorun=[True])
    r.text = 'Yes, foo is here'
    assert results == dict(ext_autorun=[True], int_autorun=[True, True])
    r.text = 'Just bar in here'
    assert results == dict(ext_autorun=[True, False],
                           int_autorun=[True, True, False])
