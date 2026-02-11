from odoo import models, fields, api
from collections import defaultdict


class AccountMove(models.Model):
    _inherit = 'account.move'

    commission_ids = fields.One2many(
        'salesperson.commission', 'move_id', string='Comisiones')
    commission_count = fields.Integer(
        string='Comisiones', compute='_compute_commission_count')

    @api.depends('commission_ids')
    def _compute_commission_count(self):
        for move in self:
            move.commission_count = len(move.commission_ids)

    # --- Trigger de cobro ---
    # Por qué: payment_state es un stored computed field. Los stored computed
    # NO pasan por write() — Odoo los persiste directo a DB vía _write().
    # Override _compute_payment_state es la forma correcta de interceptar
    # el cambio de estado de pago.
    @api.depends('amount_residual', 'move_type', 'state', 'company_id')
    def _compute_payment_state(self):
        super()._compute_payment_state()
        # Por qué: Después del compute estándar, chequeamos si alguna factura
        # pasó a 'paid'/'in_payment' y tiene comisiones de cobro pendientes.
        for move in self:
            if (move.move_type == 'out_invoice'
                    and move.payment_state in ('paid', 'in_payment')
                    and move.commission_ids):
                move.commission_ids.filtered(
                    lambda c: c.collection_status == 'pending'
                ).write({'collection_status': 'accrued'})

    def action_view_commissions(self):
        """Acción del smart button para ver comisiones de esta factura."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Comisiones',
            'res_model': 'salesperson.commission',
            'view_mode': 'tree,form',
            'domain': [('move_id', '=', self.id)],
            'context': {'default_move_id': self.id},
        }

    def _post(self, soft=True):
        """Override: al confirmar factura/NC, calcula comisiones automáticamente.

        Patrón: Herencia estándar Odoo — super() primero para que la factura
        quede posted, luego generamos las comisiones.
        """
        posted = super()._post(soft=soft)
        for move in posted:
            # Por qué: Solo facturas y NC de cliente generan comisiones
            if move.move_type in ('out_invoice', 'out_refund'):
                move._generate_commissions()
        return posted

    def _generate_commissions(self):
        """Genera registros de comisión agrupados por regla/porcentaje.

        Por cada línea de producto:
        1. Busca la regla más específica
        2. Agrupa montos por regla
        3. Crea un registro de comisión por grupo
        """
        self.ensure_one()
        # Por qué: Evita duplicar comisiones si se re-confirma
        if self.commission_ids:
            return

        salesperson = self.invoice_user_id
        if not salesperson:
            return

        partner = self.partner_id
        RuleModel = self.env['salesperson.commission.rule']

        # Por qué: Agrupa por regla para crear un registro por porcentaje distinto
        # key: (rule_id, percentage) → value: sum(price_subtotal)
        grouped = defaultdict(float)

        for line in self.invoice_line_ids:
            # Por qué: display_type 'product' filtra solo líneas de producto (Odoo 17)
            if line.display_type != 'product':
                continue
            if not line.product_id:
                continue

            category = line.product_id.categ_id
            rule, percentage = RuleModel._get_commission_percentage(
                salesperson, partner, category)

            if percentage <= 0:
                continue

            # Por qué: price_subtotal es el neto sin IVA por línea
            grouped[(rule.id, percentage)] += line.price_subtotal

        is_refund = self.move_type == 'out_refund'
        CommissionModel = self.env['salesperson.commission']

        for (rule_id, percentage), base_amount in grouped.items():
            # Por qué: NC genera comisión negativa para revertir
            if is_refund:
                base_amount = -abs(base_amount)

            commission_amount = base_amount * percentage / 100.0
            invoice_commission = commission_amount / 2.0
            collection_commission = commission_amount / 2.0

            CommissionModel.create({
                'move_id': self.id,
                'salesperson_id': salesperson.id,
                'rule_id': rule_id or False,
                'base_amount': base_amount,
                'commission_percentage': percentage,
                'commission_amount': commission_amount,
                'invoice_commission': invoice_commission,
                'collection_commission': collection_commission,
                # Por qué: Al facturar, el 50% de facturación se devenga inmediato
                'invoice_status': 'accrued',
                # Por qué: NC devenga ambos 50% al instante (descuenta de una)
                'collection_status': 'accrued' if is_refund else 'pending',
            })
