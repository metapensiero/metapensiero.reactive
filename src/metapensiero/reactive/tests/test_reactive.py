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
