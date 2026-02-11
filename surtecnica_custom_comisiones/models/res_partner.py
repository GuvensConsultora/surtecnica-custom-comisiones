from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Por qué: Override manual de zona para sub-zonas (ej: "Norte Buenos Aires").
    # Si está vacío, la zona se resuelve automáticamente por provincia.
    commission_zone_id = fields.Many2one(
        'commission.zone', string='Zona de Comisión',
        help='Asignar manualmente para sub-zonas. '
             'Si está vacío, se resuelve automáticamente por provincia.')
