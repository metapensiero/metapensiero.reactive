# -*- coding: utf-8 -*-
# :Project:   metapensiero.reactive -- a unobtrusive and light reactive system
# :Created:   dom 09 ago 2015 12:57:35 CEST
# :Author:    Alberto Berti <alberto@metapensiero.it>
# :License:   GNU General Public License version 3 or later
# :Copyright: Copyright (C) 2015 Alberto Berti
#

import os
import sys
from codecs import open

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.rst'), encoding='utf-8') as f:
    README = f.read()
with open(os.path.join(here, 'CHANGES.rst'), encoding='utf-8') as f:
    CHANGES = f.read()
with open(os.path.join(here, 'version.txt'), encoding='utf-8') as f:
    VERSION = f.read().strip()

PY2 = sys.version_info[:1] == (2,)

TESTS_REQUIREMENTS = ['pytest']

if PY2:
    TESTS_REQUIREMENTS.append('gevent')

setup(
    name="metapensiero.reactive",
    version=VERSION,
    url="https://github.com/azazel75/metapensiero.reactive",

    description="an unobtrusive and light reactive system",
    long_description=README + u'\n\n' + CHANGES,

    author="Alberto Berti",
    author_email="alberto@metapensiero.it",

    license="GPLv3+",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License (GPL)",
       ],
    keywords='reactive functional dataflow asyncio gevent',

    packages=find_packages('src'),
    package_dir={'': 'src'},
    namespace_packages=['metapensiero'],

    install_requires=['setuptools',
                      'metapensiero.signal>=0.7',
                      'six',
                      'namedlist'],
    extras_require={'dev': ['metapensiero.tool.bump_version', 'docutils']},
    setup_requires=['pytest-runner'],
    tests_require=TESTS_REQUIREMENTS,
)
