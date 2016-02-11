# -*- coding: utf-8 -*-
# :Project:  metapensiero.reactive -- dependency class
# :Created:    mar 26 gen 2016 18:15:10 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
#

from __future__ import unicode_literals, absolute_import

import six

import logging

logger = logging.getLogger(__name__)


class Dependency(object):

    def __init__(self, tracker):
        self._tracker = tracker
        self._dependents = set()

    def __call__(self, computation=None):
        if not (computation or self._tracker.active):
            result = False
        else:
            computation = computation or self._tracker.current_computation
            if not computation in self._dependents:
                self._dependents.add(computation)
                computation.on_invalidate.connect(self._on_computation_invalidate)
                result = True
            else:
                result = False
        return result

    depend = __call__

    def _on_computation_invalidate(self, computation):
        self._dependents.remove(computation)

    def changed(self):
        deps = self._dependents
        if len(deps) > 0:
            for comp in list(deps):
                comp.invalidate()
            self._tracker.flusher.require_flush()

    @property
    def has_dependents(self):
        return len(self._dependents) > 0
