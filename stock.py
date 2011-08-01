# -*- encoding: utf-8 -*-
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

# pylint: disable=E1101
# pylint: disable=F0401
'''
Inherit stock for endicia API
'''
from endicia import ShippingLabelAPI, LabelRequest, RefundRequestAPI, \
    SCANFormAPI, CalculatingPostageAPI, Element
from endicia.tools import objectify_response, get_images
from endicia.exceptions import RequestError

from trytond.model import ModelWorkflow, ModelView, ModelSQL, fields
from trytond.transaction import Transaction
from trytond.wizard import Wizard


class ShipmentOut(ModelWorkflow, ModelSQL, ModelView):
    """Extend customer shipment for endicia methods
    """

    _name = 'stock.shipment.out'

    def __init__(self):
        super(ShipmentOut, self).__init__()
        self._error_messages.update({
            'weight_required': 'Please enter weights for the products',
            'weight_uom_required': 'Please enter weight uom for the products',
        })

    def get_move_line_weights(self, shipment_id):
        """
        Return weight for individual lines in oz as zo is the preferred
        unit for endicia

        :param shipment_id: ID of the shipment
        """
        product_uom_obj = self.pool.get('product.uom')
        weight_matrix = {}
        shipment = self.browse(shipment_id)

        for move in shipment.outgoing_moves:
            if not move.product.weight:
                self.raise_user_error('weight_required')
            if not move.product.weight_uom:
                self.raise_user_error('weight_uom_required')

            # Find the quantity in the default uom of the product as the weight
            # is for per unit in that uom
            if move.uom.id != move.product.default_uom.id :
                quantity = product_uom_obj.compute_qty(
                    move.uom,
                    move.quantity,
                    move.product.default_uom
                    )
            else:
                quantity = move.quantity

            weight = float(move.product.weight) * quantity

            if move.product.weight_uom.symbol != 'oz':
                # If the weight is not in lbs then convert it to lbs
                uom_oz_id, = product_uom_obj.search([('symbol', '=', 'oz')])
                uom_oz = product_uom_obj.browse(uom_oz_id)
                weight = product_uom_obj.compute_qty(
                    move.product.weight_uom,
                    weight,
                    uom_oz
                )

            weight_matrix[move.id] = int(weight)

        return weight_matrix

ShipmentOut()


class StockMakeShipmentWizardView(ModelView):
    """Shipment Make Wizard View
    """
    _name = 'shipment.make.wizard.view'

    label_sub_type = fields.Selection([
        ('None', 'None'),
        ('Integrated', 'Integrated')
        ], 'Label Sub Type')
    integrated_form_type = fields.Selection([
        ('Form2976', 'Form2976(Same as CN22)'),
        ('Form2976A', 'Form2976(Same as CP72)'),
        ], 'Form Type')
    include_postage = fields.Boolean('Include Postage ?')

StockMakeShipmentWizardView()


class Carrier(ModelSQL, ModelView):
    'Carrier'
    _name = 'carrier'

    def __init__(self):
        super(Carrier, self).__init__()
        self.carrier_cost_method.selection.append(('endicia-usps', 'USPS'))
        self._error_messages.update({
            'location_required': 'Warehouse address is required.',
            'custom_details_required':
                'The Selected product has no customs details'
                '\nAdd the details under Custom Details '
                'tab on product page of "%s"',
            'error_label': 'Error in generating label "%s"',
        })

    def get_sale_price(self, carrier):
        """Estimates the shipment rate for the provided shipment
        """
        company_obj = self.pool.get('company.company')
        shipment_obj = self.pool.get('stock.shipment.out')
        if carrier.carrier_cost_method != 'endicia-usps':
            return super(CarrierUSPS, self).get_sale_price(carrier)
        # Getting the api credentials to be used in shipping label generation
        # endicia credentials are in the format : 
        # EndiciaSettings(account_id, requester_id, passphrase, is_test)
        endicia_credentials = company_obj.get_endicia_credentials()
        shipment_id = Transaction().context['id']

        if shipment_id:
            shipment = shipment_obj.browse(shipment_id)

            #From location is the warehouse location. So it must be filled.
            location = shipment.warehouse.address
            if not location:
                self.raise_user_error('location_required')
            line_weights = shipment_obj.get_move_line_weights(shipment_id)
            calculate_postage_request = CalculatingPostageAPI(
                mailclass = carrier.carrier_product.code,
                weightoz = sum(line_weights.values()),
                from_postal_code = location.zip,
                to_postal_code = shipment.delivery_address.zip,
                to_country_code = shipment.delivery_address.country.code,
                accountid = endicia_credentials.account_id,
                requesterid = endicia_credentials.requester_id,
                passphrase = endicia_credentials.passphrase,
                test = endicia_credentials.usps_test,
                )
            response = calculate_postage_request.send_request()
            return objectify_response(response).PostagePrice.\
                get('TotalAmount'), False
        else:
            return 0, False

    def label_from_shipment_out(self, carrier, shipment_id, options):
        """This method will call the corresponding method to generate the 
        label from the expected class
        """
        if carrier.carrier_cost_method != 'endicia-usps':
            return False
        endicia_obj = self.pool.get('carrier.endicia-usps')
        return endicia_obj.label_from_shipment_out(carrier, 
            shipment_id, options) 


Carrier()


class CarrierEndiciaUSPS(ModelSQL):
    _name = 'carrier.endicia-usps'

    def __init__(self):
        super(CarrierEndiciaUSPS, self).__init__()
        self._error_messages.update({
            'location_required': 'Warehouse address is required.',
            'custom_details_required':
                'The Selected product has no customs details'
                '\nAdd the details under Custom Details '
                'tab on product page of "%s"',
            'error_label': 'Error in generating label "%s"',
        })

    def _add_items_from_moves(self, shipping_label_api, moves, line_weights):
        '''
        Adding customs items/info and form descriptions to the request
        '''
        user_obj = self.pool.get('res.user')
        customsitems = []
        value = 0
        description = ''
        for move in moves:
            customs_item_det = (
                move.product.name, float(move.product.list_price)
            )
            if not customs_item_det[0] or not customs_item_det[1]:
                self.raise_user_error('custom_details_required',
                    error_args=(move.product.name,))
            new_item = [
                Element('Description',customs_item_det[0]),
                Element('Quantity', int(move.quantity)),
                Element('Weight', int(line_weights[move.id])),
                Element('Value', customs_item_det[1]),
                ]
            customsitems.append(Element('CustomsItem', new_item))
            value = value + \
                    (float(move.product.list_price)*move.quantity)
            description = description + customs_item_det[0] + ', '
        shipping_label_api.add_data({
            'customsinfo':[
                Element('CustomsItems', customsitems),
                Element('ContentsType', 'Gift')]})
        shipping_label_api.add_data({
            'ContentsType': 'Gift',
            'Value': value,
            'Description': description,
            'CustomsCertify': 'TRUE',
            'CustomsSigner': user_obj.browse(Transaction().user).name,
            })
        return shipping_label_api

    def _make_label(self, carrier, shipment, options):
        """
        Create a label for given shipment and return
        the response as such

        :param carrier: Browse Record of shipment method
        :param shipment: Browse Record of outgoing shipment
        :param options: Dictionary of values
        """
        address_obj = self.pool.get('party.address')
        company_obj = self.pool.get('company.company')
        shipment_obj = self.pool.get('stock.shipment.out')
        line_weights = shipment_obj.get_move_line_weights(shipment.id)
        # Getting the api credentials to be used in shipping label generation
        # endicia credentials are in the format : 
        # EndiciaSettings(account_id, requester_id, passphrase, is_test)
        endicia_credentials = company_obj.get_endicia_credentials()

        mailclass = carrier.carrier_product.code or \
            'FirstClassMailInternational'
        label_request = LabelRequest(
            Test=endicia_credentials.usps_test and 'YES' or 'NO',
            LabelType= ('International' in mailclass) and 'International' \
                or 'Default')
        delivery_address = shipment.delivery_address
        shipping_label_api = ShippingLabelAPI(
            label_request=label_request,
            weight_oz=sum(line_weights.values()),
            partner_customer_id=delivery_address.id,
            partner_transaction_id=shipment.id,
            mail_class=mailclass,
            accountid = endicia_credentials.account_id,
            requesterid = endicia_credentials.requester_id,
            passphrase = endicia_credentials.passphrase,
            test = endicia_credentials.usps_test,
            )
        #From location is the warehouse location. So it must be filled.
        location = shipment.warehouse.address
        if not location:
            self.raise_user_error('location_required')
        from_address = address_obj.address_to_endicia_from_address(location.id)
        to_address = address_obj.address_to_endicia_to_address(
            delivery_address.id)
        shipping_label_api.add_data(from_address.data)
        shipping_label_api.add_data(to_address.data)

        shipping_label_api.add_data({
            'LabelSubtype': options['label_sub_type'],
            'IncludePostage': options['include_postage'] and 'TRUE' or 'FALSE',
            })
        if options['label_sub_type'] != 'None':
            shipping_label_api.add_data({
                'IntegratedFormType': options['integrated_form_type'],
                })
        #Comment this line if not required
        shipping_label_api = self._add_items_from_moves(shipping_label_api,
            shipment.outgoing_moves, line_weights)

        response = shipping_label_api.send_request()

        return objectify_response(response)

    def label_from_shipment_out(self, carrier, shipment_id, options):
        """Generated the label and creates a shipment record for given shipment
        """
        result = {}
        labels = []
        shipment_obj = self.pool.get('stock.shipment.out')
        attachment_obj = self.pool.get('ir.attachment')
        record_obj = self.pool.get('shipment.record')
        shipment = shipment_obj.browse(shipment_id)
        try:
            result = self._make_label(carrier, shipment, options)
        except RequestError, error:
            self.raise_user_error('error_label', error_args=(error,))
        # Do the extra bits here like saving the tracking no
        tracking_no = result.TrackingNumber.pyval
        postage_paid = result.FinalPostage.pyval

        # The label image is available in two elements:
        #  1. Base64LabelImage - This is abset if the label
        #       node is present
        #  2. Label - Contains one or mode elements of each part
        #
        # An attempt to save label is made at first if it exists,
        # else, the Base64LabelImage is saved
        shipment_record = record_obj.create({
            'reference': tracking_no,
            'carrier': carrier.id,
            'tracking_number': tracking_no,
            'shipment_cost': postage_paid,
            'state': 'done',
            'shipments': [('add', shipment.id)]
            })

        images = get_images(result)

        for (id, label) in images:
            attachment_obj.create({
               'name': str(tracking_no) + ' - ' + str(id) + ' - USPS',
               'data': label,
               'resource': 'shipment.record,%s' % shipment_record
               })
        return 'Success'

CarrierEndiciaUSPS()


class RefundRequestWizardView(ModelView):
    """Shipment Refund Wizard View
    """
    _name = 'shipment.refund.wizard.view'
    _description = __doc__

    refund_status = fields.Text('Refund Status', readonly=True,)
    refund_approved = fields.Boolean('Refund Approved ?', readonly=True,)

RefundRequestWizardView()


class RefundRequestWizard(Wizard):
    """A wizard to cancel the current shipment and refund the cost
    """
    _name = 'shipment.refund.wizard'
    _description = 'Shipment Refund Wizard'

    states = {
        'init': {
            'actions': [],
            'result': {
                'type': 'form',
                'object': 'shipment.refund.wizard.view',
                'state': [
                    ('end', 'Cancel', 'tryton-cancel'),
                    ('request_refund', 'Request Refund', 'tryton-ok', True),
                ],
            },
        },
        'request_refund': {
            'actions': ['_request_refund'],
            'result': {
                'type': 'form',
                'object': 'shipment.refund.wizard.view',
                'state': [
                    ('end', 'Ok', 'tryton-ok'),
                ],
            },
        },
    }

    def _request_refund(self, data):
        """Requests the refund for the current shipment record 
        and returns the response.
        """
        res = data['form']
        company_obj = self.pool.get('company.company')
        shipment_record_obj = self.pool.get('shipment.record')
        shipment_record = shipment_record_obj.browse(data['id'])
        # Getting the api credentials to be used in refund request generation
        # endicia credentials are in the format : 
        # (account_id, requester_id, passphrase, is_test)
        endicia_credentials = company_obj.get_endicia_credentials()
        pic_number = shipment_record.tracking_number

        test = endicia_credentials.usps_test and 'Y' or 'N'

        refund_request = RefundRequestAPI(
            pic_number=pic_number,
            accountid=endicia_credentials.account_id,
            requesterid=endicia_credentials.requester_id,
            passphrase=endicia_credentials.passphrase,
            test=test,
            )
        response = refund_request.send_request()
        result = objectify_response(response)
        if str(result.RefundList.PICNumber.IsApproved) == 'YES':
            refund_approved = True
        else:
            refund_approved = False
        res['refund_status'] = str(result.RefundList.PICNumber.ErrorMsg)
        res['refund_approved'] = refund_approved
        return res

RefundRequestWizard()


class SCANFormWizardView(ModelView):
    """Shipment SCAN Form Wizard View
    """
    _name = 'shipment.scanform.wizard.view'
    _description = __doc__

    response = fields.Text('Response', readonly=True,)

SCANFormWizardView()


class SCANFormWizard(Wizard):
    """A wizard to generate the SCAN Form for the current shipment record
    """
    _name = 'shipment.scanform.wizard'
    _description = 'Shipment SCAN Form Wizard'

    def __init__(self):
        super(SCANFormWizard, self).__init__()
        self._error_messages.update({
            'endicia_credentials_required': 'Please check the account '
                'settings for Endicia account.\nSome details may be missing.',
            'scan_form_error': '"%s"',
            })

    states = {
        'init': {
            'actions': [],
            'result': {
                'type': 'form',
                'object': 'shipment.scanform.wizard.view',
                'state': [
                    ('end', 'Cancel', 'tryton-cancel'),
                    ('make_scanform', 'Make SCAN Form', 'tryton-ok', True),
                ],
            },
        },
        'make_scanform': {
            'actions': ['_make_scanform'],
            'result': {
                'type': 'form',
                'object': 'shipment.scanform.wizard.view',
                'state': [
                    ('end', 'Ok', 'tryton-ok'),
                ],
            },
        },
    }

    def _make_scanform(self, data):
        """
        Generate the SCAN Form for the current shipment record
        """
        res = data['form']
        company_obj = self.pool.get('company.company')
        attachment_obj = self.pool.get('ir.attachment')
        shipment_record_obj = self.pool.get('shipment.record')
        shipment_record = shipment_record_obj.browse(data['id'])
        # Getting the api credentials to be used in refund request generation
        # endicia credentials are in the format : 
        # (account_id, requester_id, passphrase, is_test)
        endicia_credentials = company_obj.get_endicia_credentials()
        # tracking_no is same as PICNumber
        pic_number = shipment_record.tracking_number

        test = endicia_credentials.usps_test and 'Y' or 'N'

        scan_request = SCANFormAPI(
            pic_number=pic_number,
            accountid=endicia_credentials.account_id,
            requesterid=endicia_credentials.requester_id,
            passphrase=endicia_credentials.passphrase,
            test=test,
        )
        response = scan_request.send_request()
        result = objectify_response(response)
        if not hasattr(result, 'SCANForm'):
            res['response'] = result.ErrorMsg
        else:
            attachment_obj.create({
               'name': 'SCAN' + str(result.SubmissionID),
               'data': str(result.SCANForm),
               'resource': 'shipment.record,%s' % data['id']})
            res['response'] = 'SCAN' + str(result.SubmissionID)
        return res

SCANFormWizard()
