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

    # --- Facturación a proveedor ---
    # Por qué: Cada porción (50% facturación / 50% cobro) se factura por separado
    # al vendedor como proveedor. ondelete='set null' limpia el vínculo si se borra el bill.
    invoice_vendor_bill_id = fields.Many2one(
        'account.move', string='Fact. Prov. (Facturación)',
        ondelete='set null', copy=False,
        help='Factura de proveedor que cubre la porción de facturación (50%)')
    collection_vendor_bill_id = fields.Many2one(
        'account.move', string='Fact. Prov. (Cobro)',
        ondelete='set null', copy=False,
        help='Factura de proveedor que cubre la porción de cobro (50%)')

    # Por qué: Estado consolidado de facturación al proveedor
    # pending = ninguna porción facturada, partial = una de dos, billed = ambas
    billing_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('partial', 'Parcial'),
        ('billed', 'Facturado'),
    ], string='Estado Facturación Prov.',
        compute='_compute_billing_status', store=True)

    # Por qué: Estado consolidado de pago al proveedor
    payment_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('partial', 'Parcial'),
        ('paid', 'Pagado'),
    ], string='Estado Pago Prov.',
        compute='_compute_payment_status', store=True)

    # Por qué: Montos computed para reportes pivot/tree con sums
    billed_amount = fields.Monetary(
        string='Monto Facturado',
        compute='_compute_billing_status', store=True)
    paid_amount = fields.Monetary(
        string='Monto Pagado',
        compute='_compute_payment_status', store=True)

    @api.depends('invoice_vendor_bill_id', 'collection_vendor_bill_id')
    def _compute_billing_status(self):
        """Calcula estado y monto facturado al proveedor.

        Patrón: Cuenta cuántas porciones tienen bill vinculado para
        determinar pending/partial/billed.
        """
        for rec in self:
            has_inv = bool(rec.invoice_vendor_bill_id)
            has_col = bool(rec.collection_vendor_bill_id)
            billed = 0.0
            if has_inv:
                billed += rec.invoice_commission
            if has_col:
                billed += rec.collection_commission
            rec.billed_amount = billed

            if has_inv and has_col:
                rec.billing_status = 'billed'
            elif has_inv or has_col:
                rec.billing_status = 'partial'
            else:
                rec.billing_status = 'pending'

    @api.depends(
        'invoice_vendor_bill_id.payment_state',
        'collection_vendor_bill_id.payment_state',
    )
    def _compute_payment_status(self):
        """Calcula estado y monto pagado al proveedor.

        Por qué: Depende del payment_state de cada bill vinculado.
        Solo suma la porción si el bill está paid/in_payment.
        """
        paid_states = ('paid', 'in_payment')
        for rec in self:
            inv_paid = (rec.invoice_vendor_bill_id.payment_state
                        in paid_states) if rec.invoice_vendor_bill_id else False
            col_paid = (rec.collection_vendor_bill_id.payment_state
                        in paid_states) if rec.collection_vendor_bill_id else False

            paid = 0.0
            if inv_paid:
                paid += rec.invoice_commission
            if col_paid:
                paid += rec.collection_commission
            rec.paid_amount = paid

            if inv_paid and col_paid:
                rec.payment_status = 'paid'
            elif inv_paid or col_paid:
                rec.payment_status = 'partial'
            else:
                rec.payment_status = 'pending'

    def action_view_vendor_bills(self):
        """Smart button: muestra las facturas de proveedor vinculadas."""
        self.ensure_one()
        bill_ids = []
        if self.invoice_vendor_bill_id:
            bill_ids.append(self.invoice_vendor_bill_id.id)
        if self.collection_vendor_bill_id:
            bill_ids.append(self.collection_vendor_bill_id.id)

        if len(bill_ids) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': bill_ids[0],
            }
        return {
            'type': 'ir.actions.act_window',
            'name': 'Facturas de Proveedor',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', bill_ids)],
        }
