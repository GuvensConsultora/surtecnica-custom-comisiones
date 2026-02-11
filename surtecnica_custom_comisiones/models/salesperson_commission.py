from odoo import models, fields, api


class SalespersonCommission(models.Model):
    """Comisión calculada por factura.

    Un registro por cada combinación (factura, regla/porcentaje).
    Si una factura tiene líneas con distintos porcentajes,
    se crean múltiples registros de comisión.

    Split 50/50: la mitad se devenga al facturar, la otra al cobrar.
    """
    _name = 'salesperson.commission'
    _description = 'Comisión de Vendedor'
    _order = 'date desc, id desc'

    move_id = fields.Many2one(
        'account.move', string='Factura', required=True,
        ondelete='cascade', index=True)
    salesperson_id = fields.Many2one(
        'res.users', string='Vendedor', required=True, index=True)
    rule_id = fields.Many2one(
        'salesperson.commission.rule', string='Regla Aplicada')
    partner_id = fields.Many2one(
        related='move_id.partner_id', string='Cliente',
        store=True, readonly=True)
    # Por qué: base_amount es el neto sin IVA (price_subtotal) de las líneas agrupadas
    base_amount = fields.Monetary(string='Monto Base (sin IVA)')
    commission_percentage = fields.Float(
        string='Comisión (%)', digits=(5, 2))
    commission_amount = fields.Monetary(string='Comisión Total (100%)')
    # Por qué: Split 50/50 — mitad al facturar, mitad al cobrar
    invoice_commission = fields.Monetary(string='Comisión Facturación (50%)')
    collection_commission = fields.Monetary(string='Comisión Cobro (50%)')
    invoice_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('accrued', 'Devengado'),
    ], string='Estado Facturación', default='pending', required=True)
    collection_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('accrued', 'Devengado'),
    ], string='Estado Cobro', default='pending', required=True)
    currency_id = fields.Many2one(
        related='move_id.currency_id', string='Moneda',
        store=True, readonly=True)
    date = fields.Date(
        related='move_id.invoice_date', string='Fecha',
        store=True, readonly=True)
    company_id = fields.Many2one(
        related='move_id.company_id', string='Compañía',
        store=True, readonly=True)
    # Por qué: Campo para identificar el tipo de movimiento en reportes
    move_type = fields.Selection(
        related='move_id.move_type', string='Tipo',
        store=True, readonly=True)
