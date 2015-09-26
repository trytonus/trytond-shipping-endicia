# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from decimal import Decimal
import logging

from endicia import CalculatingPostageAPI, PostageRatesAPI
from endicia.tools import objectify_response
from endicia.exceptions import RequestError
from trytond.model import ModelView, fields
from trytond.pool import PoolMeta, Pool
from trytond.transaction import Transaction
from trytond.pyson import Eval, Bool


__all__ = ['Configuration', 'Sale']
__metaclass__ = PoolMeta


ENDICIA_PACKAGE_TYPES = [
    ('Documents', 'Documents'),
    ('Gift', 'Gift'),
    ('Merchandise', 'Merchandise'),
    ('Other', 'Other'),
    ('Sample', 'Sample')
]
MAILPIECE_SHAPES = [
    (None, ''),
    ('Card', 'Card'),
    ('Letter', 'Letter'),
    ('Flat', 'Flat'),
    ('Parcel', 'Parcel'),

    ('LargeParcel', 'LargeParcel'),
    ('IrregularParcel', 'IrregularParcel'),

    ('FlatRateEnvelope', 'FlatRateEnvelope'),
    ('FlatRateLegalEnvelope', 'FlatRateLegalEnvelope'),
    ('FlatRatePaddedEnvelope', 'FlatRatePaddedEnvelope'),
    ('FlatRateGiftCardEnvelope', 'FlatRateGiftCardEnvelope'),
    ('FlatRateWindowEnvelope', 'FlatRateWindowEnvelope'),
    ('FlatRateCardboardEnvelope', 'FlatRateCardboardEnvelope'),
    ('SmallFlatRateEnvelope', 'SmallFlatRateEnvelope'),

    ('SmallFlatRateBox', 'SmallFlatRateBox'),
    ('MediumFlatRateBox', 'MediumFlatRateBox'),
    ('LargeFlatRateBox', 'LargeFlatRateBox'),
    ('DVDFlatRateBox', 'DVDFlatRateBox'),
    ('LargeVideoFlatRateBox', 'LargeVideoFlatRateBox'),

    ('RegionalRateBoxA', 'RegionalRateBoxA'),
    ('RegionalRateBoxB', 'RegionalRateBoxB'),
    ('RegionalRateBoxC', 'RegionalRateBoxC'),
]

logger = logging.getLogger(__name__)


class Configuration:
    'Sale Configuration'
    __name__ = 'sale.configuration'

    endicia_mailclass = fields.Many2One(
        'endicia.mailclass', 'Default MailClass',
    )
    endicia_label_subtype = fields.Selection([
        ('None', 'None'),
        ('Integrated', 'Integrated')
    ], 'Label Subtype')
    endicia_integrated_form_type = fields.Selection([
        (None, ''),
        ('Form2976', 'Form2976(Same as CN22)'),
        ('Form2976A', 'Form2976(Same as CP72)'),
    ], 'Integrated Form Type')
    endicia_include_postage = fields.Boolean('Include Postage ?')
    endicia_package_type = fields.Selection(
        ENDICIA_PACKAGE_TYPES, 'Package Content Type'
    )
    endicia_mailpiece_shape = fields.Selection(
        MAILPIECE_SHAPES, 'Endicia MailPiece Shape'
    )

    @staticmethod
    def default_endicia_label_subtype():
        # This is the default value as specified in Endicia doc
        return 'None'

    @staticmethod
    def default_endicia_integrated_form_type():
        return None

    @staticmethod
    def default_endicia_package_type():
        # This is the default value as specified in Endicia doc
        return 'Other'

    @staticmethod
    def default_endicia_mailpiece_shape():
        """
        This is not a required field, so send None by default
        """
        return None


class Sale:
    "Sale"
    __name__ = 'sale.sale'

    endicia_mailclass = fields.Many2One(
        'endicia.mailclass', 'MailClass', states={
            'readonly': ~Eval('state').in_(['draft', 'quotation']),
        }, depends=['state']
    )
    endicia_mailpiece_shape = fields.Selection(
        MAILPIECE_SHAPES, 'Endicia MailPiece Shape', states={
            'readonly': ~Eval('state').in_(['draft', 'quotation']),
        }, depends=['state']
    )
    is_endicia_shipping = fields.Function(
        fields.Boolean('Is Endicia Shipping?', readonly=True),
        'get_is_endicia_shipping'
    )

    @classmethod
    def view_attributes(cls):
        return super(Sale, cls).view_attributes() + [
            ('//page[@id="endicia"]', 'states', {
                'invisible': ~Bool(Eval('is_endicia_shipping'))
            })]

    def _get_weight_uom(self):
        """
        Returns uom for endicia
        """
        UOM = Pool().get('product.uom')

        if self.is_endicia_shipping:

            # Endicia by default uses this uom
            return UOM.search([('symbol', '=', 'oz')])[0]

        return super(Sale, self)._get_weight_uom()

    @staticmethod
    def default_endicia_mailclass():
        Config = Pool().get('sale.configuration')
        config = Config(1)
        return config.endicia_mailclass and config.endicia_mailclass.id or None

    @classmethod
    def __setup__(cls):
        super(Sale, cls).__setup__()
        cls._error_messages.update({
            'mailclass_missing':
                'Select a mailclass to ship using Endicia [USPS].'
        })
        cls._buttons.update({
            'update_endicia_shipment_cost': {
                'invisible': Eval('state') != 'quotation'
            }
        })

    @fields.depends('is_endicia_shipping', 'carrier')
    def on_change_carrier(self):
        super(Sale, self).on_change_carrier()

        self.is_endicia_shipping = self.carrier and \
            self.carrier.carrier_cost_method == 'endicia' or None

    def _get_carrier_context(self):
        "Pass sale in the context"
        context = super(Sale, self)._get_carrier_context()

        if not self.carrier.carrier_cost_method == 'endicia':
            return context

        context = context.copy()
        context['sale'] = self.id
        return context

    def on_change_lines(self):
        """Pass a flag in context which indicates the get_sale_price method
        of endicia carrier not to calculate cost on each line change
        """
        with Transaction().set_context({'ignore_carrier_computation': True}):
            return super(Sale, self).on_change_lines()

    def apply_endicia_shipping(self):
        "Add a shipping line to sale for endicia"
        Currency = Pool().get('currency.currency')

        if self.carrier and self.carrier.carrier_cost_method == 'endicia':
            if not self.endicia_mailclass:
                self.raise_user_error('mailclass_missing')
            with Transaction().set_context(self._get_carrier_context()):
                shipment_cost_usd = self.carrier.get_sale_price()
                if not shipment_cost_usd[0]:
                    return
            # Convert the shipping cost to sale currency from USD
            usd, = Currency.search([('code', '=', 'USD')])
            shipment_cost = Currency.compute(
                usd, shipment_cost_usd[0], self.currency
            )
            self.add_shipping_line(
                shipment_cost,
                '%s - %s' % (
                    self.carrier.party.name, self.endicia_mailclass.name
                )
            )

    @classmethod
    def quote(cls, sales):
        res = super(Sale, cls).quote(sales)
        cls.update_endicia_shipment_cost(sales)
        return res

    @classmethod
    @ModelView.button
    def update_endicia_shipment_cost(cls, sales):
        "Updates the shipping line with new value if any"
        for sale in sales:
            sale.apply_endicia_shipping()

    def create_shipment(self, shipment_type):
        Shipment = Pool().get('stock.shipment.out')

        with Transaction().set_context(ignore_carrier_computation=True):
            # disable `carrier cost computation`(default behaviour) as cost
            # should only be computed after updating mailclass else error may
            # occur, with improper mailclass.
            shipments = super(Sale, self).create_shipment(shipment_type)
        if shipment_type == 'out' and shipments and self.carrier and \
                self.carrier.carrier_cost_method == 'endicia':
            Shipment.write(shipments, {
                'endicia_mailclass': self.endicia_mailclass.id,
                'endicia_mailpiece_shape': self.endicia_mailpiece_shape,
                'is_endicia_shipping': self.is_endicia_shipping,
            })
        return shipments

    def get_endicia_shipping_cost(self, mailclass=None):
        """Returns the calculated shipping cost as sent by endicia

        :param mailclass: endicia mailclass for which cost to be fetched

        :returns: The shipping cost in USD
        """
        Carrier = Pool().get('carrier')
        EndiciaConfiguration = Pool().get('endicia.configuration')

        endicia_credentials = EndiciaConfiguration(1).get_endicia_credentials()
        carrier, = Carrier.search(['carrier_cost_method', '=', 'endicia'])

        if not mailclass and not self.endicia_mailclass:
            self.raise_user_error('mailclass_missing')

        from_address = self._get_ship_from_address()
        to_address = self.shipment_address
        to_zip = to_address.zip

        if to_address.country and to_address.country.code == 'US':
            # Domestic
            to_zip = to_zip and to_zip[:5]
        else:
            # International
            to_zip = to_zip and to_zip[:15]

        # Endicia only support 1 decimal place in weight
        weight_oz = "%.1f" % self.package_weight
        calculate_postage_request = CalculatingPostageAPI(
            mailclass=mailclass or self.endicia_mailclass.value,
            MailpieceShape=self.endicia_mailpiece_shape,
            weightoz=weight_oz,
            from_postal_code=from_address.zip and from_address.zip[:5],
            to_postal_code=to_zip,
            to_country_code=to_address.country and to_address.country.code,
            accountid=endicia_credentials.account_id,
            requesterid=endicia_credentials.requester_id,
            passphrase=endicia_credentials.passphrase,
            test=endicia_credentials.is_test,
        )

        # Logging.
        logger.debug(
            'Making Postage Request for shipping cost of'
            'Sale ID: {0} and Carrier ID: {1}'
            .format(self.id, carrier.id)
        )
        logger.debug('--------POSTAGE REQUEST--------')
        logger.debug(str(calculate_postage_request.to_xml()))
        logger.debug('--------END REQUEST--------')

        try:
            response = calculate_postage_request.send_request()
        except RequestError, e:
            self.raise_user_error(unicode(e))

        # Logging.
        logger.debug('--------POSTAGE RESPONSE--------')
        logger.debug(str(response))
        logger.debug('--------END RESPONSE--------')

        return self.fetch_endicia_postage_rate(
            objectify_response(response).PostagePrice
        )

    def _get_endicia_mail_classes(self):
        """
        Returns list of endicia mailclass instances eligible for this sale

        Downstream module can decide the eligibility of mail classes for sale
        """
        Mailclass = Pool().get('endicia.mailclass')

        return Mailclass.search([])

    def _make_endicia_rate_line(self, carrier, mailclass, shipment_rate):
        """
        Build a rate tuple from shipment_rate and mailclass
        """
        Currency = Pool().get('currency.currency')

        usd, = Currency.search([('code', '=', 'USD')])
        write_vals = {
            'carrier': carrier.id,
            'endicia_mailclass': mailclass.id,
        }
        return (
            carrier._get_endicia_mailclass_name(mailclass),
            shipment_rate,
            usd,
            {},
            write_vals
        )

    def get_endicia_shipping_rates(self, silent=True):
        """
        Call the rates service and get possible quotes for shipment for eligible
        mail classes
        """
        Carrier = Pool().get('carrier')
        UOM = Pool().get('product.uom')
        EndiciaConfiguration = Pool().get('endicia.configuration')

        endicia_credentials = EndiciaConfiguration(1).get_endicia_credentials()

        carrier, = Carrier.search(['carrier_cost_method', '=', 'endicia'])

        from_address = self._get_ship_from_address()
        mailclass_type = "Domestic" if self.shipment_address.country.code == 'US' \
            else "International"

        uom_oz = UOM.search([('symbol', '=', 'oz')])[0]

        # Endicia only support 1 decimal place in weight
        weight_oz = "%.1f" % self._get_package_weight(uom_oz)
        to_zip = self.shipment_address.zip
        if mailclass_type == 'Domestic':
            to_zip = to_zip and to_zip[:5]
        else:
            # International
            to_zip = to_zip and to_zip[:15]
        postage_rates_request = PostageRatesAPI(
            mailclass=mailclass_type,
            weightoz=weight_oz,
            from_postal_code=from_address.zip[:5],
            to_postal_code=to_zip,
            to_country_code=self.shipment_address.country.code,
            accountid=endicia_credentials.account_id,
            requesterid=endicia_credentials.requester_id,
            passphrase=endicia_credentials.passphrase,
            test=endicia_credentials.is_test,
        )

        # Logging.
        logger.debug(
            'Making Postage Rates Request for shipping rates of'
            'Sale ID: {0} and Carrier ID: {1}'
            .format(self.id, carrier.id)
        )
        logger.debug('--------POSTAGE RATES REQUEST--------')
        logger.debug(str(postage_rates_request.to_xml()))
        logger.debug('--------END REQUEST--------')

        try:
            response_xml = postage_rates_request.send_request()
            response = objectify_response(response_xml)
        except RequestError, e:
            self.raise_user_error(unicode(e))

        # Logging.
        logger.debug('--------POSTAGE RATES RESPONSE--------')
        logger.debug(str(response_xml))
        logger.debug('--------END RESPONSE--------')

        allowed_mailclasses = {
            mailclass.value: mailclass
            for mailclass in self._get_endicia_mail_classes()
        }

        rate_lines = []
        for postage_price in response.PostagePrice:
            mailclass = allowed_mailclasses.get(postage_price.MailClass)
            if not mailclass:
                continue
            cost = self.fetch_endicia_postage_rate(postage_price)
            rate_lines.append(
                self._make_endicia_rate_line(carrier, mailclass, cost)
            )
        return filter(None, rate_lines)

    def fetch_endicia_postage_rate(self, postage_price_node):
        """
        Fetch postage rate from response
        """
        return Decimal(postage_price_node.get('TotalAmount'))

    def get_is_endicia_shipping(self, name):
        """
        Check if shipping is from USPS
        """
        return self.carrier and self.carrier.carrier_cost_method == 'endicia'
