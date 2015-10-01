# -*- encoding: utf-8 -*-
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

'''
Inherit stock for endicia API
'''
from decimal import Decimal, ROUND_UP
import base64
import math
import logging

from endicia import ShippingLabelAPI, LabelRequest, RefundRequestAPI, \
    BuyingPostageAPI, Element, CalculatingPostageAPI
from endicia.tools import objectify_response, get_images
from endicia.exceptions import RequestError

from trytond.model import Workflow, ModelView, fields
from trytond.wizard import Wizard, StateView, Button
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.rpc import RPC

from .sale import ENDICIA_PACKAGE_TYPES, MAILPIECE_SHAPES


__metaclass__ = PoolMeta
__all__ = [
    'ShipmentOut', 'ShippingEndicia', 'GenerateShippingLabel',
    'EndiciaRefundRequestWizardView', 'EndiciaRefundRequestWizard',
    'BuyPostageWizardView', 'BuyPostageWizard',
]

STATES = {
    'readonly': Eval('state') == 'done',
}

logger = logging.getLogger(__name__)

quantize_2_decimal = lambda v: Decimal("%f" % v).quantize(
    Decimal('.01'), rounding=ROUND_UP
)


class ShipmentOut:
    "Shipment Out"
    __name__ = 'stock.shipment.out'

    endicia_mailclass = fields.Many2One(
        'endicia.mailclass', 'MailClass', states=STATES, depends=['state']
    )
    endicia_mailpiece_shape = fields.Selection(
        MAILPIECE_SHAPES, 'Endicia MailPiece Shape', states=STATES,
        depends=['state']
    )
    endicia_shipment_bag = fields.Many2One(
        'endicia.shipment.bag', 'Endicia Shipment Bag')
    endicia_label_subtype = fields.Selection([
        ('None', 'None'),
        ('Integrated', 'Integrated')
    ], 'Label Subtype', states=STATES, depends=['state'])
    endicia_integrated_form_type = fields.Selection([
        (None, ''),
        ('Form2976', 'Form2976(Same as CN22)'),
        ('Form2976A', 'Form2976(Same as CP72)'),
    ], 'Integrated Form Type', states=STATES, depends=['state'])
    endicia_include_postage = fields.Boolean(
        'Include Postage ?', states=STATES, depends=['state']
    )
    endicia_package_type = fields.Selection(
        ENDICIA_PACKAGE_TYPES, 'Package Content Type',
        states=STATES, depends=['state']
    )
    is_endicia_shipping = fields.Function(
        fields.Boolean('Is Endicia Shipping?', readonly=True),
        'get_is_endicia_shipping'
    )
    endicia_refunded = fields.Boolean('Refunded ?', readonly=True)

    def _get_weight_uom(self):
        """
        Returns uom for endicia
        """
        UOM = Pool().get('product.uom')

        if self.is_endicia_shipping:

            # Endicia by default uses this uom
            return UOM.search([('symbol', '=', 'oz')])[0]

        return super(ShipmentOut, self)._get_weight_uom()

    @staticmethod
    def default_endicia_mailclass():
        Config = Pool().get('sale.configuration')
        config = Config(1)
        return config.endicia_mailclass and config.endicia_mailclass.id or None

    @staticmethod
    def default_endicia_label_subtype():
        Config = Pool().get('sale.configuration')
        config = Config(1)
        return config.endicia_label_subtype

    @staticmethod
    def default_endicia_integrated_form_type():
        Config = Pool().get('sale.configuration')
        config = Config(1)
        return config.endicia_integrated_form_type

    @staticmethod
    def default_endicia_include_postage():
        Config = Pool().get('sale.configuration')
        config = Config(1)
        return config.endicia_include_postage

    @staticmethod
    def default_endicia_package_type():
        Config = Pool().get('sale.configuration')
        config = Config(1)
        return config.endicia_package_type

    @classmethod
    def __setup__(cls):
        super(ShipmentOut, cls).__setup__()
        # There can be cases when people might want to use a different
        # shipment carrier at any state except `done`.
        cls.carrier.states = STATES
        cls._error_messages.update({
            'mailclass_missing':
                'Select a mailclass to ship using Endicia [USPS].',
            'error_label': 'Error in generating label "%s"',
            'tracking_number_already_present':
                'Tracking Number is already present for this shipment.',
            'invalid_state': 'Labels can only be generated when the '
                'shipment is in Packed or Done states only',
            'wrong_carrier': 'Carrier for selected shipment is not Endicia',
        })
        cls.__rpc__.update({
            'make_endicia_labels': RPC(readonly=False, instantiate=0),
            'get_endicia_shipping_cost': RPC(readonly=False, instantiate=0),
        })

    def on_change_carrier(self):
        res = super(ShipmentOut, self).on_change_carrier()

        res['is_endicia_shipping'] = self.carrier and \
            self.carrier.carrier_cost_method == 'endicia'

        return res

    @classmethod
    @ModelView.button
    @Workflow.transition('done')
    def done(cls, shipments):
        """
        Add endicia shipments to a open bag
        """
        EndiciaShipmentBag = Pool().get('endicia.shipment.bag')

        super(ShipmentOut, cls).done(shipments)
        endicia_shipments = filter(
            lambda s: s.carrier and s.carrier.carrier_cost_method == 'endicia',
            shipments
        )

        if not endicia_shipments:
            return

        with Transaction().set_user(0):
            bag = EndiciaShipmentBag.get_bag()
        cls.write(endicia_shipments, {
            'endicia_shipment_bag': bag
        })

    def _get_carrier_context(self):
        "Pass shipment in the context"
        context = super(ShipmentOut, self)._get_carrier_context()

        if not self.carrier.carrier_cost_method == 'endicia':
            return context

        context = context.copy()
        context['shipment'] = self.id
        return context

    def _update_endicia_item_details(self, request):
        '''
        Adding customs items/info and form descriptions to the request

        :param request: Shipping Label API request instance
        '''
        User = Pool().get('res.user')
        UOM = Pool().get('product.uom')

        user = User(Transaction().user)
        uom_oz, = UOM.search([('symbol', '=', 'oz')])
        customsitems = []
        value = 0

        for move in self.outgoing_moves:
            if move.quantity <= 0:
                continue
            weight_oz = quantize_2_decimal(move.get_weight(uom_oz))
            new_item = [
                Element('Description', move.product.name[0:50]),
                Element('Quantity', int(math.ceil(move.quantity))),
                Element('Weight', weight_oz),
                Element('Value', quantize_2_decimal(
                    move.product.customs_value_used
                )),
            ]
            customsitems.append(Element('CustomsItem', new_item))
            value += float(move.product.customs_value_used) * move.quantity

        description = ','.join([
            move.product.name for move in self.outgoing_moves
        ])
        request.add_data({
            'customsinfo': [
                Element('ContentsExplanation', description[:25]),
                Element('CustomsItems', customsitems),
                Element('ContentsType', self.endicia_package_type)
            ]
        })
        total_value = sum(map(
            lambda move: float(move.product.cost_price) * move.quantity,
            self.outgoing_moves
        ))
        request.add_data({
            'ContentsType': self.endicia_package_type,
            'Value': quantize_2_decimal(total_value),
            'Description': description[:50],
            'CustomsCertify': 'TRUE',   # TODO: Should this be part of config ?
            'CustomsSigner': user.name,
        })

    def make_endicia_labels(self):
        """
        Make labels for the given shipment

        :return: Tracking number as string
        """
        Attachment = Pool().get('ir.attachment')
        EndiciaConfiguration = Pool().get('endicia.configuration')

        if self.state not in ('packed', 'done'):
            self.raise_user_error('invalid_state')

        if not (
            self.carrier and
            self.carrier.carrier_cost_method == 'endicia'
        ):
            self.raise_user_error('wrong_carrier')

        if self.tracking_number:
            self.raise_user_error('tracking_number_already_present')

        endicia_credentials = EndiciaConfiguration(1).get_endicia_credentials()

        if not self.endicia_mailclass:
            self.raise_user_error('mailclass_missing')

        mailclass = self.endicia_mailclass.value
        label_request = LabelRequest(
            Test=endicia_credentials.is_test and 'YES' or 'NO',
            LabelType=(
                'International' in mailclass
            ) and 'International' or 'Default',
            # TODO: Probably the following have to be configurable
            ImageFormat="PNG",
            LabelSize="6x4",
            ImageResolution="203",
            ImageRotation="Rotate270",
        )

        # Endicia only support 1 decimal place in weight
        weight_oz = "%.1f" % self.weight
        shipping_label_request = ShippingLabelAPI(
            label_request=label_request,
            weight_oz=weight_oz,
            partner_customer_id=self.delivery_address.id,
            partner_transaction_id=self.id,
            mail_class=mailclass,
            MailpieceShape=self.endicia_mailpiece_shape,
            accountid=endicia_credentials.account_id,
            requesterid=endicia_credentials.requester_id,
            passphrase=endicia_credentials.passphrase,
            test=endicia_credentials.is_test,
        )

        from_address = self._get_ship_from_address()

        shipping_label_request.add_data(
            from_address.address_to_endicia_from_address().data
        )
        shipping_label_request.add_data(
            self.delivery_address.address_to_endicia_to_address().data
        )
        shipping_label_request.add_data({
            'LabelSubtype': self.endicia_label_subtype,
            'IncludePostage':
                self.endicia_include_postage and 'TRUE' or 'FALSE',
        })

        if self.endicia_label_subtype != 'None':
            # Integrated form type needs to be sent for international shipments
            shipping_label_request.add_data({
                'IntegratedFormType': self.endicia_integrated_form_type,
            })

        self._update_endicia_item_details(shipping_label_request)

        # Logging.
        logger.debug(
            'Making Shipping Label Request for'
            'Shipment ID: {0} and Carrier ID: {1}'
            .format(self.id, self.carrier.id)
        )
        logger.debug('--------SHIPPING LABEL REQUEST--------')
        logger.debug(str(shipping_label_request.to_xml()))
        logger.debug('--------END REQUEST--------')

        try:
            response = shipping_label_request.send_request()
        except RequestError, error:
            self.raise_user_error('error_label', error_args=(error,))
        else:
            result = objectify_response(response)

            # Logging.
            logger.debug('--------SHIPPING LABEL RESPONSE--------')
            logger.debug(str(response))
            logger.debug('--------END RESPONSE--------')

            tracking_number = result.TrackingNumber.pyval
            self.__class__.write([self], {
                'tracking_number': unicode(result.TrackingNumber.pyval),
                'cost': Decimal(str(result.FinalPostage.pyval)),
            })

            # Save images as attachments
            images = get_images(result)
            for (id, label) in images:
                Attachment.create([{
                    'name': "%s_%s_USPS-Endicia.png" % (tracking_number, id),
                    'data': buffer(base64.decodestring(label)),
                    'resource': '%s,%s' % (self.__name__, self.id)
                }])

            return str(tracking_number)

    def get_endicia_shipping_cost(self):
        """Returns the calculated shipping cost as sent by endicia

        :returns: The shipping cost in USD
        """
        Carrier = Pool().get('carrier')
        EndiciaConfiguration = Pool().get('endicia.configuration')

        endicia_credentials = EndiciaConfiguration(1).get_endicia_credentials()
        carrier, = Carrier.search(['carrier_cost_method', '=', 'endicia'])

        if not self.endicia_mailclass:
            self.raise_user_error('mailclass_missing')

        from_address = self._get_ship_from_address()
        to_address = self.delivery_address
        to_zip = to_address.zip

        if to_address.country and to_address.country.code == 'US':
            # Domestic
            to_zip = to_zip and to_zip[:5]
        else:
            # International
            to_zip = to_zip and to_zip[:15]

        # Endicia only support 1 decimal place in weight
        weight_oz = "%.1f" % self.weight
        calculate_postage_request = CalculatingPostageAPI(
            mailclass=self.endicia_mailclass.value,
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
            'Making Postage Request for'
            'Shipment ID: {0} and Carrier ID: {1}'
            .format(self.id, carrier.id)
        )
        logger.debug('--------POSTAGE REQUEST--------')
        logger.debug(str(calculate_postage_request.to_xml()))
        logger.debug('--------END REQUEST--------')

        try:
            response = calculate_postage_request.send_request()
        except RequestError, error:
            self.raise_user_error('error_label', error_args=(error,))

        # Logging.
        logger.debug('--------POSTAGE RESPONSE--------')
        logger.debug(str(response))
        logger.debug('--------END RESPONSE--------')

        return Decimal(
            objectify_response(response).PostagePrice.get('TotalAmount')
        )

    def get_is_endicia_shipping(self, name):
        """
        Check if shipping is from USPS
        """
        return self.carrier and self.carrier.carrier_cost_method == 'endicia'


class EndiciaRefundRequestWizardView(ModelView):
    """Endicia Refund Wizard View
    """
    __name__ = 'endicia.refund.wizard.view'

    refund_status = fields.Text('Refund Status', readonly=True,)
    refund_approved = fields.Boolean('Refund Approved ?', readonly=True,)


class EndiciaRefundRequestWizard(Wizard):
    """A wizard to cancel the current shipment and refund the cost
    """
    __name__ = 'endicia.refund.wizard'

    start = StateView(
        'endicia.refund.wizard.view',
        'shipping_endicia.endicia_refund_wizard_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Request Refund', 'request_refund', 'tryton-ok'),
        ]
    )
    request_refund = StateView(
        'endicia.refund.wizard.view',
        'shipping_endicia.endicia_refund_wizard_view_form', [
            Button('OK', 'end', 'tryton-ok'),
        ]
    )

    @classmethod
    def __setup__(self):
        super(EndiciaRefundRequestWizard, self).__setup__()
        self._error_messages.update({
            'wrong_carrier': 'Carrier for selected shipment is not Endicia'
        })

    def default_request_refund(self, data):
        """Requests the refund for the current shipment record
        and returns the response.
        """
        Shipment = Pool().get('stock.shipment.out')
        EndiciaConfiguration = Pool().get('endicia.configuration')

        # Getting the api credentials to be used in refund request generation
        # endicia credentials are in the format :
        # (account_id, requester_id, passphrase, is_test)
        endicia_credentials = EndiciaConfiguration(1).get_endicia_credentials()

        shipments = Shipment.browse(Transaction().context['active_ids'])

        # PICNumber is the argument name expected by endicia in API,
        # so its better to use the same name here for better understanding
        pic_numbers = []
        for shipment in shipments:
            if not (
                shipment.carrier and
                shipment.carrier.carrier_cost_method == 'endicia'
            ):
                self.raise_user_error('wrong_carrier')

            pic_numbers.append(shipment.tracking_number)

        test = endicia_credentials.is_test and 'Y' or 'N'

        refund_request = RefundRequestAPI(
            pic_numbers=pic_numbers,
            accountid=endicia_credentials.account_id,
            requesterid=endicia_credentials.requester_id,
            passphrase=endicia_credentials.passphrase,
            test=test,
        )
        try:
            response = refund_request.send_request()
        except RequestError, error:
            self.raise_user_error('error_label', error_args=(error,))

        result = objectify_response(response)
        if str(result.RefundList.PICNumber.IsApproved) == 'YES':
            refund_approved = True
            # If refund is approved, then set the state of record
            # as cancel/refund
            shipment.__class__.write(
                [shipment], {'endicia_refunded': True}
            )
        else:
            refund_approved = False
        default = {
            'refund_status': unicode(result.RefundList.PICNumber.ErrorMsg),
            'refund_approved': refund_approved
        }
        return default


class BuyPostageWizardView(ModelView):
    """Buy Postage Wizard View
    """
    __name__ = 'buy.postage.wizard.view'

    company = fields.Many2One('company.company', 'Company', required=True)
    amount = fields.Numeric('Amount in USD', required=True)
    response = fields.Text('Response', readonly=True)

    @staticmethod
    def default_company():
        return Transaction().context.get('company')


class BuyPostageWizard(Wizard):
    """Buy Postage Wizard
    """
    __name__ = 'buy.postage.wizard'

    start = StateView(
        'buy.postage.wizard.view',
        'shipping_endicia.endicia_buy_postage_wizard_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Buy Postage', 'buy_postage', 'tryton-ok'),
        ]
    )
    buy_postage = StateView(
        'buy.postage.wizard.view',
        'shipping_endicia.endicia_buy_postage_wizard_view_form', [
            Button('OK', 'end', 'tryton-ok'),
        ]
    )

    def default_buy_postage(self, data):
        """
        Generate the SCAN Form for the current shipment record
        """
        EndiciaConfiguration = Pool().get('endicia.configuration')

        default = {}
        endicia_credentials = EndiciaConfiguration(1).get_endicia_credentials()

        buy_postage_api = BuyingPostageAPI(
            request_id=Transaction().user,
            recredit_amount=self.start.amount,
            requesterid=endicia_credentials.requester_id,
            accountid=endicia_credentials.account_id,
            passphrase=endicia_credentials.passphrase,
            test=endicia_credentials.is_test,
        )
        try:
            response = buy_postage_api.send_request()
        except RequestError, error:
            self.raise_user_error('error_label', error_args=(error,))

        result = objectify_response(response)
        default['company'] = self.start.company
        default['amount'] = self.start.amount
        default['response'] = str(result.ErrorMessage) \
            if hasattr(result, 'ErrorMessage') else 'Success'
        return default


class ShippingEndicia(ModelView):
    'Endicia Configuration'
    __name__ = 'shipping.label.endicia'

    endicia_mailclass = fields.Many2One(
        'endicia.mailclass', 'MailClass', required=True
    )
    endicia_mailpiece_shape = fields.Selection(
        MAILPIECE_SHAPES, 'Endicia MailPiece Shape'
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
    endicia_refunded = fields.Boolean('Refunded ?', readonly=True)


class GenerateShippingLabel(Wizard):
    'Generate Labels'
    __name__ = 'shipping.label'

    endicia_config = StateView(
        'shipping.label.endicia',
        'shipping_endicia.shipping_endicia_configuration_view_form',
        [
            Button('Back', 'start', 'tryton-go-previous'),
            Button('Continue', 'generate', 'tryton-go-next'),
        ]
    )

    def default_endicia_config(self, data):
        Config = Pool().get('sale.configuration')
        config = Config(1)
        shipment = self.start.shipment

        return {
            'endicia_mailclass': (
                shipment.endicia_mailclass and shipment.endicia_mailclass.id
            ) or (
                config.endicia_mailclass and config.endicia_mailclass.id
            ) or None,
            'endicia_mailpiece_shape': (
                shipment.endicia_mailpiece_shape or
                config.endicia_mailpiece_shape
            ),
            'endicia_label_subtype': (
                shipment.endicia_label_subtype or config.endicia_label_subtype
            ),
            'endicia_integrated_form_type': (
                shipment.endicia_integrated_form_type or
                config.endicia_integrated_form_type
            ),
            'endicia_include_postage': (
                shipment.endicia_include_postage or
                config.endicia_include_postage
            ),
            'endicia_package_type': (
                shipment.endicia_package_type or config.endicia_package_type
            )
        }

    def transition_next(self):
        state = super(GenerateShippingLabel, self).transition_next()

        if self.start.carrier.carrier_cost_method == 'endicia':
            return 'endicia_config'
        return state

    def update_shipment(self):
        shipment = self.start.shipment

        if self.start.carrier.carrier_cost_method == 'endicia':
            shipment.endicia_mailclass = self.endicia_config.endicia_mailclass
            shipment.endicia_mailpiece_shape = \
                self.endicia_config.endicia_mailpiece_shape
            shipment.endicia_label_subtype = \
                self.endicia_config.endicia_label_subtype
            shipment.endicia_integrated_form_type = \
                self.endicia_config.endicia_integrated_form_type
            shipment.endicia_package_type = \
                self.endicia_config.endicia_package_type
            shipment.endicia_include_postage = \
                self.endicia_config.endicia_include_postage

        return super(GenerateShippingLabel, self).update_shipment()
