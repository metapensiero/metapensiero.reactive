.. -*- coding: utf-8 -*-

Changes
-------

0.1 (2016-02-05)
~~~~~~~~~~~~~~~~

- Initial effort.
- Added testing with tox and ``gevent`` and ``asyncio``.
- Firt cut of the docs.

0.2 (2016-02-05)
~~~~~~~~~~~~~~~~

- small doc fixes.

0.3 (2016-02-10)
~~~~~~~~~~~~~~~~

- more tests.
- allow __set__ if generator is not defined.
- refactoring of Value's code.
- Fix behavior if Value's accessed when tracking isn't active.
- Provide a mechanism to halt tracking while computing if system
  suspension is needed (``gevent``, ``asyncio``).
- Updates to the doc.
- Code is now tested in a pre-production environment.

0.4 (2016-02-11)
~~~~~~~~~~~~~~~~

- fix a small bug in __delete__()
