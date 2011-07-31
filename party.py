# -*- encoding: utf-8 -*-
"""
Customizes party address to have address in correct format for Endicia API .
"""
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

# pylint: disable=E1101
# pylint: disable=F0401

import string
from endicia import FromAddress, ToAddress
from trytond.model import ModelView, ModelSQL
from trytond.transaction import Transaction

class Address(ModelSQL, ModelView):
    '''
    Address
    '''
    _name = "party.address"

    def address_to_endicia_from_address(self, id):
        '''
        Converts partner address to Endicia Form Address.

        :param id: ID of record
        :param return: Returns instance of FromAddress
        '''
        user_obj = self.pool.get('res.user')
        if type(id) == list:
            id = id[0]
        address = self.browse(id)
        user_rec = user_obj.browse(Transaction().user)
        phone = address.party.phone
        if phone:
            # Remove the special characters in the phone if any
            phone = "".join([char for char in phone if char in string.digits])
        return FromAddress(
            FromName = user_rec.name or None,
            #FromCompany = user_rec.company.name or None,
            ReturnAddress1 = address.street or None,
            ReturnAddress2 = address.streetbis or None,
            ReturnAddress3 = None,
            ReturnAddress4 = None,
            FromCity = address.city or None,
            FromState = address.subdivision and \
                address.subdivision.code[3:] or None,
            FromPostalCode = address.zip or None,
            FromPhone = phone or None,
            FromEMail = address.party.email or None,
        )

    def address_to_endicia_to_address(self, id):
        '''
        Converts party address to Endicia Form Address.

        :param id: ID of record
        :param return: Returns instance of ToAddress
        '''
        if type(id) == list:
            id = id[0]
        address = self.browse(id)
        phone = address.party.phone
        if phone:
            # Remove the special characters in the phone if any
            phone = "".join([char for char in phone if char in string.digits])
        return ToAddress(
            ToName = address.name or None,
            ToCompany = address.party and address.party.name or None,
            ToAddress1 = address.street or None,
            ToAddress2 = address.streetbis or None,
            ToAddress3 = None,
            ToAddress4 = None,
            ToCity = address.city or None,
            ToState = address.subdivision and \
                address.subdivision.code[3:] or None,
            ToPostalCode = address.zip or None,
            ToCountry = address.country and address.country.name or None,
            ToCountryCode = address.country and \
                address.country.code or None,
            ToPhone = phone or None,
            ToEMail = address.party.email or None,
        )

Address()
