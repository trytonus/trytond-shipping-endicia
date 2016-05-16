# -*- encoding: utf-8 -*-
from decimal import Decimal, ROUND_UP
import base64
import math
import logging

from endicia import ShippingLabelAPI, LabelRequest, RefundRequestAPI, \
    BuyingPostageAPI, Element
from endicia.tools import objectify_response, get_images
from endicia.exceptions import RequestError

from trytond.model import Workflow, ModelView, fields
from trytond.wizard import Wizard, StateView, Button
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval

ENDICIA_STATES = {
    'readonly': Eval('state') == 'done',
    'invisible': Eval('carrier_cost_method') != 'endicia'
}
ENDICIA_DEPENDS = ['state', 'carrier_cost_method']

ENDICIA_PACKAGE_TYPES = [
    ('Documents', 'Documents'),
    ('Gift', 'Gift'),
    ('Merchandise', 'Merchandise'),
    ('Other', 'Other'),
    ('Sample', 'Sample')
]

__metaclass__ = PoolMeta
__all__ = [
    'ShipmentOut', 'ShippingEndicia', 'GenerateShippingLabel',
    'EndiciaRefundRequestWizardView', 'EndiciaRefundRequestWizard',
    'BuyPostageWizardView', 'BuyPostageWizard',
]

logger = logging.getLogger(__name__)


def quantize_2_decimal(value):
    return Decimal("%f" % value).quantize(Decimal('.01'), rounding=ROUND_UP)


class ShipmentOut:
    "Shipment Out"
    __name__ = 'stock.shipment.out'

    endicia_label_subtype = fields.Selection([
        (None, 'None'),
        ('Integrated', 'Integrated')
    ], 'Label Subtype', states=ENDICIA_STATES, depends=ENDICIA_DEPENDS)
    endicia_integrated_form_type = fields.Selection([
        (None, ''),
        ('Form2976', 'Form2976(Same as CN22)'),
        ('Form2976A', 'Form2976(Same as CP72)'),
    ], 'Integrated Form Type', states=ENDICIA_STATES, depends=ENDICIA_DEPENDS)
    endicia_include_postage = fields.Boolean(
        'Include Postage ?', states=ENDICIA_STATES, depends=ENDICIA_DEPENDS
    )
    endicia_package_type = fields.Selection(
        ENDICIA_PACKAGE_TYPES, 'Package Content Type',
        states=ENDICIA_STATES, depends=ENDICIA_DEPENDS
    )
    endicia_refunded = fields.Boolean(
        'Refunded ?', readonly=True, states={
            'invisible': Eval('carrier_cost_method') != 'endicia'
        }, depends=ENDICIA_DEPENDS
    )

    @staticmethod
    def default_endicia_package_type():
        return "Other"

    @classmethod
    def __register__(cls, module):
        super(ShipmentOut, cls).__register__(module)

        # endicia_label_subtype selection "None" has been changed to NULL
        cursor = Transaction().cursor
        cursor.execute("""
            UPDATE stock_shipment_out
            SET endicia_label_subtype = NULL
            WHERE endicia_label_subtype = 'None'
        """)

    @classmethod
    def __setup__(cls):
        super(ShipmentOut, cls).__setup__()
        cls._error_messages.update({
            'error_label': 'Error in generating label "%s"',
            'tracking_number_already_present':
                'Tracking Number is already present for this shipment.',
            'invalid_state': 'Labels can only be generated when the '
                'shipment is in Packed or Done states only',
            'wrong_carrier': 'Carrier for selected shipment is not Endicia',
        })

    @classmethod
    @ModelView.button
    @Workflow.transition('done')
    def done(cls, shipments):
        """
        Add endicia shipments to a open manifest
        """
        ShippingManifest = Pool().get('shipping.manifest')

        super(ShipmentOut, cls).done(shipments)

        for shipment in shipments:
            if shipment.carrier and \
                    shipment.carrier.carrier_cost_method == 'endicia':
                with Transaction().set_user(0):
                    manifest = ShippingManifest.get_manifest(
                        shipment.carrier, shipment.warehouse
                    )
                shipment.manifest = manifest
                shipment.save()

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

    def generate_shipping_labels(self, **kwargs):
        """
        Make labels for the given shipment

        :return: Tracking number as string
        """
        Attachment = Pool().get('ir.attachment')
        Tracking = Pool().get('shipment.tracking')
        Uom = Pool().get('product.uom')

        if self.carrier_cost_method != 'endicia':
            return super(ShipmentOut, self).generate_shipping_labels(**kwargs)

        label_request = LabelRequest(
            Test=self.carrier.endicia_is_test and 'YES' or 'NO',
            LabelType=(
                'International' in self.carrier_service.code
            ) and 'International' or 'Default',
            # TODO: Probably the following have to be configurable
            ImageFormat="PNG",
            LabelSize="6x4",
            ImageResolution="203",
            ImageRotation="Rotate270",
        )

        try:
            package, = self.packages
        except ValueError:
            self.raise_user_error(
                "There should be exactly one package to generate USPS label"
                "\n Multi Piece shipment is not supported yet"
            )

        oz, = Uom.search([('symbol', '=', 'oz')])
        # Endicia only support 1 decimal place in weight
        weight_oz = "%.1f" % Uom.compute_qty(
            package.weight_uom, package.weight, oz
        )
        shipping_label_request = ShippingLabelAPI(
            label_request=label_request,
            weight_oz=weight_oz,
            partner_customer_id=self.delivery_address.id,
            partner_transaction_id=self.id,
            mail_class=self.carrier_service.code,
            accountid=self.carrier.endicia_account_id,
            requesterid=self.carrier.endicia_requester_id,
            passphrase=self.carrier.endicia_passphrase,
            test=self.carrier.endicia_is_test,
        )

        shipping_label_request.mailpieceshape = package.box_type and \
            package.box_type.code

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

        if self.delivery_address.country.code != 'US':
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
            self.raise_user_error('error_label', error_args=(error.message,))
        else:
            result = objectify_response(response)

            # Logging.
            logger.debug('--------SHIPPING LABEL RESPONSE--------')
            logger.debug(str(response))
            logger.debug('--------END RESPONSE--------')

            tracking_number = unicode(result.TrackingNumber.pyval)
            stock_package = self.packages[0]
            tracking, = Tracking.create([{
                'carrier': self.carrier,
                'tracking_number': tracking_number,
                'origin': '%s,%d' % (
                    stock_package.__name__, stock_package.id
                ),
            }])

            self.tracking_number = tracking.id
            self.save()

            self.__class__.write([self], {
                'cost': Decimal(str(result.FinalPostage.pyval)),
            })

            # Save images as attachments
            images = get_images(result)
            for (id, label) in images:
                label = stock_package._process_raw_label(label)
                Attachment.create([{
                    'name': "%s_%s_USPS-Endicia.png" % (tracking_number, id),
                    'data': buffer(base64.decodestring(label)),
                    'resource': '%s,%s' % (self.__name__, self.id)
                }])


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
            Button('Request Refund', 'request_refund', 'tryton-ok',
                   default=True),
        ]
    )
    request_refund = StateView(
        'endicia.refund.wizard.view',
        'shipping_endicia.endicia_refund_wizard_view_form', [
            Button('OK', 'end', 'tryton-ok', default=True),
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

            if shipment.tracking_number:
                pic_numbers.append(shipment.tracking_number.tracking_number)

        test = shipment.carrier.endicia_is_test and 'Y' or 'N'

        refund_request = RefundRequestAPI(
            pic_numbers=pic_numbers,
            accountid=shipment.carrier.endicia_account_id,
            requesterid=shipment.carrier.endicia_requester_id,
            passphrase=shipment.carrier.endicia_passphrase,
            test=test,
        )
        try:
            response = refund_request.send_request()
        except RequestError, error:
            self.raise_user_error('error_label', error_args=(error.message,))

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

    amount = fields.Numeric('Amount in USD', required=True)
    response = fields.Text('Response', readonly=True)
    carrier = fields.Many2One(
        "carrier", "Carrier", required=True,
        domain=[('carrier_cost_method', '=', 'endicia')]
    )


class BuyPostageWizard(Wizard):
    """Buy Postage Wizard
    """
    __name__ = 'buy.postage.wizard'

    start = StateView(
        'buy.postage.wizard.view',
        'shipping_endicia.endicia_buy_postage_wizard_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Buy Postage', 'buy_postage', 'tryton-ok',
                   default=True),
        ]
    )
    buy_postage = StateView(
        'buy.postage.wizard.view',
        'shipping_endicia.endicia_buy_postage_wizard_view_form', [
            Button('OK', 'end', 'tryton-ok', default=True),
        ]
    )

    def default_buy_postage(self, data):
        """
        Generate the SCAN Form for the current shipment record
        """
        default = {}

        buy_postage_api = BuyingPostageAPI(
            request_id=Transaction().user,
            recredit_amount=self.start.amount,
            requesterid=self.start.carrier.endicia_requester_id,
            accountid=self.start.carrier.endicia_account_id,
            passphrase=self.start.carrier.endicia_passphrase,
            test=self.start.carrier.endicia_is_test,
        )
        try:
            response = buy_postage_api.send_request()
        except RequestError, error:
            self.raise_user_error('error_label', error_args=(error.message,))

        result = objectify_response(response)
        default['amount'] = self.start.amount
        default['carrier'] = self.start.carrier
        default['response'] = str(result.ErrorMessage) \
            if hasattr(result, 'ErrorMessage') else 'Success'
        return default


class ShippingEndicia(ModelView):
    'Endicia Configuration'
    __name__ = 'shipping.label.endicia'

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
            Button(
                'Continue', 'generate_labels', 'tryton-go-next', default=True
            ),
        ]
    )

    def transition_next(self):
        state = super(GenerateShippingLabel, self).transition_next()

        if self.start.carrier.carrier_cost_method == 'endicia':
            return 'endicia_config'
        return state

    def default_endicia_config(self, data):
        return {
            'endicia_label_subtype': self.shipment.endicia_label_subtype,
            'endicia_integrated_form_type':
                self.shipment.endicia_integrated_form_type,
            'endicia_include_postage': self.shipment.endicia_include_postage,
            'endicia_package_type': self.shipment.endicia_package_type,
        }

    def transition_shipping_labels(self):
        if self.start.carrier.carrier_cost_method == "endicia":
            shipment = self.shipment
            shipment.endicia_label_subtype = \
                self.endicia_config.endicia_label_subtype
            shipment.endicia_integrated_form_type = \
                self.endicia_config.endicia_integrated_form_type
            shipment.endicia_package_type = \
                self.endicia_config.endicia_package_type
            shipment.endicia_include_postage = \
                self.endicia_config.endicia_include_postage
            shipment.save()

        return super(GenerateShippingLabel, self).transition_shipping_labels()
