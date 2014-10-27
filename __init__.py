# -*- encoding: utf-8 -*-
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
"""
Endicia integration
"""
from trytond.pool import Pool
from party import Address
from stock import (
    ShipmentOut, GenerateEndiciaLabelMessage, GenerateEndiciaLabel,
    EndiciaRefundRequestWizardView, EndiciaRefundRequestWizard,
    BuyPostageWizardView, BuyPostageWizard
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
        GenerateEndiciaLabelMessage,
        EndiciaRefundRequestWizardView,
        BuyPostageWizardView,
        EndiciaConfiguration,
        Country,
        module='endicia_integration', type_='model'
    )
    Pool.register(
        GenerateEndiciaLabel,
        EndiciaRefundRequestWizard,
        BuyPostageWizard,
        module='endicia_integration', type_='wizard'
    )
