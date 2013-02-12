# -*- encoding: utf-8 -*-
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
"""
Endicia integration
"""
from trytond.pool import Pool
from .company import *
from .party import *
from .stock import *
from .carrier import *
from .sale import *


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
