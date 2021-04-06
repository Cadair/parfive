#!/usr/bin/env python
from setuptools import setup  # isort:skip
import os

setup(
    use_scm_version={'write_to': os.path.join('parfive', '_version.py')},
)
