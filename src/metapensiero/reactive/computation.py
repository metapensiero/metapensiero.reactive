# -*- coding: utf-8 -*-
# :Project:  metapensiero.reactive -- computation object
# :Created:    mar 26 gen 2016 18:13:41 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
#

from __future__ import unicode_literals, absolute_import

import six

import logging

from metapensiero import signal

logger = logging.getLogger(__name__)


@six.add_metaclass(signal.SignalAndHandlerInitMeta)
class Computation(object):

    on_error = signal.Signal()

    @signal.Signal
    def on_invalidate(self, subscribers, notify):
        self._notify(self.on_invalidate, notify)

    @on_invalidate.on_connect
    def on_invalidate(self, handler, subscribers, connect):
        if self.invalidated:
            with self._tracker.no_suspend():
                handler(self)
        else:
            connect(handler)

    @signal.Signal
    def on_stop(self, subscribers, notify):
        self._notify(self.on_invalidate, notify)

    @on_stop.on_connect
    def on_stop(self, handler, subscribers, connect):
        if self.stopped:
            with self._tracker.no_suspend():
                handler(self)
        else:
            connect(handler)

    def __init__(self, tracker, parent, func, on_error=None):
        self.invalidated = False
        self.first_run = True
        self.stopped = False
        self._tracker = tracker
        self._func = func
        self._parent = parent
        self._recomputing = False
        if on_error:
            self.on_error.connect(on_error)

        self._tracker._computations.add(self)
        errored = False
        try:
            self._compute()
        except:
            errored = True
            logger.exception("Error while runnning computation")
            raise
        finally:
            self.first_run = False
            if errored:
                self.stop()

        if not self.stopped and parent:
            parent.on_invalidate.connect(self._on_parent_invalidated)

    def _notify(self, signal, fnotify):
        try:
            with self._tracker.no_suspend():
                fnotify(self)
        finally:
            signal.clear()

    def invalidate(self):
        """Invalidate the current state of this computation"""
        if not self.invalidated:
            if not (self._recomputing or self.stopped):
                flusher = self._tracker.flusher
                flusher.add_computation(self)
                self.on_invalidate.notify()

        self.invalidated = True

    @property
    def _needs_recompute(self):
        return self.invalidated and not self.stopped

    def _compute(self):
        self.invalidated = False
        with self._tracker.while_compute(self):
            self._func(self)

    def _recompute(self):
        if self._needs_recompute:
            try:
                self._recomputing = True
                self._compute()
            except Exception as e:
                if len(self.on_error.subscribers) > 0:
                    self.on_error.notify(self, e)
                else:
                    logger.exception("Error while recomputing")
                    raise
            finally:
                self._recomputing = False

    def stop(self):
        if not self.stopped:
            self.invalidate()
            self._tracker._computations.remove(self)
            self.stopped = True

    def _on_parent_invalidated(self, parent):
        self.stop()
