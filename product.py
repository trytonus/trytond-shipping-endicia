#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
"Product custom details"
from trytond.model import ModelView, ModelSQL, fields

class Product(ModelSQL, ModelView):
    "Product extension for Endicia/USPS Shipping to add custom details"
    _name = "product.product"
    
    customs_desc = fields.Char('Customs Description')
    customs_value = fields.Float('Customs Value', digits=(7, 2))
    
Product()
