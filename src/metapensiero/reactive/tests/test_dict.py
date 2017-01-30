# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- tests
# :Created:   ven 27 gen 2017 19:51:14 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2017 Alberto Berti
#

import pytest

from metapensiero import reactive


def test_dict_basic(env):
    d = reactive.ReactiveDict()
    all = env.run_comp(lambda c: d.all.depend())
    struct = env.run_comp(lambda c: d.structure.depend())
    imm = env.run_comp(lambda c: d.immutables.depend())
    foo_setter = env.run_comp(lambda c: d.__setitem__('foo', 'bar'))
    foo = env.run_comp(lambda c: d['foo'])
    assert d['foo'] == 'bar'
    assert all.invalidated
    assert struct.invalidated
    assert imm.invalidated
    assert not foo_setter.invalidated
    assert not foo.invalidated
    d['foo'] = 'zoo'
    assert foo.invalidated
    assert not foo_setter.invalidated
    env.wait_for_flush()
    assert not all.invalidated
    assert not struct.invalidated
    assert not imm.invalidated
    assert not foo_setter.invalidated
    assert not foo.invalidated
    d['foo'] = 'zoo'
    assert not all.invalidated
    assert not struct.invalidated
    assert not imm.invalidated
    assert not foo_setter.invalidated
    assert not foo.invalidated
    d['foo'] = 'bar'
    assert all.invalidated
    assert not struct.invalidated
    assert imm.invalidated
    assert not foo_setter.invalidated
    assert foo.invalidated
    env.wait_for_flush()
    assert not all.invalidated
    assert not struct.invalidated
    assert not imm.invalidated
    assert not foo_setter.invalidated
    assert not foo.invalidated
    del d['foo']
    assert 'foo' not in d
    with pytest.raises(KeyError):
        d['foo']
    assert all.invalidated
    assert struct.invalidated
    assert imm.invalidated
    assert not foo_setter.invalidated
    assert foo.invalidated
