# -*- coding: utf-8 -*-
# :Project: metapensiero.reactive -- basic stuff
# :Created: lun 23 ott 2017 03:47:27 CEST
# :Author:  Alberto Berti <alberto@metapensiero.it>
# :License: GNU General Public License version 3 or later
#

from . import get_tracker

class Tracked:
    """A base class for objects that are Tracker-related"""

    def __init__(self, *, tracker=None):
        if tracker is None:
            self._tracker = get_tracker
        else:
            self._tracker = tracker

    @property
    def tracker(self):
        result = self._tracker
        if callable(result):
            result = result()
        return result
