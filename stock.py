# -*- encoding: utf-8 -*-
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

'''
Inherit stock for endicia API
'''
from decimal import Decimal
import base64
import math

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
    'ShipmentOut', 'GenerateEndiciaLabelMessage', 'GenerateEndiciaLabel',
    'EndiciaRefundRequestWizardView', 'EndiciaRefundRequestWizard',
    'BuyPostageWizardView', 'BuyPostageWizard',
]

STATES = {
    'readonly': Eval('state') == 'done',
}


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
            'warehouse_address_required': 'Warehouse address is required.',
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

        user = User(Transaction().user)
        customsitems = []
        value = 0

        for move in self.outgoing_moves:
            if move.quantity <= 0:
                continue
            new_item = [
                Element('Description', move.product.name[0:50]),
                Element('Quantity', int(math.ceil(move.quantity))),
                Element('Weight', int(move.get_weight(self.weight_uom))),
                Element('Value', float(move.product.list_price)),
            ]
            customsitems.append(Element('CustomsItem', new_item))
            value += float(move.product.list_price) * move.quantity

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
            'Value': total_value,
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

        shipping_label_request = ShippingLabelAPI(
            label_request=label_request,
            weight_oz=self.package_weight,
            partner_customer_id=self.delivery_address.id,
            partner_transaction_id=self.id,
            mail_class=mailclass,
            MailpieceShape=self.endicia_mailpiece_shape,
            accountid=endicia_credentials.account_id,
            requesterid=endicia_credentials.requester_id,
            passphrase=endicia_credentials.passphrase,
            test=endicia_credentials.is_test,
        )

        # From address is the warehouse location. So it must be filled.
        if not self.warehouse.address:
            self.raise_user_error('warehouse_address_required')

        shipping_label_request.add_data(
            self.warehouse.address.address_to_endicia_from_address().data
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

        try:
            response = shipping_label_request.send_request()
        except RequestError, error:
            self.raise_user_error('error_label', error_args=(error,))
        else:
            result = objectify_response(response)

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

            return tracking_number

    def _get_ship_from_address(self):
        """
        Usually the warehouse from which you ship
        """
        return self.warehouse.address

    def get_endicia_shipping_cost(self):
        """Returns the calculated shipping cost as sent by endicia

        :returns: The shipping cost in USD
        """
        EndiciaConfiguration = Pool().get('endicia.configuration')
        endicia_credentials = EndiciaConfiguration(1).get_endicia_credentials()

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

        calculate_postage_request = CalculatingPostageAPI(
            mailclass=self.endicia_mailclass.value,
            MailpieceShape=self.endicia_mailpiece_shape,
            weightoz=self.package_weight,
            from_postal_code=from_address.zip and from_address.zip[:5],
            to_postal_code=to_zip,
            to_country_code=to_address.country and to_address.country.code,
            accountid=endicia_credentials.account_id,
            requesterid=endicia_credentials.requester_id,
            passphrase=endicia_credentials.passphrase,
            test=endicia_credentials.is_test,
        )

        try:
            response = calculate_postage_request.send_request()
        except RequestError, error:
            self.raise_user_error('error_label', error_args=(error,))

        return Decimal(
            objectify_response(response).PostagePrice.get('TotalAmount')
        )

    def get_is_endicia_shipping(self, name):
        """
        Check if shipping is from USPS
        """
        return self.carrier and self.carrier.carrier_cost_method == 'endicia'


class GenerateEndiciaLabelMessage(ModelView):
    'Generate Endicia Labels Message'
    __name__ = 'generate.endicia.label.message'

    tracking_number = fields.Char("Tracking number", readonly=True)


class GenerateEndiciaLabel(Wizard):
    'Generate Endicia Labels'
    __name__ = 'generate.endicia.label'

    start = StateView(
        'generate.endicia.label.message',
        'endicia_integration.generate_endicia_label_message_view_form',
        [
            Button('Ok', 'end', 'tryton-ok'),
        ]
    )

    def default_start(self, data):
        Shipment = Pool().get('stock.shipment.out')

        try:
            shipment, = Shipment.browse(Transaction().context['active_ids'])
        except ValueError:
            self.raise_user_error(
                'This wizard can be called for only one shipment at a time'
            )

        tracking_number = shipment.make_endicia_labels()

        return {'tracking_number': str(tracking_number)}


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
        'endicia_integration.endicia_refund_wizard_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Request Refund', 'request_refund', 'tryton-ok'),
        ]
    )
    request_refund = StateView(
        'endicia.refund.wizard.view',
        'endicia_integration.endicia_refund_wizard_view_form', [
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
        'endicia_integration.endicia_buy_postage_wizard_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Buy Postage', 'buy_postage', 'tryton-ok'),
        ]
    )
    buy_postage = StateView(
        'buy.postage.wizard.view',
        'endicia_integration.endicia_buy_postage_wizard_view_form', [
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
