# -*- coding: utf-8 -*-
"""
    shipment_bag

"""
import base64

from trytond.model import Workflow, ModelView
from trytond.pool import Pool, PoolMeta

from endicia import SCANFormAPI
from endicia.tools import objectify_response

__metaclass__ = PoolMeta
__all__ = ['ShippingManifest']


class ShippingManifest:
    __name__ = 'shipping.manifest'

    @classmethod
    def __setup__(cls):
        super(ShippingManifest, cls).__setup__()

        cls._error_messages.update({
            'error_scanform': 'Error in generating scanform "%s"',
        })

    @classmethod
    @ModelView.button
    @Workflow.transition('closed')
    def close(cls, manifests):
        """
        Generate the SCAN Form for manifest
        """
        Attachment = Pool().get('ir.attachment')

        super(ShippingManifest, cls).close(manifests)
        for manifest in manifests:
            if not manifest.shipments:
                manifest.raise_user_error('manifest_empty')

            if manifest.carrier_cost_method != 'endicia':
                continue

            pic_numbers = [
                shipment.tracking_number.tracking_number
                for shipment in manifest.shipments if shipment.tracking_number
            ]
            test = manifest.carrier.endicia_is_test and 'Y' or 'N'
            scan_request = SCANFormAPI(
                pic_numbers=pic_numbers,
                accountid=manifest.carrier.endicia_account_id,
                requesterid=manifest.carrier.endicia_requester_id,
                passphrase=manifest.carrier.endicia_passphrase,
                test=test,
            )
            response = scan_request.send_request()
            result = objectify_response(response)
            if not hasattr(result, 'SCANForm'):
                manifest.raise_user_error(
                    'error_scanform', error_args=(result.ErrorMsg,)
                )
            else:
                Attachment.create([{
                    'name': 'SCAN%s.png' % str(result.SubmissionID),
                    'data': buffer(base64.decodestring(result.SCANForm.pyval)),
                    'resource': '%s,%s' % (manifest.__name__, manifest.id)
                }])
