.. -*- coding: utf-8 -*-
.. :Project:   metapensiero.reactive -- a unobtrusive and light reactive system
.. :Created:   dom 09 ago 2015 12:57:35 CEST
.. :Author:    Alberto Berti <alberto@metapensiero.it>
.. :License:   GNU General Public License version 3 or later
.. :Copyright: Copyright (C) 2015 Alberto Berti
..

=======================
 metapensiero.reactive
=======================

 :author: Alberto Berti
 :contact: alberto@metapensiero.it
 :license: GNU General Public License version 3 or later

A unobtrusive and light reactive system
=======================================

Goal
----

This package implements a framework for `functional reactive
programming <https://en.wikipedia.org/wiki/Functional_reactive_programming>`_
which wants to be simple to use and extend without imposing complex
concepts of streams, channels and so on that are typical of *dataflow
programming*.

To explain reactive programming just think about a spreadsheet where
you have a value cell and a formula cell. The latter updates
automatically just when it's  appropriate.

This package implement just that. No, wait, not a spreadsheet, but a
way to express that a block of code (a function) that creates a result
(a calculated value) or a *side effect* depends on some other value
so that when the value changes, the block of code is automatically
re-run.

It has been inspired by Javascript `meteor's "tracker" package`__ but
it diverges from in order to be more pythonic.

__ https://github.com/meteor/meteor/tree/devel/packages/tracker

Usage
-----

Let's see a small example:

.. code:: python

  cur_temp_fahrenheit = 40

  def cur_temp_celsius(t_fahrenheit):
      return (t_fahrenheit - 32) / 1.8

  log = []

  def log_temp_celsius():
      log.append(cur_temp_celsius(cur_temp_fahrenheit))

  log_temp_celsius()

  assert log == [4.444444444444445]

This is a small piece of code with a function that converts Fahrenheit
degrees to Celsius and then logs them to a list, but you can think of
it as any kind of side effect.

Now, we suppose that ``cur_temp_fahrenheit`` changes and we want to
log it whenever it does so.

To do that we need to trasform ``cur_temp_fahrenheit`` into a
*reactive* value and have the *tracker* track the dependencies between
that value and the *computation* that uses it. This way, when the
value is changed, our ``log_temp_celsius()`` can be re-run and it will
do its work. So we change the code a bit mostly by using a getter and
a setter to change the temp variable and add some code  when
this happens and then instruct the *tracker* to run the log
function so that it knows what to re-run. Let's see:

.. code:: python

  from metapensiero import reactive

  tracker = reactive.get_tracker()
  dep = tracker.dependency()

  # this is just to handle setting a global var
  cur_temp_fahrenheit = [40]

  def get_temp_f():
      dep.depend()
      return cur_temp_fahrenheit[0]

  def set_temp_f(new):
      if new != cur_temp_fahrenheit[0]:
          dep.changed()
      cur_temp_fahrenheit[0] = new

  def cur_temp_celsius(t_fahrenheit):
      return (t_fahrenheit - 32) / 1.8

  log = []

  def log_temp_celsius(handle):
      log.append(cur_temp_celsius(get_temp_f()))

  handle = tracker.reactive(log_temp_celsius)

  assert log == [4.444444444444445]

  set_temp_f(50)

  assert log == [4.444444444444445, 10.0]
  assert cur_temp_fahrenheit == 50

  handle.stop()

  set_temp_f(60)

  assert log == [4.444444444444445, 10.0]
  assert cur_temp_fahrenheit == 60

As you can see, when we set the current temperature to a new
value, ``log_temp_celsius`` is re-run and a new entry is added to the
``log`` list. we can still use the function(s) without using the
tracker, in which case we will have the default, normal, non-reactive
behavior. When we use ``tracker.reactive()`` all the defined
dependencies on reactive-aware data sources are tracked by running
the given function immediately. Next, when the reactive source
changes, the tracker re-executes the function, thus re-tracking the
dependencies that may be different. ``tracker.reactive()`` returns an
handle, a ``Computation`` object that can be used to stop the
reactive behavior when it's no more necessary. The same object is
given as parameter to the tracked function.

The example proposed is indeed silly, but shows you the power of the
framework:

* code changes are minimal;

* the new concepts to learn are very few and simple;

* the reactive functions can be run alone without tracker involvement
  and they will run as normal code, without the need to refactor them.

Tracked functions can use ``tracker.reactive()`` themselves, in which
case the inner trackings will be stopped when the outer is re-run.

The code above is a bit ugly due to the usage of the getter and
setter, how can we avoid that? Here is the same example using the
``Value`` class:

.. code:: python

  from metapensiero import reactive

  tracker = reactive.get_tracker()
  cur_temp_fahrenheit = reactive.Value(40)

  def cur_temp_celsius(t_fahrenheit):
      return (t_fahrenheit - 32) / 1.8

  log = []

  def log_temp_celsius(handle):
      log.append(cur_temp_celsius(cur_temp_fahrenheit.value))

  handle = tracker.reactive(log_temp_celsius)

  assert log == [4.444444444444445]

  cur_temp_fahrenheit.value = 50

  assert log == [4.444444444444445, 10.0]

  handle.stop()

  cur_temp_fahrenheit.value = 60
  assert log == [4.444444444444445, 10.0]

``Value`` class can be used also be used as a method decorator in a
way similar to the builtin ``property`` decorator but with only a
*getter* function.

Another way to use the Value class is just as a value container, by
using its ``value`` to get or set the value, or just as any other data
member in a class body.

.. code:: python

  a = Value()

  a.value = True
  assert a.value == True

  class Foo(object):

      bar = Value()

      @Value()
      def zoo(self):
          # ... calc something useful



  foo = Foo()
  foo.bar = True

  assert foo.bar == True

  animal = foo.zoo

When used in class' body a ``Value`` saves a triplet of ``(Dependency,
Computation, value)`` per instance so you have to take that into
account. ``Value`` uses weak references in order to avoid keeping
instances alive.

There is also a constructor to build reactive
`namedlist`__ classes.

__ https://pypi.python.org/pypi/namedlist

The framework is also compatible with ``gevent`` and ``asyncio`` in
order to batch computation's recalculation in another ``Greenlet`` or
``Task``, respectively. As all the *invalidated* calculations are
recomputed sequentially, it's important to avoid having *suspension
points* in the reactive code, like calls to ``sleep()`` functions or
the execution of ``yield from`` and ``await`` statements. If this is
unavoidable, a *manual* suspension context manager is avaliable in
computations, named ``suspend()``. Using that, the block of code
inside a *with* statement runs isolated, and tracking is reinstated
afterwards.

For all those features, please have a look at code and tests for now.

Testing
-------

To run the tests you should run the following at the package root::

  python setup.py test

Build status
------------

.. image:: https://travis-ci.org/azazel75/metapensiero.reactive.svg?branch=master
    :target: https://travis-ci.org/azazel75/metapensiero.reactive
