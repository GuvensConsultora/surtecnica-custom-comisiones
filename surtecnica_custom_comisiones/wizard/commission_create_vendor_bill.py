from odoo import models, fields, api, _
from odoo.exceptions import UserError
from collections import defaultdict


class CommissionCreateVendorBill(models.TransientModel):
    """Wizard para crear facturas de proveedor desde comisiones seleccionadas.

    Agrupa comisiones por vendedor y crea una factura de proveedor por cada uno.
    Solo factura porciones devengadas (accrued) y no facturadas previamente.

    Por qué: Diario sin documentos AFIP para evitar numeración fiscal en
    facturas internas de comisiones.
    """
    _name = 'commission.create.vendor.bill'
    _description = 'Crear Factura de Proveedor por Comisiones'

    journal_id = fields.Many2one(
        'account.journal', string='Diario', required=True,
        # Por qué: Solo diarios de compra sin documentos AFIP
        domain="[('type', '=', 'purchase'), ('l10n_latam_use_documents', '=', False)]",
    )
    commission_ids = fields.Many2many(
        'salesperson.commission', string='Comisiones',
    )

    @api.model
    def default_get(self, fields_list):
        """Carga las comisiones seleccionadas desde el contexto."""
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            res['commission_ids'] = [(6, 0, active_ids)]
        return res

    def action_create_bills(self):
        """Crea facturas de proveedor agrupadas por vendedor.

        Patrón: Agrupa comisiones por salesperson_id, crea una factura por
        vendedor con líneas detalladas por cada porción devengada sin facturar.

        Returns: action para ver las facturas creadas
        """
        self.ensure_one()
        if not self.commission_ids:
            raise UserError(_('No se seleccionaron comisiones.'))

        product = self.env.ref(
            'surtecnica_custom_comisiones.product_commission')

        # Por qué: Agrupar por vendedor para crear una factura por cada uno
        grouped = defaultdict(lambda: self.env['salesperson.commission'])
        for comm in self.commission_ids:
            grouped[comm.salesperson_id] |= comm

        bills = self.env['account.move']

        for salesperson, comms in grouped.items():
            lines_data = []
            link_map = []  # [(commission, portion_field)]

            for comm in comms:
                # Porción facturación: devengada y sin factura de proveedor
                if (comm.invoice_status == 'accrued'
                        and not comm.invoice_vendor_bill_id):
                    label = 'Facturación'
                    name = (
                        f"Comisión {comm.commission_percentage}% - "
                        f"{comm.move_id.name} - "
                        f"{comm.partner_id.name} ({label})"
                    )
                    lines_data.append((0, 0, {
                        'product_id': product.id,
                        'name': name,
                        'quantity': 1,
                        'price_unit': comm.invoice_commission,
                    }))
                    link_map.append((comm, 'invoice_vendor_bill_id'))

                # Porción cobro: devengada y sin factura de proveedor
                if (comm.collection_status == 'accrued'
                        and not comm.collection_vendor_bill_id):
                    label = 'Cobro'
                    name = (
                        f"Comisión {comm.commission_percentage}% - "
                        f"{comm.move_id.name} - "
                        f"{comm.partner_id.name} ({label})"
                    )
                    lines_data.append((0, 0, {
                        'product_id': product.id,
                        'name': name,
                        'quantity': 1,
                        'price_unit': comm.collection_commission,
                    }))
                    link_map.append((comm, 'collection_vendor_bill_id'))

            if not lines_data:
                continue

            # Por qué: partner_id del bill es el partner vinculado al vendedor
            bill = self.env['account.move'].create({
                'move_type': 'in_invoice',
                'partner_id': salesperson.partner_id.id,
                'journal_id': self.journal_id.id,
                'invoice_date': fields.Date.today(),
                'invoice_line_ids': lines_data,
            })

            # Vincular cada comisión con la factura de proveedor creada
            for comm, field_name in link_map:
                comm.write({field_name: bill.id})

            bills |= bill

        if not bills:
            raise UserError(_(
                'No hay porciones devengadas sin facturar en las '
                'comisiones seleccionadas.'
            ))

        # Por qué: Retorna action para mostrar las facturas creadas
        action = self.env['ir.actions.act_window']._for_xml_id(
            'account.action_move_in_invoice_type')
        if len(bills) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = bills.id
        else:
            action['domain'] = [('id', 'in', bills.ids)]
        return action
