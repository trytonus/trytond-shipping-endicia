# -*- coding: UTF-8 -*-
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

{
    'name': 'Integration with Endicia - USPS',
    'description': '''
        The Endicia Label Server produces an integrated label image, 
        complete with Stealth (hidden) postage, return addresses, 
        verified delivery addresses, and service barcodes ''',
    'version': '2.0.0.3',
    'author': 'Openlabs Technologies & Consulting (P) LTD',
    'email': 'info@openlabs.co.in',
    'website': 'http://www.openlabs.co.in/',
    'depends': [
        'stock',
        'shipping',
    ],
    'xml': [
       'company.xml',
       'stock.xml',
       'shipping_data.xml'
    ],
    'translation': [
    ],
}
