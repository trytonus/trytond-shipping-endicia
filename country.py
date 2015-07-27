# -*- coding: utf-8 -*-
"""
    country.py

"""
from trytond.pool import PoolMeta
from trytond.model import fields

__metaclass__ = PoolMeta
__all__ = ['Country']


class Country:
    'Country'
    __name__ = 'country.country'

    endicia_country_name = fields.Char('Endicia Country Name')
    endicia_name = fields.Function(
        fields.Char('Endicia Name'), 'get_endicia_name'
    )

    def get_endicia_name(self, name):
        """
        Checks if there is some name defined in endicia_country_name
        and returns it, else returns the name of country
        """
        return self.endicia_country_name or self.name
