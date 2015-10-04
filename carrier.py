# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

from decimal import Decimal
from trytond import backend
from trytond.model import ModelSQL, ModelView, fields, ModelSingleton
from trytond.pool import PoolMeta, Pool
from trytond.transaction import Transaction
from trytond.pyson import Eval

REQUIRED_IF_ENDICIA = {
    'required': Eval('carrier_cost_method') == 'endicia',
    'invisible': Eval('carrier_cost_method') != 'endicia',
}

__all__ = ['Carrier', 'EndiciaMailclass', ]
__metaclass__ = PoolMeta


class Carrier(ModelSingleton):
    "Carrier"
    __name__ = 'carrier'

    # endicia start from here
    account_id = fields.Char('Account Id', states=REQUIRED_IF_ENDICIA)
    requester_id = fields.Char('Requester Id', states=REQUIRED_IF_ENDICIA)
    passphrase = fields.Char('Passphrase', states=REQUIRED_IF_ENDICIA)
    is_test = fields.Boolean('Is Test', states=REQUIRED_IF_ENDICIA)

    @classmethod
    def __register__(cls, module_name):
        TableHandler = backend.get('TableHandler')
        cursor = Transaction().cursor
        # Migration from 3.4.0.6 : Migrate account_id field to string
        if backend.name() == 'postgresql':
            cursor.execute(
                    'SELECT pg_typeof("account_id") '
                    'FROM carrier '
                    'LIMIT 1',
            )
            # Check if account_id is integer field
            # is_integer = cursor.fetchone()[0] == 'integer'

            #if is_integer:
            # Migrate integer field to string
            table = TableHandler(cursor, cls, module_name)
            table.alter_type('account_id', 'varchar')

        super(Carrier, cls).__register__(module_name)

    @classmethod
    def __setup__(cls):
        super(Carrier, cls).__setup__()
        selection = ('endicia', 'USPS [Endicia]')
        if selection not in cls.carrier_cost_method.selection:
            cls.carrier_cost_method.selection.append(selection)

        cls._error_messages.update({
            'endicia_credentials_required':
                'Endicia settings on endicia configuration are incomplete.',
        })

    def get_rates(self):
        """
        Return list of tuples as:
            [
                (
                    <display method name>, <rate>, <currency>, <metadata>,
                    <write_vals>
                )
                ...
            ]
        """
        Sale = Pool().get('sale.sale')

        sale = Transaction().context.get('sale')

        if sale and self.carrier_cost_method == 'endicia':
            return Sale(sale).get_endicia_shipping_rates()

        return super(Carrier, self).get_rates()

    def get_sale_price(self):
        """Estimates the shipment rate for the current shipment

        The get_sale_price implementation by tryton's carrier module
        returns a tuple of (value, currency_id)

        :returns: A tuple of (value, currency_id which in this case is USD)
        """
        Sale = Pool().get('sale.sale')
        Shipment = Pool().get('stock.shipment.out')
        Currency = Pool().get('currency.currency')

        shipment = Transaction().context.get('shipment')
        sale = Transaction().context.get('sale')
        usd, = Currency.search([('code', '=', 'USD')])  # Default currency

        if Transaction().context.get('ignore_carrier_computation'):
            return Decimal('0'), usd.id
        if not sale and not shipment:
            return Decimal('0'), usd.id

        if self.carrier_cost_method != 'endicia':
            return super(Carrier, self).get_sale_price()

        usd, = Currency.search([('code', '=', 'USD')])
        if sale:
            return Sale(sale).get_endicia_shipping_cost(), usd.id

        if shipment:
            return Shipment(shipment).get_endicia_shipping_cost(), usd.id

        return Decimal('0'), usd.id

    def _get_endicia_mailclass_name(self, mailclass):
        """
        Return endicia service name

        This method can be overriden by downstream modules to change the
        default display name of service.
        """
        return "%s %s" % (
            self.carrier_product.code, mailclass.display_name or mailclass.name
        )


class EndiciaMailclass(ModelSQL, ModelView):
    "Endicia mailclass"
    __name__ = 'endicia.mailclass'

    active = fields.Boolean('Active', select=True)
    name = fields.Char('Name', required=True, select=True, readonly=True)
    value = fields.Char('Value', required=True, select=True, readonly=True)
    method_type = fields.Selection([
        ('domestic', 'Domestic'),
        ('international', 'International'),
    ], 'Type', required=True, select=True, readonly=True)
    display_name = fields.Char('Display Name', select=True)

    @staticmethod
    def default_active():
        return True

    @staticmethod
    def check_xml_record(records, values):
        if 'display_name' in values and len(values) == 1:
            # Allow editing if display_name is the only key in values
            return True
        return False
