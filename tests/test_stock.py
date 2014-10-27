# -*- coding: utf-8 -*-
"""
    test_stock

    Test USPS Integration via Endicia.

    :copyright: (c) 2013-2014 by Openlabs Technologies & Consulting (P) Limited
    :license: GPLv3, see LICENSE for more details.
"""
from decimal import Decimal

from trytond.tests.test_tryton import DB_NAME, USER, CONTEXT
from trytond.transaction import Transaction
from tests.test_endicia import BaseTestCase


class ShipmentTestCase(BaseTestCase):
    """
    Test model classes in stock.py.
    """

    def test_carrier_change(self):
        """
        Test on_change_carrier().
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            shipment, = self.StockShipmentOut.search([])
            self.StockShipmentOut.write([shipment], {
                'code': '1234'
            })

            self.assertEquals(
                shipment.on_change_carrier(),
                {
                    'cost_currency': 1,
                    'cost': Decimal('2.59'),
                    'cost_currency_digits': 2,
                    'is_endicia_shipping': True
                }
            )

            shipment.carrier = None
            shipment.save()

            self.assertEquals(shipment.on_change_carrier(), {
                'is_endicia_shipping': None
            })
