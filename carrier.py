from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.pyson import Eval

__all__ = ['Carrier', 'CarrierService', 'BoxType']
__metaclass__ = PoolMeta

ENDICIA_STATES = {
    'required': Eval('carrier_cost_method') == 'endicia',
    'invisible': Eval('carrier_cost_method') != 'endicia',
}


class Carrier:
    "Carrier"
    __name__ = 'carrier'

    endicia_account_id = fields.Char('Account Id', states=ENDICIA_STATES)
    endicia_requester_id = fields.Char('Requester Id', states=ENDICIA_STATES)
    endicia_passphrase = fields.Char('Passphrase', states=ENDICIA_STATES)
    endicia_is_test = fields.Boolean('Is Test', states={
        'invisible': Eval('carrier_cost_method') != 'endicia',
    })

    def _get_hide_currency(self):
        """
        Downstream implementation for carrier._get_hide_currency
        """
        if self.carrier_cost_method == 'endicia':
            return False
        return super(Carrier, self)._get_hide_currency()

    def get_currency(self, name):
        """
        Downstream implementation for carrier.get_currency
        """
        if self.carrier_cost_method != 'endicia':
            return super(Carrier, self).get_currency(name)

        ModelData = Pool().get('ir.model.data')

        return ModelData.get_id("currency", "usd")

    @classmethod
    def __setup__(cls):
        super(Carrier, cls).__setup__()
        selection = ('endicia', 'USPS (Direct)')
        if selection not in cls.carrier_cost_method.selection:
            cls.carrier_cost_method.selection.append(selection)


class CarrierService:
    __name__ = 'carrier.service'

    method_type = fields.Selection([
        (None, ''),
        ('domestic', 'Domestic'),
        ('international', 'International'),
    ], 'Endicia Method Type', select=True, readonly=True)

    @classmethod
    def __setup__(cls):
        super(CarrierService, cls).__setup__()

        for selection in [('endicia', 'USPS (Direct)')]:
            if selection not in cls.carrier_cost_method.selection:
                cls.carrier_cost_method.selection.append(selection)


class BoxType:
    __name__ = "carrier.box_type"

    @classmethod
    def __setup__(cls):
        super(BoxType, cls).__setup__()

        for selection in [('endicia', 'USPS (Direct)')]:
            if selection not in cls.carrier_cost_method.selection:
                cls.carrier_cost_method.selection.append(selection)
