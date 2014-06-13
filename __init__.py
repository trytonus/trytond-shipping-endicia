# -*- encoding: utf-8 -*-
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
"""
Endicia integration
"""
from trytond.pool import Pool
from company import Company
from party import Address
from stock import (
    ShipmentOut, GenerateEndiciaLabelMessage, GenerateEndiciaLabel,
    EndiciaRefundRequestWizardView, EndiciaRefundRequestWizard,
    SCANFormWizardView, SCANFormWizard, BuyPostageWizardView,
    BuyPostageWizard, StockMove
)
from carrier import Carrier, EndiciaMailclass
from sale import Configuration, Sale, SaleLine


def register():
    Pool.register(
        Company,
        Address,
        Carrier,
        EndiciaMailclass,
        Configuration,
        Sale,
        SaleLine,
        StockMove,
        ShipmentOut,
        GenerateEndiciaLabelMessage,
        EndiciaRefundRequestWizardView,
        SCANFormWizardView,
        BuyPostageWizardView,
        module='endicia_integration', type_='model')
    Pool.register(
        GenerateEndiciaLabel,
        EndiciaRefundRequestWizard,
        SCANFormWizard,
        BuyPostageWizard,
        module='endicia_integration', type_='wizard')
