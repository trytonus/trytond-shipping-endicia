# -*- coding: utf-8 -*-
"""
    __init__

"""
import unittest

import trytond.tests.test_tryton
from test_endicia import TestUSPSEndicia
from test_carrier import CarrierTestCase
from test_stock import ShipmentTestCase


def suite():
    """
    Define suite
    """
    test_suite = trytond.tests.test_tryton.suite()
    test_suite.addTests([
        unittest.TestLoader().loadTestsFromTestCase(TestUSPSEndicia),
        unittest.TestLoader().loadTestsFromTestCase(ShipmentTestCase),
        unittest.TestLoader().loadTestsFromTestCase(CarrierTestCase)
    ])
    return test_suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
