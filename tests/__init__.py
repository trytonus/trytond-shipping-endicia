# -*- coding: utf-8 -*-
"""
    __init__

    :copyright: © 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
import unittest

import trytond.tests.test_tryton

from .test_endicia import EndiciaTestCase


def suite():
    test_suite = trytond.tests.test_tryton.suite()
    test_suite.addTests([
        unittest.TestLoader().loadTestsFromTestCase(EndiciaTestCase)
    ])
    return test_suite
