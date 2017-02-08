# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- tests
# :Created:   ven 27 gen 2017 19:51:14 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2017 Alberto Berti
#

import asyncio
import operator

import pytest

from metapensiero import reactive
from metapensiero.reactive.dependency import Sink

@pytest.fixture(params=(reactive.ReactiveDict, reactive.ReactiveChainMap))
def dict_cls(request):
    return request.param


def test_dict_basic(env, dict_cls):
    d = dict_cls()
    all = env.run_comp(lambda c: d.all.depend())
    sink = d.all.sink()
    sink.start()
    struct_sink = d.structure.sink()
    struct_sink.start()
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

    assert list(struct_sink) == [((operator.setitem, (d, 'foo', 'bar')),),
                                 ((operator.delitem, (d, 'foo')),)]
    assert list(sink) == [((operator.setitem, (d, 'foo', 'bar')),),
                          ((operator.setitem, (d, 'foo', 'bar')),),
                          ((operator.setitem, (d, 'foo', 'zoo')),),
                          ((operator.setitem, (d, 'foo', 'bar')),),
                          ((operator.delitem, (d, 'foo')),),
                          ((operator.delitem, (d, 'foo')),)]

    sink.data.clear()
    struct_sink.data.clear()
    o = dict_cls()
    o.update(dict(pollo=2, polletto='a'))
    d['other'] = o
    o['pollo'] = 20
    o['zoo'] = 'b'

    sink_res = [
        ((operator.setitem, (d, 'other', o)),),

        ((operator.setitem, (d, 'other', o)),
         (operator.setitem, (o, 'pollo', 20))),

        ((operator.setitem, (d, 'other', o)),
         (operator.setitem, (o, 'zoo', 'b'))),

        ((operator.setitem, (d, 'other', o)),
         (operator.setitem, (o, 'zoo', 'b')))
    ]

    assert list(sink) == sink_res

    assert list(struct_sink) == [
        ((operator.setitem, (d, 'other', o)),),
        ((operator.setitem, (d, 'other', o)),
         (operator.setitem, (o, 'zoo', 'b')))]


    sink.data.clear()
    struct_sink.data.clear()
    del d['other']

    # further changes to 'o' do not affect the stream
    o['pollo'] = 5

    assert list(sink) == [
        ((operator.delitem, (d, 'other')),)]

    assert list(struct_sink) == [
        ((operator.delitem, (d, 'other')),)]

    # teardown
    all.stop()
    struct.stop()
    imm.stop()
    foo_setter.stop()
    foo.stop()


def test_chaindict():

    d = reactive.ReactiveChainMap()
    dd = d.new_child()

    sink = dd.all.sink()
    sink.start()
    struct_sink = dd.structure.sink()
    struct_sink.start()

    d['foo'] = 'bar'

    dd['foo'] = 'zoo'
    d['foo'] = 'coo'
    assert dd['foo'] == 'zoo'
    sink_res = [((operator.setitem, (dd, 'foo', 'bar')),),
                ((operator.setitem, (dd, 'foo', 'bar')),),
                ((operator.setitem, (dd, 'foo', 'zoo')),),
                ((operator.setitem, (dd, 'foo', 'zoo')),),]
    assert list(sink) == sink_res
    assert list(sink)[0][0][1][0] is dd
