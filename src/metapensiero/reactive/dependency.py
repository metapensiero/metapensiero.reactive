# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- dependency class
# :Created:   mar 26 gen 2016 18:15:10 CET
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: © 2016, 2017 Alberto Berti
#

import abc
import collections
import collections.abc
import functools
import logging
from weakref import WeakKeyDictionary

from metapensiero import signal

from .base import Tracked
from .stream_utils import Selector, Sink, Tee, Transformer

logger = logging.getLogger(__name__)


class Dependency(Tracked):

    def __init__(self, source=None, *, tracker=None):
        super().__init__(tracker=tracker)
        self._dependents = set()
        self._source = source

    def depend(self, computation=None):
        """Used to declare the dependency of a computation on an instance of this
        class. The dependency can be explicit by passing in a `Computation`
        instance or better it can be implicit, which is the usual way. When in
        implicit mode, the dependency finds the running computation by asking
        the `Tracker`.
        """
        if not (computation or self.tracker.active):
            result = False
        else:
            computation = computation or self.tracker.current_computation
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

    __call__ = depend

    def _on_computation_invalidate(self, computation):
        self._dependents.remove(computation)

    def changed(self):
        """This is called to declare that value/state/object that this instance
        represents has changed. It will notify every computation that was
        calculating when was called `depend` on it.
        """
        deps = self._dependents
        if len(deps) > 0:
            for comp in list(deps):
                if comp.stopped:
                    logger.error(
                        'Refusing to invalidate an already'
                        ' stopped computation. This should not happen!')
                comp.invalidate(self)
            self.tracker.flusher.require_flush()

    @property
    def has_dependents(self):
        """True if this dependency has any computation that depends on it."""
        return len(self._dependents) > 0

    @property
    def source(self):
        """Return a possible connected object."""
        return self._source


class StopFollowingValue(Exception):
    """Possibly raised by FollowMixin.follow ftrans function to abort following a
    single value."""


class FollowMixin(abc.ABC):

    _source = None

    def __init__(self):
        self._following = WeakKeyDictionary()

    @abc.abstractmethod
    def _add_followed(self, followed, ftrans=None):
        """Per class implementation.

        :param followed: an async generator
        :param ftrans: a function
        """

    @abc.abstractclassmethod
    def _dispatch(self, *values):
        """Per class implementation."""

    @abc.abstractmethod
    def _remove_followed(self, followed):
        """Per class implementation.

        :param followed: an ansync generator
        """

    def send(self, *values):
        if len(values) == 1 and self._source is not None:
            values = values[0]
        if self._source is not None:
            values = ((self._source,), values)
        self._dispatch(*values)

    def follow(self, *others, ftrans=None):
        """Follow the changed event of another dependency and change as well."""
        for other in others:
            assert isinstance(other, FollowMixin)
            self._add_followed(other, ftrans)

    def unfollow(self, *others):
        """Stop following another dependency."""
        for other in others:
            assert isinstance(other, FollowMixin)
            self._remove_followed(other)


class EventDependency(FollowMixin, Dependency,
                      metaclass=signal.SignalAndHandlerInitMeta):

    on_change = signal.Signal()

    def __init__(self, source=None, *, tracker=None):
        Dependency.__init__(self, source, tracker=tracker)
        FollowMixin.__init__(self)

    def _add_followed(self, followed, ftrans=None):
        assert isinstance(followed, EventDependency)
        cback = functools.partial(self._on_followed_changes, followed)
        self._following[followed] = (ftrans, cback)
        followed.on_change.connect(cback)

    def _dispatch(self, *values):
        self.on_change.notify(*values)

    def _remove_followed(self, followed):
        ftrans, cback = self._following.pop(followed)
        followed.on_change.disconnect(cback)

    def _on_followed_changes(self, followed, *changes):
        ftrans, cback = self._following[followed]
        try:
            if ftrans:
                changes = ftrans(*changes)
            self.changed(*changes)
        except StopFollowingValue:
            pass

    def changed(self, *values):
        super().changed()
        self.send(*values)

    def sink(self):
        return EventSink(self)


class StreamFollower(FollowMixin):

    def __init__(self, remove_none=False):
        super().__init__()
        self._internal_tee = Tee(push_mode=True)
        self._follow_selector = Selector(self._internal_tee,
                                         remove_none=remove_none)
        self._public_tee = Tee(self._follow_selector)

    def __aiter__(self):
        return self._public_tee.__aiter__()

    def _add_followed(self, followed, ftrans=None):
        agen_factory = Transformer(
            functools.partial(self._follow_handler, ftrans), source=followed)
        self._following[followed] = agen_factory
        self._follow_selector.add(agen_factory)

    def _dispatch(self, *values):
        if len(values) == 1:
            values = values[0]
        self._internal_tee.push(values)

    def _remove_followed(self, followed):
        self._follow_selector.remove(self._following[followed])
        del self._following[followed]

    def _follow_handler(self, ftrans, *values):
        if ftrans:
            return ftrans(*values)
        else:
            return values

    def sink(self):
        return Sink(self)


class StreamDependency(StreamFollower, Dependency):

    def __init__(self, source=None, *, tracker=None):
        Dependency.__init__(self, source, tracker=tracker)
        StreamFollower.__init__(self)
        self._public_tee = Tee(self._follow_selector)

    def _follow_handler(self, ftrans, *values):
        Dependency.changed(self)
        return super()._follow_handler(ftrans, *values)

    def changed(self, *values):
        Dependency.changed(self)
        self.send(*values)


class EventSink:

    def __init__(self, source):
        assert isinstance(source, EventDependency)
        self.source = source
        self.active = False
        self.data = collections.deque()

    def __iter__(self):
        return iter(self.data)

    def _on_changed(self, *values):
        self.data.append(values)

    def start(self):
        self.source.on_change.connect(self._on_changed)

    def stop(self):
        self.source.on_change.disconnect(self._on_changed)
