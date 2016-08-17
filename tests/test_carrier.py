# -*- coding: utf-8 -*-
"""
    test_carrier

    Test USPS Integration via Endicia.

"""
from trytond.tests.test_tryton import with_transaction
from trytond.transaction import Transaction
from tests.test_endicia import BaseTestCase


class CarrierTestCase(BaseTestCase):
    """
    Test Carrier model class.
    """

    def setup_defaults(self):
        """
        Method to setup defaults
        """
        super(CarrierTestCase, self).setup_defaults()

        self.carrier_product.code = "PROD123_US"
        self.carrier_product.save()

    @with_transaction()
    def test_0010_check_sale_package_uom(self):
        """
        Check sale package weight uom
        """
        self.setup_defaults()

        with Transaction().set_context(company=self.company.id):

            party = self.sale_party

            # Create sale order
            sale, = self.Sale.create([{
                'reference': 'S-1001',
                'payment_term': self.payment_term,
                'party': party.id,
                'invoice_address': party.addresses[0].id,
                'shipment_address': party.addresses[0].id,
                'carrier': self.carrier.id,
            }])

            self.assertEqual(sale.carrier.carrier_cost_method, 'endicia')

            self.assertEqual(sale.weight_uom.symbol, 'oz')

            # Should pick default uom if no carrier defined
            sale.carrier = None
            sale.save()

            self.assertEqual(sale.weight_uom.symbol, 'lb')
