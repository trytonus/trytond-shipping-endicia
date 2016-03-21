# -*- coding: utf-8 -*-
"""
    test_endicia

    Test USPS Integration via Endicia.

"""
from decimal import Decimal
from time import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
import unittest

import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, DB_NAME, USER, CONTEXT, \
    test_view, test_depends
from trytond.transaction import Transaction
from trytond.config import config
config.set('database', 'path', '/tmp')


class BaseTestCase(unittest.TestCase):
    """
    Base test case for trytond-endicia-integration.
    """
    def setUp(self):
        trytond.tests.test_tryton.install_module('shipping_endicia')
        self.Sale = POOL.get('sale.sale')
        self.SaleConfig = POOL.get('sale.configuration')
        self.CarrierService = POOL.get('carrier.service')
        self.Product = POOL.get('product.product')
        self.Uom = POOL.get('product.uom')
        self.Account = POOL.get('account.account')
        self.Category = POOL.get('product.category')
        self.Carrier = POOL.get('carrier')
        self.Party = POOL.get('party.party')
        self.PartyContact = POOL.get('party.contact_mechanism')
        self.PaymentTerm = POOL.get('account.invoice.payment_term')
        self.Country = POOL.get('country.country')
        self.Country_Subdivision = POOL.get('country.subdivision')
        self.Sale = POOL.get('sale.sale')
        self.PartyAddress = POOL.get('party.address')
        self.StockLocation = POOL.get('stock.location')
        self.StockShipmentOut = POOL.get('stock.shipment.out')
        self.Currency = POOL.get('currency.currency')
        self.Company = POOL.get('company.company')
        self.IrAttachment = POOL.get('ir.attachment')
        self.User = POOL.get('res.user')
        self.Template = POOL.get('product.template')
        self.GenerateLabel = POOL.get('shipping.label', type="wizard")

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
        self.currency, = self.Currency.create([{
            'name': 'United Stated Dollar',
            'code': 'USD',
            'symbol': 'USD',
        }])
        self.Currency.create([{
            'name': 'Indian Rupee',
            'code': 'INR',
            'symbol': 'INR',
        }])

        country_us, country_at = self.Country.create([{
            'name': 'United States',
            'code': 'US',
        }, {
            'name': 'Austria',
            'code': 'AT',
        }])

        subdivision_idaho, = self.Country_Subdivision.create([{
            'name': 'Idaho',
            'code': 'US-ID',
            'country': country_us.id,
            'type': 'state'
        }])

        subdivision_california, = self.Country_Subdivision.create([{
            'name': 'California',
            'code': 'US-CA',
            'country': country_us.id,
            'type': 'state'
        }])

        subdivision_steiermark, = self.Country_Subdivision.create([{
            'name': 'Steiermark',
            'code': 'AT-6',
            'country': country_at.id,
            'type': 'state'
        }])

        with Transaction().set_context(company=None):
            company_party, = self.Party.create([{
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

        self.company, = self.Company.create([{
            'party': company_party.id,
            'currency': self.currency.id,
        }])
        self.PartyContact.create([{
            'type': 'phone',
            'value': '8005551212',
            'party': self.company.party.id
        }])

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

        account_revenue, = self.Account.search([
            ('kind', '=', 'revenue')
        ])

        # Create product category
        category, = self.Category.create([{
            'name': 'Test Category',
        }])

        uom_kg, = self.Uom.search([('symbol', '=', 'kg')])
        uom_oz, = self.Uom.search([('symbol', '=', 'oz')])

        # Carrier Carrier Product
        carrier_product_template, = self.Template.create([{
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
            'products': [('create', self.Template.default_products())]
        }])

        self.carrier_product = carrier_product_template.products[0]

        # Create product
        template, = self.Template.create([{
            'name': 'Test Product',
            'category': category.id,
            'type': 'goods',
            'salable': True,
            'sale_uom': uom_kg,
            'list_price': Decimal('10.896'),
            'cost_price': Decimal('5.896'),
            'default_uom': uom_kg,
            'account_revenue': account_revenue.id,
            'weight': .1,
            'weight_uom': uom_oz.id,
            'products': [('create', self.Template.default_products())]
        }])

        self.product = template.products[0]

        # Create party
        carrier_party, = self.Party.create([{
            'name': 'Test Party',
        }])

        # Create party
        carrier_party, = self.Party.create([{
            'name': 'Test Party',
        }])

        self.carrier, = self.Carrier.create([{
            'party': carrier_party.id,
            'carrier_product': self.carrier_product.id,
            'carrier_cost_method': 'endicia',
            'currency': self.currency.id,
            'endicia_account_id': '2504280',
            'endicia_requester_id': '1xxx',
            'endicia_passphrase': 'thisisnewpassphrase',
            'endicia_is_test': True,
        }])

        self.sale_party, = self.Party.create([{
            'name': 'Test Sale Party',
            'addresses': [('create', [{
                'name': 'John Doe',
                'street': '123 Main Street',
                'zip': '83702',
                'city': 'Boise',
                'country': country_us.id,
                'subdivision': subdivision_idaho.id,
            }, {
                'name': 'John Doe',
                'street': 'Johann Fuxgasse 36',
                'zip': '8010',
                'city': 'Graz',
                'country': country_at.id,
                'subdivision': subdivision_steiermark.id,
            }, {
                'name': 'John Doe',
                'street': '1735 Carleton St.',
                'streetbis': 'Apt A',
                'zip': '94703',
                'city': 'Berkeley',
                'country': country_us.id,
                'subdivision': subdivision_california.id,
            }])]
        }])
        self.PartyContact.create([{
            'type': 'phone',
            'value': '8005763279',
            'party': self.sale_party.id
        }])

        self.sale = self.create_sale(self.sale_party)

    def create_sale(self, party):
        """
        Create and confirm sale order for party with default values.
        """
        with Transaction().set_context(company=self.company.id):

            # Create sale order
            sale, = self.Sale.create([{
                'reference': 'S-1001',
                'payment_term': self.payment_term,
                'party': party.id,
                'invoice_address': party.addresses[0].id,
                'shipment_address': party.addresses[0].id,
                'carrier': self.carrier.id,
                'lines': [
                    ('create', [{
                        'type': 'line',
                        'quantity': 3,
                        'product': self.product,
                        'unit_price': Decimal('10.00'),
                        'description': 'Test Description1',
                        'unit': self.product.template.default_uom,
                    }]),
                ]
            }])

            self.StockLocation.write([sale.warehouse], {
                'address': self.company.party.addresses[0].id,
            })

            # Confirm and process sale order
            self.assertEqual(len(sale.lines), 1)
            self.Sale.quote([sale])
            self.assertEqual(len(sale.lines), 2)
            self.Sale.confirm([sale])
            self.Sale.process([sale])

            return sale


class TestUSPSEndicia(BaseTestCase):
    """
    Test USPS with Endicia.
    """

    def test0005views(self):
        '''
        Test views.
        '''
        test_view('shipping_endicia')

    def test0006depends(self):
        '''
        Test depends.
        '''
        test_depends()

    def test_0010_generate_endicia_gss_labels(self):
        """Test case to generate Endicia labels.
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):

            # Call method to create sale order
            self.setup_defaults()

            shipment, = self.StockShipmentOut.search([])
            self.StockShipmentOut.write([shipment], {
                'code': str(int(time())),
            })

            # Before generating labels
            # There is no tracking number generated
            # And no attachment cerated for labels
            self.assertFalse(shipment.tracking_number)
            attatchment = self.IrAttachment.search([])
            self.assertEqual(len(attatchment), 0)

            # Make shipment in packed state.
            shipment.assign([shipment])
            shipment.pack([shipment])

            with Transaction().set_context(company=self.company.id):

                # Call method to generate labels.
                shipment.generate_shipping_labels()

            self.assertTrue(shipment.tracking_number)
            self.assertTrue(
                self.IrAttachment.search([
                    ('resource', '=', 'stock.shipment.out,%s' % shipment.id)
                ], count=True) > 0
            )

    def test_0015_generate_endicia_flat_label(self):
        """Test case to generate Endicia labels.
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):

            # Call method to create sale order
            self.setup_defaults()

            shipment, = self.StockShipmentOut.search([])
            self.StockShipmentOut.write([shipment], {
                'code': str(int(time())),
                'endicia_mailpiece_shape': 'Flat',
            })

            # Before generating labels
            # There is no tracking number generated
            # And no attachment cerated for labels
            self.assertFalse(shipment.tracking_number)
            attatchment = self.IrAttachment.search([])
            self.assertEqual(len(attatchment), 0)

            # Make shipment in packed state.
            shipment.assign([shipment])
            shipment.pack([shipment])

            with Transaction().set_context(company=self.company.id):

                # Call method to generate labels.
                shipment.generate_shipping_labels()

            self.assertTrue(shipment.tracking_number)
            self.assertTrue(
                self.IrAttachment.search([
                    ('resource', '=', 'stock.shipment.out,%s' % shipment.id)
                ], count=True) > 0
            )

    def test_0016_generate_endicia_flat_label_using_wizard(self):
        """
        Test case to generate Endicia labels using wizard
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):

            # Call method to create sale order
            self.setup_defaults()

            shipment, = self.StockShipmentOut.search([])
            self.StockShipmentOut.write([shipment], {
                'code': str(int(time())),
                'endicia_mailpiece_shape': 'Flat',
            })

            # Before generating labels
            # There is no tracking number generated
            # And no attachment cerated for labels
            self.assertFalse(shipment.tracking_number)
            attatchment = self.IrAttachment.search([])
            self.assertEqual(len(attatchment), 0)

            # Make shipment in packed state.
            shipment.assign([shipment])
            shipment.pack([shipment])

            with Transaction().set_context(
                company=self.company.id, active_id=shipment
            ):
                # Call method to generate labels.
                session_id, start_state, _ = self.GenerateLabel.create()

                generate_label = self.GenerateLabel(session_id)

                result = generate_label.default_start({})

                self.assertEqual(result['shipment'], shipment.id)
                self.assertEqual(result['carrier'], shipment.carrier.id)

                generate_label.start.shipment = result['shipment']
                generate_label.start.carrier = result['carrier']
                generate_label.start.override_weight = None

                self.assertEqual(
                    generate_label.transition_next(), 'endicia_config'
                )

                result = generate_label.default_endicia_config({})

                self.assertEqual(
                    result['endicia_label_subtype'],
                    shipment.endicia_label_subtype
                )

                self.assertEqual(
                    result['endicia_integrated_form_type'],
                    shipment.endicia_integrated_form_type
                )
                self.assertEqual(
                    result['endicia_package_type'],
                    shipment.endicia_package_type
                )

                self.assertEqual(
                    result['endicia_include_postage'],
                    shipment.endicia_include_postage
                )

                generate_label.endicia_config.endicia_label_subtype = \
                    result['endicia_label_subtype']
                generate_label.endicia_config.endicia_integrated_form_type = \
                    result['endicia_integrated_form_type']
                generate_label.endicia_config.endicia_package_type = \
                    result['endicia_package_type']
                generate_label.endicia_config.endicia_include_postage = \
                    result['endicia_include_postage']

                result = generate_label.default_generate({})

                self.assertEqual(
                    result['message'],
                    'Shipment labels have been generated via ENDICIA and '
                    'saved as attachments for the shipment'
                )

            self.assertTrue(shipment.tracking_number)
            self.assertTrue(
                self.IrAttachment.search([
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

            shipments = self.StockShipmentOut.search([])

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
                self.IrAttachment.search([
                    ('resource', '=', 'endicia.shipment.bag,%s' % bag.id)
                ], count=True), 1
            )

            # Create new sale and shipment
            self.create_sale(self.sale_party)

            shipment, = self.StockShipmentOut.search([
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
                self.IrAttachment.search([
                    ('resource', '=', 'endicia.shipment.bag,%s' % bag.id)
                ], count=True), 1
            )

    def test_0030_endicia_shipping_rates(self):
        """
        Tests get_endicia_shipping_rates method.
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()

            with Transaction().set_context(company=self.company.id):

                # Create sale order
                sale, = self.Sale.create([{
                    'reference': 'S-1001',
                    'payment_term': self.payment_term,
                    'party': self.sale_party.id,
                    'invoice_address': self.sale_party.addresses[0].id,
                    'shipment_address': self.sale_party.addresses[0].id,
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

                self.StockLocation.write([sale.warehouse], {
                    'address': self.company.party.addresses[0].id,
                })

                self.assertEqual(len(sale.lines), 1)

            with Transaction().set_context(sale=sale):
                self.assertGreater(len(self.carrier.get_rates()), 0)

    def test_0035_generate_endicia_flat_label_customs_form(self):
        """Test case to generate Endicia labels with customs forms
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):

            # Call method to create sale order
            self.setup_defaults()

            endicia_mailclass, = self.EndiciaMailclass.search([
                ('value', '=', 'PriorityMailInternational')
            ])

            shipment, = self.StockShipmentOut.search([])
            self.StockShipmentOut.write([shipment], {
                'code': str(int(time())),
                'endicia_mailpiece_shape': 'Flat',
                'endicia_integrated_form_type': 'Form2976',
                'endicia_label_subtype': 'Integrated',
                'endicia_mailclass': endicia_mailclass.id,
                'delivery_address': self.sale_party.addresses[1].id,
            })

            # Before generating labels
            # There is no tracking number generated
            # And no attachment cerated for labels
            self.assertFalse(shipment.tracking_number)
            attatchment = self.IrAttachment.search([])
            self.assertEqual(len(attatchment), 0)

            # Make shipment in packed state.
            shipment.assign([shipment])
            shipment.pack([shipment])

            with Transaction().set_context(company=self.company.id):

                # Call method to generate labels.
                shipment.generate_shipping_labels()

            self.assertTrue(shipment.tracking_number)
            self.assertTrue(
                self.IrAttachment.search([
                    ('resource', '=', 'stock.shipment.out,%s' % shipment.id)
                ], count=True) > 1
            )

    def test_0040_generate_endicia_label_for_ca(self):
        """Test case to generate Endicia labels for ca
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):

            # Call method to create sale order
            self.setup_defaults()

            endicia_mailclass, = self.EndiciaMailclass.search([
                ('value', '=', 'First')
            ])

            shipment, = self.StockShipmentOut.search([])
            self.StockShipmentOut.write([shipment], {
                'code': str(int(time())),
                'endicia_mailpiece_shape': None,
                'endicia_package_type': 'Merchandise',
                'endicia_integrated_form_type': 'Form2976',
                'endicia_label_subtype': 'None',
                'endicia_mailclass': endicia_mailclass.id,
                'delivery_address': self.sale_party.addresses[2].id,
            })

            # Before generating labels
            # There is no tracking number generated
            # And no attachment cerated for labels
            self.assertFalse(shipment.tracking_number)
            attatchment = self.IrAttachment.search([])
            self.assertEqual(len(attatchment), 0)

            # Make shipment in packed state.
            shipment.assign([shipment])
            shipment.pack([shipment])

            with Transaction().set_context(company=self.company.id):

                # Call method to generate labels.
                shipment.generate_shipping_labels()

            self.assertTrue(shipment.tracking_number)
            self.assertTrue(
                self.IrAttachment.search([
                    ('resource', '=', 'stock.shipment.out,%s' % shipment.id)
                ], count=True) > 0
            )


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
