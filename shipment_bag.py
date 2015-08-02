# -*- coding: utf-8 -*-
"""
    shipment_bag

"""
import base64
from datetime import datetime

from trytond.model import Workflow, ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.pyson import Eval

from endicia import SCANFormAPI

from endicia.tools import objectify_response

__all__ = ['EndiciaShipmentBag']


class EndiciaShipmentBag(Workflow, ModelSQL, ModelView):
    "Shipment Bag"
    __name__ = 'endicia.shipment.bag'

    state = fields.Selection([
        ('open', 'Open'),
        ('closed', 'Closed'),
    ], 'State', readonly=True, required=True)

    shipments = fields.One2Many(
        'stock.shipment.out', 'endicia_shipment_bag', 'Shipments',
        states={
            'readonly': Eval('state') != 'open',
        },
        domain=[
            ('carrier.carrier_cost_method', '=', 'endicia'),
            ('state', '=', 'done'),
        ],
        add_remove=[
            ('carrier.carrier_cost_method', '=', 'endicia'),
            ('endicia_shipment_bag', '=', None),
            ('state', '=', 'done'),
        ], depends=['state']
    )
    submission_id = fields.Char('Submission Id', readonly=True, select=True)

    open_date = fields.Date('Open Date', readonly=True, required=True)
    close_date = fields.Date('Close Date', readonly=True)

    @classmethod
    def __setup__(cls):
        super(EndiciaShipmentBag, cls).__setup__()

        cls._transitions |= set((
            ('open', 'closed'),
        ))

        cls._error_messages.update({
            'bag_empty': 'Bag should have atleast one shipment.',
            'error_scanform': 'Error in generating scanform "%s"',
        })

        cls._buttons.update({
            'close': {
                'invisible': Eval('state').in_(['closed']),
            },
        })

    def get_rec_name(self, name):
        return self.submission_id or str(self.id)

    @staticmethod
    def default_state():
        return 'open'

    @staticmethod
    def default_open_date():
        return datetime.utcnow().date()

    @classmethod
    def get_bag(cls):
        """
        Returns currently opened bag and make sure only one bag is opened at a
        time.
        This method can be inherited to change the logic of bag opening.
        """
        bags = cls.search([('state', '=', 'open')])

        assert len(bags) < 2  # Assert at max we have 1 open bags.
        if bags:
            # Return if a bag is opened.
            return bags[0]
        return cls.create([{}])[0]

    @classmethod
    @ModelView.button
    @Workflow.transition('closed')
    def close(cls, bags):
        for bag in bags:
            bag.make_scanform()
        cls.write(bags, {
            'close_date': datetime.utcnow().date()
        })

    def make_scanform(self):
        """
        Generate the SCAN Form for bag
        """
        EndiciaConfiguration = Pool().get('endicia.configuration')
        Attachment = Pool().get('ir.attachment')

        # Getting the api credentials to be used in refund request generation
        # endget_weight_for_endiciaicia credentials are in the format :
        # (account_id, requester_id, passphrase, is_test)
        endicia_credentials = EndiciaConfiguration(1).get_endicia_credentials()

        if not self.shipments:
            self.raise_user_error('bag_empty')

        pic_numbers = [shipment.tracking_number for shipment in self.shipments]
        test = endicia_credentials.is_test and 'Y' or 'N'
        scan_request = SCANFormAPI(
            pic_numbers=pic_numbers,
            accountid=endicia_credentials.account_id,
            requesterid=endicia_credentials.requester_id,
            passphrase=endicia_credentials.passphrase,
            test=test,
        )
        response = scan_request.send_request()
        result = objectify_response(response)
        if not hasattr(result, 'SCANForm'):
            self.raise_user_error(
                'error_scanform', error_args=(result.ErrorMsg,)
            )
        else:
            self.submission_id = str(result.SubmissionID)
            self.save()
            Attachment.create([{
                'name': 'SCAN%s.png' % str(result.SubmissionID),
                'data': buffer(base64.decodestring(result.SCANForm.pyval)),
                'resource': '%s,%s' % (self.__name__, self.id)
            }])
