from odoo import models, fields, api


class SalespersonCommissionRule(models.Model):
    """Reglas de comisión por vendedor.

    Prioridad por puntaje de especificidad (la más específica gana):
      partner_id presente → +4 puntos
      zone_id presente    → +2 puntos
      product_category_id → +1 punto

    Una sola query con ORDER BY campos DESC resuelve la prioridad.
    """
    _name = 'salesperson.commission.rule'
    _description = 'Regla de Comisión de Vendedor'
    _order = 'salesperson_id, partner_id, zone_id, product_category_id'

    salesperson_id = fields.Many2one(
        'res.users', string='Vendedor', required=True, index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Cliente',
        help='Dejar vacío para aplicar a todos los clientes')
    zone_id = fields.Many2one(
        'commission.zone', string='Zona',
        help='Dejar vacío para aplicar a todas las zonas')
    product_category_id = fields.Many2one(
        'product.category', string='Categoría de Producto',
        help='Dejar vacío para aplicar a todas las categorías')
    commission_percentage = fields.Float(
        string='Comisión (%)', required=True, digits=(5, 2))
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía',
        default=lambda self: self.env.company)

    # Por qué: SQL constraint incluye zone_id para permitir reglas distintas
    # por zona con mismo vendedor/cliente/categoría
    _sql_constraints = [
        ('unique_rule',
         'UNIQUE(salesperson_id, partner_id, zone_id, product_category_id, company_id)',
         'Ya existe una regla para esta combinación.'),
    ]

    @api.model
    def _get_commission_percentage(self, salesperson, partner, category, zone=None):
        """Busca la regla más específica con una sola query ordenada por puntaje.

        Patrón: Single-query specificity lookup — en vez de N búsquedas
        secuenciales, usa domain con OR por campo y ordena por campos NOT NULL.
        La regla más específica queda primera.

        Puntaje implícito por campo poblado:
          partner_id presente → +4
          zone_id presente    → +2
          product_category_id → +1

        Returns: (rule_record, percentage) o (browse(), 0.0) si no hay regla
        """
        # Por qué: El commercial_partner_id agrupa contactos hijos bajo el partner comercial
        commercial_partner = partner.commercial_partner_id
        zone_id = zone.id if zone else False

        domain = [
            ('salesperson_id', '=', salesperson.id),
            ('company_id', 'in', [self.env.company.id, False]),
            # Por qué: Cada OR permite matchear el valor exacto o vacío (wildcard)
            '|', ('partner_id', '=', commercial_partner.id), ('partner_id', '=', False),
            '|', ('zone_id', '=', zone_id), ('zone_id', '=', False),
            '|', ('product_category_id', '=', category.id), ('product_category_id', '=', False),
        ]
        # Por qué: ORDER DESC pone los campos NOT NULL primero → más específica gana
        rule = self.search(
            domain,
            order='partner_id DESC, zone_id DESC, product_category_id DESC',
            limit=1,
        )
        if rule:
            return rule, rule.commission_percentage

        return self.browse(), 0.0
