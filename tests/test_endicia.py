# -*- coding: utf-8 -*-
"""
    test_endicia

    Test USPS Integration via Endicia.

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: GPLv3, see LICENSE for more details.
"""
from decimal import Decimal
from time import time

import sys
import os
DIR = os.path.abspath(os.path.normpath(os.path.join(__file__,
    '..', '..', '..', '..', '..', 'trytond')))
if os.path.isdir(DIR):
    sys.path.insert(0, os.path.dirname(DIR))

import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, DB_NAME, USER, CONTEXT, \
    test_view, test_depends
from trytond.transaction import Transaction
from trytond.config import CONFIG
CONFIG['data_path'] = '.'


class TestUSPSEndicia(unittest.TestCase):
    """Test USPS with Endicia.
    """

    def setUp(self):
        trytond.tests.test_tryton.install_module('endicia_integration')
        self.sale = POOL.get('sale.sale')
        self.sale_config = POOL.get('sale.configuration')
        self.endicia_mailclass = POOL.get('endicia.mailclass')
        self.product = POOL.get('product.product')
        self.uom = POOL.get('product.uom')
        self.account = POOL.get('account.account')
        self.category = POOL.get('product.category')
        self.carrier = POOL.get('carrier')
        self.party = POOL.get('party.party')
        self.party_contact = POOL.get('party.contact_mechanism')
        self.payment_term = POOL.get('account.invoice.payment_term')
        self.country = POOL.get('country.country')
        self.country_subdivision = POOL.get('country.subdivision')
        self.sale = POOL.get('sale.sale')
        self.party_address = POOL.get('party.address')
        self.stock_location = POOL.get('stock.location')
        self.stock_shipment_out = POOL.get('stock.shipment.out')
        self.currency = POOL.get('currency.currency')
        self.company = POOL.get('company.company')
        self.ir_attachment = POOL.get('ir.attachment')

    def test0005views(self):
        '''
        Test views.
        '''
        test_view('endicia_integration')

    def test0006depends(self):
        '''
        Test depends.
        '''
        test_depends()

    def setup_defaults(self):
        """Method to setup defaults
        """
        # Create currency
        currency = self.currency.create({
            'name': 'United Stated Dollar',
            'code': 'USD',
            'symbol': 'USD',
        })
        currency_alt = self.currency.create({
            'name': 'Indian Rupee',
            'code': 'INR',
            'symbol': 'INR',
        })

        company, = self.company.search([
            ('name', '=', 'B2CK')
        ])

        # Endicia Configuration
        self.company.write([company], {
            'currency': currency.id,
            'endicia_account_id': '123456',
            'endicia_requester_id': '123456',
            'endicia_passphrase': 'PassPhrase',
            'endicia_test': True,
        })
        company_phone = self.party_contact.create({
            'type': 'phone',
            'value': '8005551212',
            'party': company.party.id
        })

        # Sale configuration
        endicia_mailclass, = self.endicia_mailclass.search([
            ('value', '=', 'First')
        ])

        self.sale_config.write(1, {
            'endicia_label_subtype': 'Integrated',
            'endicia_integrated_form_type': 'Form2976',
            'endicia_mailclass': endicia_mailclass.id,
            'endicia_include_postage':  True,
        })

        account_revenue, = self.account.search([
            ('kind', '=', 'revenue')
        ])

        # Create product category
        category = self.category.create({
            'name': 'Test Category',
        })

        uom_kg, = self.uom.search([('symbol', '=', 'kg')])
        uom_pound, = self.uom.search([('symbol', '=', 'lbs')])

        # Carrier Carrier Product
        carrier_product = self.product.create({
            'name': 'Test Carrier Product',
            'category': category.id,
            'type': 'service',
            'salable': True,
            'sale_uom': uom_kg,
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom_kg,
            'cost_price_method': 'fixed',
            'account_revenue': account_revenue.id,
        })

        # Create product
        product = self.product.create({
            'name': 'Test Product',
            'category': category.id,
            'type': 'goods',
            'salable': True,
            'sale_uom': uom_kg,
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom_kg,
            'account_revenue': account_revenue.id,
            'weight': 0.5,
            'weight_uom': uom_pound.id,
        })

        # Create party
        carrier_party = self.party.create({
            'name': 'Test Party',
        })

        carrier = self.carrier.create({
            'party': carrier_party.id,
            'carrier_product': carrier_product.id,
            'carrier_cost_method': 'endicia',
        })

        payment_term = self.payment_term.create({
            'name': 'Cash',
        })

        country_us = self.country.create({
            'name': 'United States',
            'code': 'US',
        })

        subdivision_idaho = self.country_subdivision.create({
            'name': 'Idaho',
            'code': 'US-ID',
            'country': country_us.id,
            'type': 'state'
        })

        subdivision_california = self.country_subdivision.create({
            'name': 'California',
            'code': 'US-CA',
            'country': country_us.id,
            'type': 'state'
        })
        company_address = self.party_address.create({
            'name': 'Amine Khechfe',
            'street': '247 High Street',
            'zip': '84301',
            'city': 'Palo Alto',
            'country': country_us.id,
            'subdivision': subdivision_california.id,
            'party': company.party.id,
        })

        sale_party = self.party.create({
            'name': 'Test Sale Party',
        })
        sale_party_phone = self.party_contact.create({
            'type': 'phone',
            'value': '8005763279',
            'party': sale_party.id
        })

        sale_address = self.party_address.create({
            'name': 'John Doe',
            'street': '123 Main Street',
            'zip': '83702',
            'city': 'Boise',
            'country': country_us.id,
            'subdivision': subdivision_idaho.id,
            'party': sale_party,
        })

        # Create sale order
        sale = self.sale.create({
            'reference': 'S-1001',
            'payment_term': payment_term,
            'party': sale_party.id,
            'invoice_address': sale_address.id,
            'shipment_address': sale_address.id,
            'carrier': carrier.id,
            'lines': [
                ('create', {
                    'type': 'line',
                    'quantity': 1,
                    'product': product,
                    'unit_price': Decimal('10.00'),
                    'description': 'Test Description1',
                    'unit': uom_kg,
                }),
            ]
        })

        self.stock_location.write([sale.warehouse], {
            'address': company_address.id,
        })

        # Confirm and process sale order
        self.assertEqual(len(sale.lines), 1)
        self.sale.quote([sale])
        self.assertEqual(len(sale.lines), 2)
        self.sale.confirm([sale])
        self.sale.process([sale])

    def test_0010_generate_endicia_gss_labels(self):
        """Test case to generate Endicia labels.
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):

            # Call method to create sale order
            self.setup_defaults()

            shipment, = self.stock_shipment_out.search([])
            self.stock_shipment_out.write([shipment], {
                'code': str(int(time())),
            })

            # Before generating labels
            # There is no tracking number generated
            # And no attachment cerated for labels
            self.assertFalse(shipment.tracking_number)
            attatchment = self.ir_attachment.search([])
            self.assertEqual(len(attatchment), 0)

            # Make shipment in packed state.
            shipment.assign([shipment])
            shipment.pack([shipment])

            # Call method to generate labels.
            shipment.make_endicia_labels()

            self.assertTrue(shipment.tracking_number)
            self.assertGreater(len(
                self.ir_attachment.search([
                    ('resource', '=', 'stock.shipment.out,%s' % shipment.id)
                ])
            ), 0)

    #TODO: Add more tests for wizards and other operations


def suite():
    suite = trytond.tests.test_tryton.suite()
    from trytond.modules.account.tests import test_account
    for test in test_account.suite():
        if test not in suite:
            suite.addTest(test)
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
        TestUSPSEndicia))
    return suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())

