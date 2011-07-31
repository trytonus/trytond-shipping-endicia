# -*- encoding: utf-8 -*-
"""
Customizes company to have Endicia API Information
"""
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

# pylint: disable=E1101
# pylint: disable=F0401
from collections import namedtuple
from trytond.model import ModelView, ModelSQL, fields
from trytond.transaction import Transaction


class Company(ModelSQL, ModelView):
    """
    This will add four fields for account_id, requester_id, pass phrase
    and is_test.
    """
    _name = 'company.company'

    def __init__(self):
        super(Company, self).__init__()
        self._error_messages.update({
            'endicia_credentials_required': 'Please check the account '
                'settings for Endicia account.\nSome details may be missing.',
        })

    account_id = fields.Integer('Account Id')
    requester_id = fields.Char('Requester Id')
    passphrase = fields.Char('Passphrase')
    usps_test = fields.Boolean('Is Test')

    def get_endicia_credentials(self):
        """
        Returns the credentials in tuple

        :return: (account_id, requester_id, passphrase, is_test)
        """
        user_obj = self.pool.get('res.user')
        user_record = user_obj.browse(Transaction().user)
        company = self.browse(user_record.company.id)

        if not company.account_id or not company.requester_id or \
            not company.passphrase:
            self.raise_user_error('endicia_credentials_required')
        EndiciaSettings = namedtuple('EndiciaSettings', [
            'account_id', 'requester_id', 'passphrase', 'usps_test'
            ])
        return EndiciaSettings(
            company.account_id,
            company.requester_id,
            company.passphrase,
            company.usps_test,
            )

Company()
