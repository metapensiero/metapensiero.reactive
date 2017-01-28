# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- dependency class
# :Created:   mar 26 gen 2016 18:15:10 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Alberto Berti
#

from metapensiero import signal

import logging

logger = logging.getLogger(__name__)


class Dependency(metaclass=signal.SignalAndHandlerInitMeta):

    source = None
    """The source of a dependency, if any."""

    on_change = signal.Signal()

    def __init__(self, tracker, source=None):
        self._tracker = tracker
        self._dependents = set()
        self._source = source

    def __call__(self, computation=None):
        """Used to declare the dependency of a computation on an instance of this
        class. The dependency can be explicit by passing in a `Computation`
        instance or better it can be implicit, which is the usual way. When in
        implicit mode, the dependency finds the running computation by asking
        the `Tracker`.
        """
        if not (computation or self._tracker.active):
            result = False
        else:
            computation = computation or self._tracker.current_computation
            if computation not in self._dependents:
                self._dependents.add(computation)
                computation.add_dependency(self)
                computation.on_invalidate.connect(
                    self._on_computation_invalidate
                )
                result = True
            else:
                result = False
        return result

    depend = __call__

    def _on_computation_invalidate(self, computation):
        self._dependents.remove(computation)

    def _on_change_handler(self, followed_dependency):
        """Handler that will be called from following dependencies."""
        assert isinstance(followed_dependency, Dependency)
        self.changed()

    def changed(self):
        """This is called to declare that value/state/object that this instance
        rephresents has changed. It will notify every computation that was
        calculating when was called `depend` on it.
        It will also notify any handler connected to its `on_change` Signal.
        """
        deps = self._dependents
        self.on_change.notify(self)
        if len(deps) > 0:
            for comp in list(deps):
                comp.invalidate(self)
            self._tracker.flusher.require_flush()

    def follow(self, *others):
        """Follow the changed event of another dependency and change as well."""
        for other in others:
            assert isinstance(other, Dependency)
            other.on_change.connect(self._on_change_handler)

    @property
    def has_dependents(self):
        """True if this dependency has any computation that depends on it."""
        return len(self._dependents) > 0

    @property
    def source(self):
        """Return a possible connected object."""
        return self._source

    def unfollow(self, *others):
        """Stop following another dependency."""
        for other in others:
            assert isinstance(other, Dependency)
            other.on_change.disconnect(self._on_change_handler)
