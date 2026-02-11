from odoo import models, fields, api


class CommissionZone(models.Model):
    """Zona geográfica para reglas de comisión.

    Dos niveles de uso:
    - Zona provincial: state_id seteado → matchea automáticamente por provincia del partner
    - Sub-zona: misma provincia, zona más específica → requiere asignación manual en el partner

    Por qué: Odoo no tiene concepto de "zona comercial" nativo.
    Este modelo permite agrupar clientes geográficamente para aplicar
    porcentajes de comisión diferenciados por región.
    """
    _name = 'commission.zone'
    _description = 'Zona de Comisión'
    _order = 'country_id, state_id, name'

    name = fields.Char(string='Nombre', required=True)
    country_id = fields.Many2one(
        'res.country', string='País', required=True, index=True)
    state_id = fields.Many2one(
        'res.country.state', string='Provincia',
        domain="[('country_id', '=', country_id)]",
        help='Dejar vacío para aplicar a todo el país')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('unique_zone_name',
         'UNIQUE(name, company_id)',
         'Ya existe una zona con este nombre.'),
    ]

    company_id = fields.Many2one(
        'res.company', string='Compañía',
        default=lambda self: self.env.company)

    @api.model
    def _resolve_zone(self, partner):
        """Resuelve la zona de comisión de un partner.

        Prioridad:
        1. commission_zone_id del partner (override manual, para sub-zonas)
        2. Zona que matchee por state_id del partner (automática)
        3. Sin zona

        Returns: commission.zone record o browse vacío
        """
        # Por qué: Override manual tiene prioridad → permite sub-zonas
        if partner.commission_zone_id:
            return partner.commission_zone_id

        # Por qué: Búsqueda automática por provincia del partner
        if partner.state_id:
            zone = self.search([
                ('state_id', '=', partner.state_id.id),
                ('country_id', '=', partner.country_id.id),
            ], limit=1)
            if zone:
                return zone

        return self.browse()
