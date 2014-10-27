# -*- coding: utf-8 -*-
"""
    configuration.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.model import fields, ModelSingleton, ModelSQL, ModelView

__all__ = ['EndiciaConfiguration']


class EndiciaConfiguration(ModelSingleton, ModelSQL, ModelView):
    """
    Configuration settings for Endicia.
    """
    __name__ = 'endicia.configuration'

    account_id = fields.Integer('Account Id')
    requester_id = fields.Char('Requester Id')
    passphrase = fields.Char('Passphrase')
    is_test = fields.Boolean('Is Test')

    @classmethod
    def __setup__(cls):
        super(EndiciaConfiguration, cls).__setup__()
        cls._error_messages.update({
            'endicia_credentials_required':
                'Endicia settings on endicia configuration are incomplete.',
        })

    def get_endicia_credentials(self):
        """Validate if endicia credentials are complete.
        """
        if not all([
            self.account_id,
            self.requester_id,
            self.passphrase
        ]):
            self.raise_user_error('endicia_credentials_required')

        return self
