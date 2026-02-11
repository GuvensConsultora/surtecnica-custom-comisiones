{
    'name': 'Sur Técnica - Comisiones de Vendedores',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Cálculo automático de comisiones: 50% al facturar, 50% al cobrar',
    'description': """
        Módulo de comisiones para vendedores con reglas variables
        por vendedor, cliente y categoría de producto.
        - 50% de comisión se devenga al confirmar factura
        - 50% restante se devenga al cobrar (amount_residual = 0)
        - Notas de crédito generan comisión negativa
    """,
    'author': 'Guvens Consultora',
    'website': 'https://guvens.com',
    'license': 'LGPL-3',
    'depends': ['account', 'sale', 'product'],
    'data': [
        'security/ir.model.access.csv',
        'views/salesperson_commission_rule_views.xml',
        'views/salesperson_commission_views.xml',
        'views/account_move_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
