# -*- encoding: utf-8 -*-
"""
Customizes party address to have address in correct format for Endicia API .
"""
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

import string

from endicia import FromAddress, ToAddress
from trytond.pool import PoolMeta

__all__ = ['Address']
__metaclass__ = PoolMeta


class Address:
    '''
    Address
    '''
    __name__ = "party.address"

    def address_to_endicia_from_address(self):
        '''
        Converts party address to Endicia From Address.

        :param return: Returns instance of FromAddress
        '''
        phone = self.party.phone
        if phone:
            # Remove the special characters in the phone if any
            phone = "".join([char for char in phone if char in string.digits])
        return FromAddress(
            FromName=self.name or self.party.name,
            # FromCompany = user_rec.company.name or None,
            ReturnAddress1=self.street,
            ReturnAddress2=self.streetbis,
            ReturnAddress3=None,
            ReturnAddress4=None,
            FromCity=self.city,
            FromState=self.subdivision and self.subdivision.code[3:],
            FromPostalCode=self.zip and self.zip[:5],
            FromPhone=phone and phone[-10:],
            FromEMail=self.party.email,
        )

    def address_to_endicia_to_address(self):
        '''
        Converts party address to Endicia To Address.

        :param return: Returns instance of ToAddress
        '''
        phone = self.party.phone
        zip = self.zip
        if phone:
            # Remove the special characters in the phone if any
            phone = "".join([char for char in phone if char in string.digits])
            if self.country and self.country.code != 'US':
                # International
                phone = phone[-30:]
                zip = zip and zip[:15]
            else:
                # Domestic
                phone = phone[-10:]
                zip = zip and zip[:5]

        return ToAddress(
            ToName=self.name or self.party.name,
            ToCompany=self.name or self.party.name,
            ToAddress1=self.street,
            ToAddress2=self.streetbis,
            ToAddress3=None,
            ToAddress4=None,
            ToCity=self.city,
            ToState=self.subdivision and self.subdivision.code[3:],
            ToPostalCode=zip,
            ToCountry=self.country and self.country.endicia_name,
            ToCountryCode=self.country and self.country.code,
            ToPhone=phone,
            ToEMail=self.party.email,
        )
