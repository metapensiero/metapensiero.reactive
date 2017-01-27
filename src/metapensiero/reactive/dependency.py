# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- dependency class
# :Created:   mar 26 gen 2016 18:15:10 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2016 Alberto Berti
#

from __future__ import unicode_literals, absolute_import

from metapensiero import signal

import logging


logger = logging.getLogger(__name__)


class Dependency(object):

    source = None
    """The source of a dependency, if any."""

    on_change = signal.Signal()

    def __init__(self, tracker, source=None):
        self._tracker = tracker
        self._dependents = set()
        self._source = source

    def __call__(self, computation=None):
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
        self.change()

    def changed(self):
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
        return len(self._dependents) > 0

    @property
    def source(self):
        return self._source

    def unfollow(self, *others):
        """Stop following another dependency."""
        for other in others:
            assert isinstance(other, Dependency)
            other.disconnect(self._on_change_handler)
