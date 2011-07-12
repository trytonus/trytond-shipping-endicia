#!/usr/bin/env python
#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from __future__ import with_statement
import datetime
from decimal import Decimal

import sys, os
DIR = os.path.abspath(os.path.normpath(os.path.join(__file__,
    '..', '..', '..', '..', '..', 'trytond')))
if os.path.isdir(DIR):
    sys.path.insert(0, os.path.dirname(DIR))

import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, DB_NAME, USER, CONTEXT
from trytond.transaction import Transaction


class EndiciaTestCase(unittest.TestCase):
    """
    Test Endicia Integration Module
    """

    def setUp(self):
        trytond.tests.test_tryton.install_module('endicia_integration')
        self.currency = POOL.get('currency.currency')
        self.company = POOL.get('company.company')
        self.product = POOL.get('product.product')
        self.category = POOL.get('product.category')
        self.uom = POOL.get('product.uom')
        self.shipment = POOL.get('stock.shipment.out')
        self.party = POOL.get('party.party')
        self.address = POOL.get('party.address')
        self.country = POOL.get('country.country')
        self.subdivision = POOL.get('country.subdivision')
        self.contact_mech = POOL.get('party.contact_mechanism')
        self.user = POOL.get('res.user')
        self.stock_location = POOL.get('stock.location')
        self.move = POOL.get('stock.move')
        self.ship_estimate_wiz_obj = POOL.get('shipment.estimate.wizard', 
            type='wizard')
        self.ship_make_wiz_obj = POOL.get('shipment.make.wizard', 
            type='wizard')
        self.shipment_method = POOL.get('shipment.method')
        self.attachment = POOL.get('ir.attachment')

    def test_0010_estimate_cost(self):
        """Estimate the cost for a shipment
        """
        with Transaction().start(DB_NAME, USER, CONTEXT) as transaction:
            currency = self.currency.create({
                'name': 'US Dollar',
                'symbol': 'USD',
                'code': 'USD',
                })
            sender = self.party.create({
                'name': 'Openlabs'
                })
            company_id = self.company.create({
                'party': sender,
                'currency': currency,
                'account_id': 123456,
                'requester_id': 123456,
                'passphrase': 'PassPhrase',
                'usps_test': True,
                })
            company = self.company.browse(company_id)
            self.user.write(USER, {'main_company': company_id})
            self.user.write(USER, {'company': company_id})
            party_id = self.party.create({
                'name': 'Party 1',
                })
            country_id = self.country.create({
                'name': 'United States',
                'code': 'US',
                })
            from_state_id = self.subdivision.create({
                'name': 'Idaho',
                'code': 'ID',
                'country': country_id,
                'type': 'state',
                })
            to_state_id = self.subdivision.create({
                'name': 'California',
                'code': 'CA',
                'country': country_id,
                'type': 'state',
                })
            from_phone_id = self.contact_mech.create({
                'type': 'phone',
                'other_value': '8005551212',
                'party': company.party.id,
                })
            to_phone_id = self.contact_mech.create({
                'type': 'phone',
                'other_value': '8005763279',
                'party': party_id,
                })
            from_address_id = self.address.create({
                'party': company.party.id,
                'name': 'John Doe',
                'street': '123 Main Street',
                'city': 'Boise',
                'subdivision': from_state_id,
                'country': country_id,
                'zip': '83702',
                })
            to_address_id = self.address.create({
                'party': party_id,
                'name': 'Shalabh Aggarwal',
                'street': '250 High Street',
                'city': 'Palo Alto',
                'subdivision': to_state_id,
                'country': country_id,
                'zip': '84301',
                })
            category_id = self.category.create({
                'name': 'Category1',
                })
            kg_id, = self.uom.search([('name', '=', 'Kilogram')])
            product_id = self.product.create({
                'name': 'Product1',
                'type': 'stockable',
                'category': category_id,
                'list_price': Decimal('20.0'),
                'cost_price_method': 'fixed',
                'default_uom': kg_id,
                'customs_desc': 'Product1',
                'customs_value': 20.0,
                'weight': Decimal('1.0'),
                })
            warehouse_id, = self.stock_location.search([
                ('code', '=', 'WH')
                ], limit=1)
            self.stock_location.write(warehouse_id, {
                'address': from_address_id,
                })
            customer_id, = self.stock_location.search([('code', '=', 'CUS')])
            storage_id, = self.stock_location.search([('code', '=', 'STO')])

            today = datetime.date.today()
            currency_id = self.company.read(company.id,
                    ['currency'])['currency']
            move_id = self.move.create({
                'product': product_id,
                'uom': kg_id,
                'quantity': 2,
                'from_location': storage_id,
                'to_location': customer_id,
                'planned_date': today,
                'state': 'draft',
                'company': company.id,
                'unit_price': Decimal('1'),
                'currency': currency_id,
                })

            shipment_id = self.shipment.create({
                'planned_date': today,
                'customer': party_id,
                'delivery_address': to_address_id,
                'warehouse': warehouse_id,
                'moves': [('add', [move_id])],
                })
            method_id, = self.shipment_method.search(
                [('value', '=', 'Priority')], limit=1)
            ship_estimate = self.ship_estimate_wiz_obj.create()
            rv = self.ship_estimate_wiz_obj.execute(ship_estimate, {
                'form': {
                    'method': method_id,
                    },
                'id': shipment_id,
                    },
                'get_estimate')
            self.assertTrue(rv.get('datas').get('amount'))

    def test_0020_make_shipment(self):
        """Complete a shipment and store label
        """
        with Transaction().start(DB_NAME, USER, CONTEXT) as transaction:
            currency = self.currency.create({
                'name': 'US Dollar',
                'symbol': 'USD',
                'code': 'USD',
                })
            sender = self.party.create({
                'name': 'Openlabs'
                })
            company_id = self.company.create({
                'party': sender,
                'currency': currency,
                'account_id': 123456,
                'requester_id': 123456,
                'passphrase': 'PassPhrase',
                'usps_test': True,
                })
            company = self.company.browse(company_id)
            self.user.write(USER, {'main_company': company_id})
            self.user.write(USER, {'company': company_id})
            party_id = self.party.create({
                'name': 'Party 1',
                })
            country_id = self.country.create({
                'name': 'United States',
                'code': 'US',
                })
            from_state_id = self.subdivision.create({
                'name': 'Idaho',
                'code': 'US-ID',
                'country': country_id,
                'type': 'state',
                })
            to_state_id = self.subdivision.create({
                'name': 'California',
                'code': 'US-CA',
                'country': country_id,
                'type': 'state',
                })
            from_phone_id = self.contact_mech.create({
                'type': 'phone',
                'other_value': '8005551212',
                'party': company.party.id,
                })
            to_phone_id = self.contact_mech.create({
                'type': 'phone',
                'other_value': '8005763279',
                'party': party_id,
                })
            from_address_id = self.address.create({
                'party': company.party.id,
                'name': 'John Doe',
                'street': '123 Main Street',
                'city': 'Boise',
                'subdivision': from_state_id,
                'country': country_id,
                'zip': '83702',
                })
            to_address_id = self.address.create({
                'party': party_id,
                'name': 'Shalabh Aggarwal',
                'street': '250 High Street',
                'city': 'Palo Alto',
                'subdivision': to_state_id,
                'country': country_id,
                'zip': '84301',
                })
            category_id = self.category.create({
                'name': 'Category1',
                })
            kg_id, = self.uom.search([('name', '=', 'Kilogram')])
            product_id = self.product.create({
                'name': 'Product1',
                'type': 'stockable',
                'category': category_id,
                'list_price': Decimal('20.0'),
                'cost_price_method': 'fixed',
                'default_uom': kg_id,
                'customs_desc': 'Product1',
                'customs_value': 20.0,
                'weight': Decimal('0.25'),
                })
            warehouse_id, = self.stock_location.search([
                ('code', '=', 'WH')
                ], limit=1)
            self.stock_location.write(warehouse_id, {
                'address': from_address_id,
                })
            customer_id, = self.stock_location.search([('code', '=', 'CUS')])
            storage_id, = self.stock_location.search([('code', '=', 'STO')])

            today = datetime.date.today()
            currency_id = self.company.read(company.id,
                    ['currency'])['currency']
            move_id = self.move.create({
                'product': product_id,
                'uom': kg_id,
                'quantity': 2,
                'from_location': storage_id,
                'to_location': customer_id,
                'planned_date': today,
                'state': 'draft',
                'company': company.id,
                'unit_price': Decimal('1'),
                'currency': currency_id,
                })

            shipment_id = self.shipment.create({
                'planned_date': today,
                'customer': party_id,
                'delivery_address': to_address_id,
                'warehouse': warehouse_id,
                'moves': [('add', [move_id])],
                })
            method_id, = self.shipment_method.search(
                [('value', '=', 'First')], limit=1)
            ship_make = self.ship_make_wiz_obj.create()

            # Storing the number of attachents before the label is generated
            attachments0 = self.attachment.search([])

            rv = self.ship_make_wiz_obj.execute(ship_make, {
                'form': {
                    'method': method_id,
                    'label_sub_type': 'None',
                    'integrated_form_type': 'Form2976',
                    'include_postage': True,
                    },
                'id': shipment_id,
                    },
                'make_shipment')
            self.assertEqual(rv.get('datas').get('response'), 'Success')

            # Storing the number of attachents after the label is generated
            attachments1 = self.attachment.search([])

            # Asserting that the number of attachments after the label is 
            # generated is 1 more than it was before.
            self.assertEqual(len(attachments1), len(attachments0)+1)


def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(EndiciaTestCase))
    return suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
