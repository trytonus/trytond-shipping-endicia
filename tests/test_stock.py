# -*- coding: utf-8 -*-
"""
    test_stock

    Test USPS Integration via Endicia.

"""
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

            res = shipment.on_change_carrier()
            self.assertTrue('cost_currency' in res)
            self.assertTrue('cost' in res)
            self.assertTrue('cost_currency_digits' in res)

            shipment.carrier = None
            shipment.save()

            self.assertEquals(shipment.on_change_carrier(), {
                'is_endicia_shipping': None
            })
