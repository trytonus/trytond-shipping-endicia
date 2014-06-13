# -*- encoding: utf-8 -*-
"""
Customizes company to have Endicia API Information
"""

from collections import namedtuple

from trytond.model import fields
from trytond.pool import PoolMeta

__all__ = ['Company']
__metaclass__ = PoolMeta


class Company:
    """
    Company
    """
    __name__ = 'company.company'

    endicia_account_id = fields.Integer('Account Id')
    endicia_requester_id = fields.Char('Requester Id')
    endicia_passphrase = fields.Char('Passphrase')
    endicia_test = fields.Boolean('Is Test')

    @classmethod
    def __setup__(cls):
        super(Company, cls).__setup__()
        cls._error_messages.update({
            'endicia_credentials_required':
                'Endicia settings on company are incomplete.',
        })

    def get_endicia_credentials(self):
        """
        Returns the credentials in tuple

        :return: (account_id, requester_id, passphrase, is_test)
        """
        if not all([
            self.endicia_account_id,
            self.endicia_requester_id,
            self.endicia_passphrase
        ]):
            self.raise_user_error('endicia_credentials_required')

        EndiciaSettings = namedtuple('EndiciaSettings', [
            'account_id', 'requester_id', 'passphrase', 'usps_test'
        ])
        return EndiciaSettings(
            self.endicia_account_id,
            self.endicia_requester_id,
            self.endicia_passphrase,
            self.endicia_test,
        )
