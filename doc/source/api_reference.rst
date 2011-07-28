.. Endicia Integration documentation master file, created by
   sphinx-quickstart on Sat Jul 23 11:23:35 2011.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.


API References
##############

contents:

.. toctree::
   :maxdepth: 5
   
Endicia Integration
"""""""""""""""""""

.. currentmodule:: trytond-endicia-integration

.. automodule:: company

Company
-------

    .. autoclass:: Company


        .. automethod:: __init__
            
        .. automethod:: get_endicia_credentials
        
.. automodule:: party

Party
-----

    .. autoclass:: Address


        .. automethod:: address_to_endicia_from_address
            
        .. automethod:: address_to_endicia_to_address
        
.. automodule:: stock

Stock
-----

    .. autoclass:: ShipmentOut
    
    
        .. automethod:: __init__
        
        .. automethod:: get_move_line_weights
        
        
    .. autoclass:: StockMakeShipmentWizardView
    
    
    .. autoclass:: Carrier
    
    
        .. automethod:: __init__
        
        .. automethod:: get_sale_price
        
        .. automethod:: label_from_shipment_out
    
    
    .. autoclass:: CarrierEndiciaUSPS
    
    
        .. automethod:: __init__
        
        .. automethod:: _add_items_from_moves
        
        .. automethod:: _make_label
        
        .. automethod:: label_from_shipment_out
        
        
    .. autoclass:: RefundRequestWizardView
    
    .. autoclass:: RefundRequestWizard
    
    
        .. automethod:: _request_refund
        
        
    .. autoclass:: SCANFormWizardView
    
    .. autoclass:: SCANFormWizard
    
    
        .. automethod:: _make_scanform

