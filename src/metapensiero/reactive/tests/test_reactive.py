# -*- coding: utf-8 -*-
# :Project:  metapensiero.reactive -- tests
# :Created:    mer 27 gen 2016 14:56:03 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
#

from metapensiero import reactive

def test_computation_invalidation(env):
    t = env.tracker
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
    env.wait_for_flush()
    assert results == dict(autorun=["A sample V", "A sample V"], comp_invalidate=True)
    assert comp.invalidated is False
    assert t.active is False
    assert t.current_computation is None
    assert len(dep._dependents) == 1

def test_computation_stopping(env):
    t = env.tracker
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
    env.wait_for_flush()
    assert results == dict(autorun=["A sample V"], comp_invalidate=False)
    assert comp.invalidated is True
    assert t.active is False
    assert t.current_computation is None
    assert len(dep._dependents) == 0

def test_value(env):

    t = env.tracker
    v = reactive.Value(1)

    results = dict(autorun=[])

    def autorun(comp):
        assert t.active is True
        assert t.current_computation is comp
        results['autorun'].append(v.value)


    assert v.value == 1
    assert results == dict(autorun=[])
    comp = t.reactive(autorun)
    assert results == dict(autorun=[1])
    v.value = 2
    env.wait_for_flush()
    assert results == dict(autorun=[1,2])


def test_reactivenamedlist(env):

    t = env.tracker
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
    env.wait_for_flush()
    assert results == [(10, 15), (20, 15)]
    p.x = 20
    p.y = 15
    env.wait_for_flush()
    assert results == [(10, 15), (20, 15)]
    p.y = 25
    env.wait_for_flush()
    assert results == [(10, 15), (20, 15), (20, 25)]

def test_reactive_property(env):

    t = env.tracker
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
    env.wait_for_flush()
    assert results == dict(ext_autorun=[True], int_autorun=[True, True])
    r.text = 'Just bar in here'
    env.wait_for_flush()
    assert results == dict(ext_autorun=[True, False],
                           int_autorun=[True, True, False])

def test_value_with_nested_autorun(env):

    import math

    def is_prime(n):
        "A simple prime number checker"
        if n % 2 == 0 and n > 2:
            return False
        return all(n % i for i in range(3, int(math.sqrt(n)) + 1, 2))

    t = env.tracker

    results = dict(autorun=[], autorun2=[])

    def autorun():
        res = v()
        results['autorun'].append(v())
        return is_prime(res)

    def autorun2(comp):
        results['autorun2'].append(is_v_prime())

    assert results == dict(autorun=[], autorun2=[])
    v = reactive.Value(1)
    is_v_prime = reactive.Value(autorun)
    assert v() == 1
    assert results == dict(autorun=[], autorun2=[])
    is_v_prime()
    assert results == dict(autorun=[1], autorun2=[])
    comp = t.reactive(autorun2)
    assert results == dict(autorun=[1], autorun2=[True])
    assert is_v_prime.value == True
    v.value = 2
    env.wait_for_flush()
    assert results == dict(autorun=[1, 2], autorun2=[True])
    assert is_v_prime.value == True
    v.value = 2
    env.wait_for_flush()
    assert results == dict(autorun=[1,  2], autorun2=[True])
    assert is_v_prime.value == True
    v.value = 4
    env.wait_for_flush()
    assert results == dict(autorun=[1, 2, 4], autorun2=[True, False])
    assert is_v_prime.value == False
    assert len(v._dep._dependents) == 1
    assert len(is_v_prime._dep._dependents) == 1

def test_value_with_nested_autorun_stop_non_directly_dependent(env):

    import math

    def is_prime(n):
        "A simple prime number checker"
        if n % 2 == 0 and n > 2:
            return False
        return all(n % i for i in range(3, int(math.sqrt(n)) + 1, 2))

    t = env.tracker

    results = dict(autorun=[], autorun2=[])

    def autorun():
        res = v.value
        results['autorun'].append(v.value)
        return is_prime(res)

    def autorun2(comp):
        results['autorun2'].append(is_v_prime.value)

    assert results == dict(autorun=[], autorun2=[])
    v = reactive.Value(1)
    is_v_prime = reactive.Value(autorun)
    assert v.value == 1
    assert results == dict(autorun=[], autorun2=[])
    is_v_prime.value
    assert results == dict(autorun=[1], autorun2=[])
    comp = t.reactive(autorun2)
    assert results == dict(autorun=[1], autorun2=[True])
    assert is_v_prime.value == True

    assert len(v._dep._dependents) == 1
    assert len(is_v_prime._dep._dependents) == 1

    comp.stop()

    assert len(v._dep._dependents) == 1
    assert len(is_v_prime._dep._dependents) == 0

    v.value = 4

    env.wait_for_flush()
    assert results == dict(autorun=[1], autorun2=[True])
    # the reading here will recalculate the already invalidated
    # computation of is_v_prime
    assert is_v_prime.value == False

def test_value_with_nested_autorun_stop_dependent(env):

    import math

    def is_prime(n):
        "A simple prime number checker"
        if n % 2 == 0 and n > 2:
            return False
        return all(n % i for i in range(3, int(math.sqrt(n)) + 1, 2))

    t = env.tracker

    results = dict(autorun=[], autorun2=[])

    def autorun():
        res = v.value
        results['autorun'].append(v.value)
        return is_prime(res)

    def autorun2(comp):
        results['autorun2'].append(is_v_prime.value)

    assert results == dict(autorun=[], autorun2=[])
    v = reactive.Value(1)
    is_v_prime = reactive.Value(autorun)
    assert v.value == 1
    assert results == dict(autorun=[], autorun2=[])
    comp = t.reactive(autorun2)
    assert results == dict(autorun=[1], autorun2=[True])
    assert is_v_prime.value == True

    assert len(v._dep._dependents) == 1
    assert len(is_v_prime._dep._dependents) == 1

    comp.stop()

    assert len(v._dep._dependents) == 1
    assert len(is_v_prime._dep._dependents) == 0

    v.value = 4

    env.wait_for_flush()
    assert results == dict(autorun=[1], autorun2=[True])
    # the reading here will recalculate the already invalidated
    # computation of is_v_prime
    assert is_v_prime.value == False

def test_value_with_nested_autorun_stop_two_dependents(env):

    import math

    def is_prime(n):
        "A simple prime number checker"
        if n % 2 == 0 and n > 2:
            return False
        return all(n % i for i in range(3, int(math.sqrt(n)) + 1, 2))

    t = env.tracker

    results = dict(autorun=[], autorun2=[], autorun3=[])

    def autorun():
        res = v.value
        results['autorun'].append(v.value)
        return is_prime(res)

    def autorun2(comp):
        results['autorun2'].append(is_v_prime.value)

    def autorun3(comp):
        results['autorun3'].append(is_v_prime.value)


    assert results == dict(autorun=[], autorun2=[], autorun3=[])
    v = reactive.Value(1)
    is_v_prime = reactive.Value(autorun)
    assert v.value == 1
    assert results == dict(autorun=[], autorun2=[], autorun3=[])
    comp = t.reactive(autorun2)
    assert results == dict(autorun=[1], autorun2=[True], autorun3=[])
    comp2 = t.reactive(autorun3)
    assert results == dict(autorun=[1], autorun2=[True], autorun3=[True])
    assert is_v_prime.value == True

    assert len(v._dep._dependents) == 1
    assert len(is_v_prime._dep._dependents) == 2

    comp.stop()

    assert len(v._dep._dependents) == 1
    assert len(is_v_prime._dep._dependents) == 1

    v.value = 4
    env.wait_for_flush()

    assert results == dict(autorun=[1, 4], autorun2=[True],
                           autorun3=[True, False])
    assert is_v_prime.value == False

    comp2.stop()

    assert len(v._dep._dependents) == 1
    assert len(is_v_prime._dep._dependents) == 0

    v.value = 5
    env.wait_for_flush()

    assert results == dict(autorun=[1, 4], autorun2=[True], autorun3=[True, False])
    assert is_v_prime._comp.invalidated is True

    comp2 = t.reactive(autorun3)
    assert results == dict(autorun=[1, 4, 5], autorun2=[True], autorun3=[True, False, True])
    assert is_v_prime._comp.invalidated is False

    v.value = 7
    env.wait_for_flush()

    assert results == dict(autorun=[1, 4, 5, 7], autorun2=[True], autorun3=[True, False, True])
    assert is_v_prime._comp.invalidated is False

    v.value = 8
    env.wait_for_flush()

    assert results == dict(autorun=[1, 4, 5, 7, 8], autorun2=[True], autorun3=[True, False, True, False])
    assert is_v_prime._comp.invalidated is False

    comp2.stop()

    assert results == dict(autorun=[1, 4, 5, 7, 8], autorun2=[True], autorun3=[True, False, True, False])
    assert is_v_prime._comp.invalidated is False

    v.value = 3
    env.wait_for_flush()

    assert results == dict(autorun=[1, 4, 5, 7, 8], autorun2=[True], autorun3=[True, False, True, False])
    assert is_v_prime._comp.invalidated is True
