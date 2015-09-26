# -*- coding: utf-8 -*-
"""
    configuration.py

"""
from trytond import backend
from trytond.model import fields, ModelSingleton, ModelSQL, ModelView
from trytond.transaction import Transaction

__all__ = ['EndiciaConfiguration']


class EndiciaConfiguration(ModelSingleton, ModelSQL, ModelView):
    """
    Configuration settings for Endicia.
    """
    __name__ = 'endicia.configuration'

    account_id = fields.Char('Account Id')
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

    @classmethod
    def __register__(cls, module_name):
        TableHandler = backend.get('TableHandler')
        cursor = Transaction().cursor

        # Migration from 3.4.0.6 : Migrate account_id field to string
        if backend.name() == 'postgresql':
            cursor.execute(
                'SELECT pg_typeof("account_id") '
                'FROM endicia_configuration '
                'LIMIT 1',
            )

            # Check if account_id is integer field
            is_integer = cursor.fetchone()[0] == 'integer'

            if is_integer:
                # Migrate integer field to string
                table = TableHandler(cursor, cls, module_name)
                table.alter_type('account_id', 'varchar')

        super(EndiciaConfiguration, cls).__register__(module_name)

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
