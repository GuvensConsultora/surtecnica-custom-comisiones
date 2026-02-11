from odoo import models, fields, api


class SalespersonCommissionRule(models.Model):
    """Reglas de comisión por vendedor.

    Prioridad de aplicación (la más específica gana):
    1. vendedor + cliente + categoría → máxima
    2. vendedor + cliente → alta
    3. vendedor + categoría → media
    4. vendedor solo → default/fallback
    """
    _name = 'salesperson.commission.rule'
    _description = 'Regla de Comisión de Vendedor'
    _order = 'salesperson_id, partner_id, product_category_id'

    salesperson_id = fields.Many2one(
        'res.users', string='Vendedor', required=True, index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Cliente',
        help='Dejar vacío para aplicar a todos los clientes')
    product_category_id = fields.Many2one(
        'product.category', string='Categoría de Producto',
        help='Dejar vacío para aplicar a todas las categorías')
    commission_percentage = fields.Float(
        string='Comisión (%)', required=True, digits=(5, 2))
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía',
        default=lambda self: self.env.company)

    # Por qué: SQL constraint evita reglas duplicadas para la misma combinación
    _sql_constraints = [
        ('unique_rule',
         'UNIQUE(salesperson_id, partner_id, product_category_id, company_id)',
         'Ya existe una regla para esta combinación de vendedor/cliente/categoría.'),
    ]

    @api.model
    def _get_commission_percentage(self, salesperson, partner, category):
        """Busca la regla más específica por prioridad descendente.

        Patrón: Specificity-based lookup — busca la combinación más precisa
        primero y cae a reglas más genéricas si no encuentra.

        Returns: (rule_record, percentage) o (False, 0.0) si no hay regla
        """
        domain_base = [
            ('salesperson_id', '=', salesperson.id),
            ('company_id', 'in', [self.env.company.id, False]),
        ]
        # Por qué: El commercial_partner_id agrupa contactos hijos bajo el partner comercial
        commercial_partner = partner.commercial_partner_id

        # Prioridad 1: vendedor + cliente + categoría
        rule = self.search(domain_base + [
            ('partner_id', '=', commercial_partner.id),
            ('product_category_id', '=', category.id),
        ], limit=1)
        if rule:
            return rule, rule.commission_percentage

        # Prioridad 2: vendedor + cliente (cualquier categoría)
        rule = self.search(domain_base + [
            ('partner_id', '=', commercial_partner.id),
            ('product_category_id', '=', False),
        ], limit=1)
        if rule:
            return rule, rule.commission_percentage

        # Prioridad 3: vendedor + categoría (cualquier cliente)
        rule = self.search(domain_base + [
            ('partner_id', '=', False),
            ('product_category_id', '=', category.id),
        ], limit=1)
        if rule:
            return rule, rule.commission_percentage

        # Prioridad 4: vendedor solo (regla default)
        rule = self.search(domain_base + [
            ('partner_id', '=', False),
            ('product_category_id', '=', False),
        ], limit=1)
        if rule:
            return rule, rule.commission_percentage

        return self.browse(), 0.0
