# -*- coding: utf-8 -*-
"""
    test_endicia

    Test USPS Integration via Endicia.

    :copyright: (c) 2013-2014 by Openlabs Technologies & Consulting (P) Limited
    :license: GPLv3, see LICENSE for more details.
"""
from decimal import Decimal
from time import time
from datetime import datetime
from dateutil.relativedelta import relativedelta

import sys
import os
DIR = os.path.abspath(os.path.normpath(
    os.path.join(__file__, '..', '..', '..', '..', '..', 'trytond')
))
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
        self.User = POOL.get('res.user')
        self.template = POOL.get('product.template')
        self.EndiciaConfiguration = POOL.get('endicia.configuration')

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

    def _create_coa_minimal(self, company):
        """Create a minimal chart of accounts
        """
        AccountTemplate = POOL.get('account.account.template')
        Account = POOL.get('account.account')

        account_create_chart = POOL.get(
            'account.create_chart', type="wizard"
        )

        account_template, = AccountTemplate.search(
            [('parent', '=', None)]
        )

        session_id, _, _ = account_create_chart.create()
        create_chart = account_create_chart(session_id)
        create_chart.account.account_template = account_template
        create_chart.account.company = company
        create_chart.transition_create_account()

        receivable, = Account.search([
            ('kind', '=', 'receivable'),
            ('company', '=', company),
        ])
        payable, = Account.search([
            ('kind', '=', 'payable'),
            ('company', '=', company),
        ])
        create_chart.properties.company = company
        create_chart.properties.account_receivable = receivable
        create_chart.properties.account_payable = payable
        create_chart.transition_create_properties()

    def _create_fiscal_year(self, date_=None, company=None):
        """
        Creates a fiscal year and requried sequences
        """
        FiscalYear = POOL.get('account.fiscalyear')
        Sequence = POOL.get('ir.sequence')
        SequenceStrict = POOL.get('ir.sequence.strict')
        Company = POOL.get('company.company')

        if date_ is None:
            date_ = datetime.utcnow().date()

        if not company:
            company, = Company.search([], limit=1)

        invoice_sequence, = SequenceStrict.create([{
            'name': '%s' % date_.year,
            'code': 'account.invoice',
            'company': company
        }])
        fiscal_year, = FiscalYear.create([{
            'name': '%s' % date_.year,
            'start_date': date_ + relativedelta(month=1, day=1),
            'end_date': date_ + relativedelta(month=12, day=31),
            'company': company,
            'post_move_sequence': Sequence.create([{
                'name': '%s' % date_.year,
                'code': 'account.move',
                'company': company,
            }])[0],
            'out_invoice_sequence': invoice_sequence,
            'in_invoice_sequence': invoice_sequence,
            'out_credit_note_sequence': invoice_sequence,
            'in_credit_note_sequence': invoice_sequence,
        }])
        FiscalYear.create_period([fiscal_year])
        return fiscal_year

    def _get_account_by_kind(self, kind, company=None, silent=True):
        """Returns an account with given spec

        :param kind: receivable/payable/expense/revenue
        :param silent: dont raise error if account is not found
        """
        Account = POOL.get('account.account')
        Company = POOL.get('company.company')

        if company is None:
            company, = Company.search([], limit=1)

        accounts = Account.search([
            ('kind', '=', kind),
            ('company', '=', company)
        ], limit=1)
        if not accounts and not silent:
            raise Exception("Account not found")
        return accounts[0] if accounts else None

    def _create_payment_term(self):
        """Create a simple payment term with all advance
        """
        PaymentTerm = POOL.get('account.invoice.payment_term')

        return PaymentTerm.create([{
            'name': 'Direct',
            'lines': [('create', [{'type': 'remainder'}])]
        }])

    def setup_defaults(self):
        """Method to setup defaults
        """
        # Create currency
        currency, = self.currency.create([{
            'name': 'United Stated Dollar',
            'code': 'USD',
            'symbol': 'USD',
        }])
        self.currency.create([{
            'name': 'Indian Rupee',
            'code': 'INR',
            'symbol': 'INR',
        }])

        country_us, = self.country.create([{
            'name': 'United States',
            'code': 'US',
        }])

        subdivision_idaho, = self.country_subdivision.create([{
            'name': 'Idaho',
            'code': 'US-ID',
            'country': country_us.id,
            'type': 'state'
        }])

        subdivision_california, = self.country_subdivision.create([{
            'name': 'California',
            'code': 'US-CA',
            'country': country_us.id,
            'type': 'state'
        }])

        with Transaction().set_context(company=None):
            company_party, = self.party.create([{
                'name': 'Test Party',
                'addresses': [('create', [{
                    'name': 'Amine Khechfe',
                    'street': '247 High Street',
                    'zip': '84301',
                    'city': 'Palo Alto',
                    'country': country_us.id,
                    'subdivision': subdivision_california.id,
                }])]
            }])

        # Endicia Configuration
        self.EndiciaConfiguration.create([{
            'account_id': '123456',
            'requester_id': '123456',
            'passphrase': 'PassPhrase',
            'is_test': True,
        }])
        self.company, = self.company.create([{
            'party': company_party.id,
            'currency': currency.id,
        }])
        self.party_contact.create([{
            'type': 'phone',
            'value': '8005551212',
            'party': self.company.party.id
        }])

        # Sale configuration
        endicia_mailclass, = self.endicia_mailclass.search([
            ('value', '=', 'First')
        ])

        self.sale_config.write(self.sale_config(1), {
            'endicia_label_subtype': 'Integrated',
            'endicia_integrated_form_type': 'Form2976',
            'endicia_mailclass': endicia_mailclass.id,
            'endicia_include_postage': True,
        })

        self.User.write(
            [self.User(USER)], {
                'main_company': self.company.id,
                'company': self.company.id,
            }
        )

        CONTEXT.update(self.User.get_preferences(context_only=True))

        self._create_fiscal_year(company=self.company)
        self._create_coa_minimal(company=self.company)
        self.payment_term, = self._create_payment_term()

        account_revenue, = self.account.search([
            ('kind', '=', 'revenue')
        ])

        # Create product category
        category, = self.category.create([{
            'name': 'Test Category',
        }])

        uom_kg, = self.uom.search([('symbol', '=', 'kg')])
        uom_pound, = self.uom.search([('symbol', '=', 'lb')])

        # Carrier Carrier Product
        carrier_product_template, = self.template.create([{
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
            'products': [('create', self.template.default_products())]
        }])

        carrier_product = carrier_product_template.products[0]

        # Create product
        template, = self.template.create([{
            'name': 'Test Product',
            'category': category.id,
            'type': 'goods',
            'salable': True,
            'sale_uom': uom_kg,
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom_kg,
            'account_revenue': account_revenue.id,
            'weight': .5,
            'weight_uom': uom_pound.id,
            'products': [('create', self.template.default_products())]
        }])

        self.product = template.products[0]

        # Create party
        carrier_party, = self.party.create([{
            'name': 'Test Party',
        }])

        # Create party
        carrier_party, = self.party.create([{
            'name': 'Test Party',
        }])

        self.carrier, = self.carrier.create([{
            'party': carrier_party.id,
            'carrier_product': carrier_product.id,
            'carrier_cost_method': 'endicia',
        }])

        self.sale_party, = self.party.create([{
            'name': 'Test Sale Party',
            'addresses': [('create', [{
                'name': 'John Doe',
                'street': '123 Main Street',
                'zip': '83702',
                'city': 'Boise',
                'country': country_us.id,
                'subdivision': subdivision_idaho.id,
            }])]
        }])
        self.party_contact.create([{
            'type': 'phone',
            'value': '8005763279',
            'party': self.sale_party.id
        }])

        self.create_sale(self.sale_party)

    def create_sale(self, party):
        """
        Create and confirm sale order for party with default values.
        """
        with Transaction().set_context(company=self.company.id):

            # Create sale order
            sale, = self.sale.create([{
                'reference': 'S-1001',
                'payment_term': self.payment_term,
                'party': party.id,
                'invoice_address': party.addresses[0].id,
                'shipment_address': party.addresses[0].id,
                'carrier': self.carrier.id,
                'lines': [
                    ('create', [{
                        'type': 'line',
                        'quantity': 1,
                        'product': self.product,
                        'unit_price': Decimal('10.00'),
                        'description': 'Test Description1',
                        'unit': self.product.template.default_uom,
                    }]),
                ]
            }])

            self.stock_location.write([sale.warehouse], {
                'address': self.company.party.addresses[0].id,
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

            with Transaction().set_context(company=self.company.id):

                # Call method to generate labels.
                shipment.make_endicia_labels()

            self.assertTrue(shipment.tracking_number)
            self.assertTrue(
                self.ir_attachment.search([
                    ('resource', '=', 'stock.shipment.out,%s' % shipment.id)
                ], count=True) > 0
            )

    def test_0015_generate_endicia_flat_label(self):
        """Test case to generate Endicia labels.
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):

            # Call method to create sale order
            self.setup_defaults()

            shipment, = self.stock_shipment_out.search([])
            self.stock_shipment_out.write([shipment], {
                'code': str(int(time())),
                'endicia_mailpiece_shape': 'Flat',
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

            with Transaction().set_context(company=self.company.id):

                # Call method to generate labels.
                shipment.make_endicia_labels()

            self.assertTrue(shipment.tracking_number)
            self.assertTrue(
                self.ir_attachment.search([
                    ('resource', '=', 'stock.shipment.out,%s' % shipment.id)
                ], count=True) > 0
            )

    def test_0020_shipment_bag(self):
        """Test case for shipment bag
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            EndiciaShipmentBag = POOL.get('endicia.shipment.bag')
            ShipmentOut = POOL.get('stock.shipment.out')

            # Call method to create sale order
            self.setup_defaults()
            self.create_sale(self.sale_party)  # Create second sale and shipment

            shipments = self.stock_shipment_out.search([])

            # Make shipments in packed state.
            ShipmentOut.assign(shipments)
            ShipmentOut.pack(shipments)
            ShipmentOut.done(shipments)

            bags = EndiciaShipmentBag.search(())
            self.assertTrue(len(bags), 1)
            bag = bags[0]
            self.assertFalse(bag.submission_id)
            self.assertEqual(len(bag.shipments), 2)
            EndiciaShipmentBag.close([bag])
            self.assertTrue(bag.submission_id)

            self.assertEqual(
                self.ir_attachment.search([
                    ('resource', '=', 'endicia.shipment.bag,%s' % bag.id)
                ], count=True), 1
            )

            # Create new sale and shipment
            self.create_sale(self.sale_party)

            shipment, = self.stock_shipment_out.search([
                ('state', '=', 'waiting')
            ])

            # Make shipment in packed state.
            ShipmentOut.assign([shipment])
            ShipmentOut.pack([shipment])
            ShipmentOut.done([shipment])

            self.assertEqual(EndiciaShipmentBag.search([], count=True), 2)

            bag, = EndiciaShipmentBag.search([('state', '=', 'open')])
            self.assertFalse(bag.submission_id)
            self.assertEqual(len(bag.shipments), 1)
            self.assertEqual(bag.shipments[0], shipment)
            EndiciaShipmentBag.close([bag])
            self.assertTrue(bag.submission_id)

            self.assertEqual(
                self.ir_attachment.search([
                    ('resource', '=', 'endicia.shipment.bag,%s' % bag.id)
                ], count=True), 1
            )
    # TODO: Add more tests for wizards and other operations


def suite():
    suite = trytond.tests.test_tryton.suite()
    from trytond.modules.account.tests import test_account
    for test in test_account.suite():
        if test not in suite:
            suite.addTest(test)
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestUSPSEndicia)
    )
    return suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
