# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from decimal import Decimal
import logging

from endicia import PostageRatesAPI
from endicia.tools import objectify_response
from endicia.exceptions import RequestError
from trytond.model import fields
from trytond.pool import PoolMeta, Pool


__all__ = ['Configuration', 'Sale']
__metaclass__ = PoolMeta

logger = logging.getLogger(__name__)


class Configuration:
    'Sale Configuration'
    __name__ = 'sale.configuration'

    usps_box_type = fields.Many2One(
        'carrier.box_type', 'USPS Box Type', required=True
    )


class Sale:
    "Sale"
    __name__ = 'sale.sale'

    def get_shipping_rate(self, carrier, carrier_service=None, silent=False):
        """
        Call the rates service and get possible quotes for shipment for eligible
        mail classes
        """
        Currency = Pool().get('currency.currency')
        UOM = Pool().get('product.uom')
        ModelData = Pool().get('ir.model.data')

        if carrier.carrier_cost_method != "endicia":
            return super(Sale, self).get_shipping_rate(
                carrier, carrier_service, silent
            )

        from_address = self._get_ship_from_address()
        if self.shipment_address.country.code == "US":
            mailclass_type = "Domestic"
        else:
            mailclass_type = "International"

        uom_oz = UOM.search([('symbol', '=', 'oz')])[0]

        # Endicia only support 1 decimal place in weight
        weight_oz = "%.1f" % UOM.compute_qty(
            self.weight_uom, self.weight, uom_oz
        )
        to_zip = self.shipment_address.zip
        if mailclass_type == 'Domestic':
            to_zip = to_zip and to_zip[:5]
        else:
            # International
            to_zip = to_zip and to_zip[:15]
        postage_rates_request = PostageRatesAPI(
            mailclass=mailclass_type,
            weightoz=weight_oz,
            from_postal_code=from_address.zip[:5],
            to_postal_code=to_zip,
            to_country_code=self.shipment_address.country.code,
            accountid=carrier.endicia_account_id,
            requesterid=carrier.endicia_requester_id,
            passphrase=carrier.endicia_passphrase,
            test=carrier.endicia_is_test,
        )

        # Logging.
        logger.debug(
            'Making Postage Rates Request for shipping rates of'
            'Sale ID: {0} and Carrier ID: {1}'
            .format(self.id, carrier.id)
        )
        logger.debug('--------POSTAGE RATES REQUEST--------')
        logger.debug(str(postage_rates_request.to_xml()))
        logger.debug('--------END REQUEST--------')

        try:
            response_xml = postage_rates_request.send_request()
            response = objectify_response(response_xml)
        except RequestError, e:
            self.raise_user_error(unicode(e))
        except Exception, e:
            if not silent:
                raise
            logger.debug('--------ENDICIA ERROR-----------')
            logger.debug(unicode(e))
            logger.debug('--------ENDICIA END ERROR-----------')
            return []

        # Logging.
        logger.debug('--------POSTAGE RATES RESPONSE--------')
        logger.debug(str(response_xml))
        logger.debug('--------END RESPONSE--------')

        allowed_services = {
            service.code: service for service in carrier.services
        }
        rates = []
        for postage_price in response.PostagePrice:
            service = allowed_services.get(postage_price.MailClass)
            if not service:
                continue

            currency = Currency(ModelData.get_id('currency', 'usd'))
            rate = {
                'carrier': carrier,
                'carrier_service': service,
                'cost': currency.round(
                    Decimal(postage_price.get('TotalAmount'))
                ),
                'cost_currency': currency
            }

            rate['display_name'] = "USPS %s" % (
                service.name
            )

            rates.append(rate)

        if carrier_service:
            return filter(
                lambda r: r['carrier_service'] == carrier_service,
                rates
            )
        return rates
