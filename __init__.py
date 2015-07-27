# -*- encoding: utf-8 -*-
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
"""
Endicia integration
"""
from trytond.pool import Pool
from party import Address
from stock import (
    ShipmentOut, EndiciaRefundRequestWizardView, EndiciaRefundRequestWizard,
    BuyPostageWizardView, BuyPostageWizard, ShippingEndicia,
    GenerateShippingLabel
)
from shipment_bag import EndiciaShipmentBag
from carrier import Carrier, EndiciaMailclass
from sale import Configuration, Sale
from configuration import EndiciaConfiguration
from country import Country


def register():
    Pool.register(
        Address,
        Carrier,
        EndiciaMailclass,
        Configuration,
        Sale,
        EndiciaShipmentBag,
        ShipmentOut,
        EndiciaRefundRequestWizardView,
        BuyPostageWizardView,
        EndiciaConfiguration,
        Country,
        ShippingEndicia,
        module='shipping_endicia', type_='model'
    )
    Pool.register(
        EndiciaRefundRequestWizard,
        BuyPostageWizard,
        GenerateShippingLabel,
        module='shipping_endicia', type_='wizard'
    )
