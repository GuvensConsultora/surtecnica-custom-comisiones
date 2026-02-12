# Sur Técnica - Comisiones de Vendedores (Odoo 17)

---

# Bloque 1: Introducción

## Qué hace Odoo nativamente

Odoo 17 asigna un vendedor a cada pedido de venta (`sale.order.user_id`) y lo propaga a la factura (`account.move.invoice_user_id`). También gestiona el ciclo completo de facturación y cobro con estados de pago (`payment_state`).

**Lo que Odoo NO hace:** calcular comisiones. No existe un mecanismo nativo para definir porcentajes de comisión por vendedor, ni para calcularlos automáticamente al facturar o cobrar.

## Qué problema resuelve este módulo

El cálculo de comisiones se hacía manualmente con planillas, generando errores, demoras y discusiones. Se necesitaba:

- Automatizar el cálculo al confirmar facturas y al cobrar
- Soportar porcentajes diferentes según vendedor, cliente, zona geográfica, producto y categoría de producto
- Que la regla más específica siempre gane sobre la más genérica
- Revertir comisiones automáticamente con Notas de Crédito
- Dividir la comisión 50% al facturar y 50% al cobrar

## Qué agrega este módulo

- **Zonas geográficas** — Regiones comerciales (provinciales o sub-zonas) para diferenciar comisiones por ubicación del cliente
- **Reglas de comisión inteligentes** — Porcentajes por combinación de vendedor + cliente + zona + producto + categoría, donde la regla más específica siempre gana
- **Cálculo automático** — Al confirmar factura se devenga el 50%, al cobrar se devenga el otro 50%
- **Reversión automática** — Las Notas de Crédito generan comisión negativa
- **Reportes** — Lista, pivot y gráfico de comisiones por vendedor

---

# Bloque 2: Funcionamiento para el usuario final

## Qué ve el usuario

### En la factura

Al confirmar una factura de cliente, el sistema calcula la comisión automáticamente. En la factura aparece un botón **"Comisiones"** (icono $) que muestra los registros de comisión generados.

### En el menú Facturación

```
Facturación
  └── Comisiones
        ├── Comisiones          ← Ver todas las comisiones (lista, pivot, gráfico)
        ├── Reglas de Comisión  ← Configurar porcentajes (solo gerentes)
        └── Zonas               ← Configurar zonas geográficas (solo gerentes)
```

### En el contacto

En la pestaña **"Ventas y compras"** aparece el campo **"Zona de Comisión"** para asignar manualmente una sub-zona al cliente.

## Cómo se calcula la comisión

### Momento 1: Al confirmar la factura

El sistema toma cada línea de producto de la factura y busca qué porcentaje de comisión corresponde. Calcula el total y devenga el **50% de facturación** inmediatamente.

### Momento 2: Al cobrar la factura

Cuando el cliente paga el total, el sistema devenga el **50% de cobro** restante. Recién ahí la comisión está 100% devengada.

### Notas de Crédito

Si se emite una NC, se genera una comisión **negativa** que resta del total. Ambos 50% se devengan al instante.

### Ejemplo numérico

Factura de $100.000 + IVA al cliente Acme SA, vendedor Juan, comisión 6%:

| Momento | Comisión total | 50% Facturación | 50% Cobro |
|---------|:--------------:|:---------------:|:---------:|
| Confirmar factura | $6.000 | $3.000 Devengado | $3.000 Pendiente |
| Cobrar factura | $6.000 | $3.000 Devengado | $3.000 Devengado |

NC posterior por $20.000 (misma regla 6%):

| Momento | Comisión total | 50% Facturación | 50% Cobro |
|---------|:--------------:|:---------------:|:---------:|
| Confirmar NC | -$1.200 | -$600 Devengado | -$600 Devengado |

**Comisión neta de Juan:** $6.000 - $1.200 = **$4.800**

## Por qué la regla más específica gana sobre la genérica

Imaginemos que Juan es vendedor y tiene una comisión base del 2% para todos sus clientes. Pero Acme SA es un cliente VIP que genera mucho volumen, entonces se le pone 6%. Y si encima Acme SA compra Herramientas (categoría con buen margen), se le pone 10%.

**Si no existiera prioridad por especificidad**, el sistema no sabría cuál regla aplicar cuando Juan le vende Herramientas a Acme SA: ¿el 2% genérico? ¿el 6% del cliente? ¿el 10% de cliente+categoría?

**La regla es simple: cuanto más detalles tiene una regla, más específica es, y gana.** Es como un embudo:

```
Regla genérica (solo vendedor)           → 2%    ← aplica a TODOS los clientes
  └─ Regla con zona                      → 4%    ← aplica a clientes de esa zona
      └─ Regla con zona + producto       → 5%    ← aplica a ese producto en esa zona
          └─ Regla con cliente            → 6%    ← aplica a ese cliente específico
              └─ Regla con cliente + zona + producto → 10%  ← máxima especificidad
```

**Siempre gana la regla que más se parece a la situación real de la factura.** Si hay una regla que dice exactamente "este vendedor + este cliente + esta zona + este producto", esa gana sobre cualquier regla más genérica. Si no existe una regla tan específica, el sistema busca la siguiente más cercana, y así hasta llegar a la regla default del vendedor.

### Tabla de prioridades

Cada campo que se completa en una regla suma puntos. La regla con más puntos gana:

| Campo completado | Puntos |
|------------------|:------:|
| Cliente | +8 |
| Zona | +4 |
| Producto | +2 |
| Categoría de producto | +1 |

| Puntaje | La regla tiene... | Ejemplo |
|:-------:|-------------------|---------|
| 15 | Cliente + Zona + Producto + Categoría | Acme SA + Buenos Aires + Taladro Bosch + Herramientas → 12% |
| 12 | Cliente + Zona | Acme SA + Buenos Aires → 8% |
| 10 | Cliente + Producto | Acme SA + Taladro Bosch → 7% |
| 9 | Cliente + Categoría | Acme SA + Herramientas → 6.5% |
| 8 | Cliente | Acme SA → 6% |
| 6 | Zona + Producto | Buenos Aires + Taladro Bosch → 5.5% |
| 5 | Zona + Categoría | Buenos Aires + Herramientas → 5% |
| 4 | Zona | Buenos Aires → 4% |
| 3 | Producto + Categoría | Taladro Bosch + Herramientas → 3.5% |
| 2 | Producto | Taladro Bosch → 3% |
| 1 | Categoría | Herramientas → 2.5% |
| 0 | *(todo vacío)* | Default del vendedor → 2% |

**En resumen:** Cliente gana sobre Zona, Zona gana sobre Producto, Producto gana sobre Categoría. Y las combinaciones suman.

### Ejemplo completo: vendedor Juan Pérez con 7 reglas

| # | Cliente | Zona | Producto | Categoría | % |
|---|---------|------|----------|-----------|:-:|
| R1 | *(vacío)* | *(vacío)* | *(vacío)* | *(vacío)* | 2% |
| R2 | *(vacío)* | Buenos Aires | *(vacío)* | *(vacío)* | 4% |
| R3 | *(vacío)* | Norte Buenos Aires | *(vacío)* | *(vacío)* | 5% |
| R4 | *(vacío)* | Córdoba | *(vacío)* | Herramientas | 3.5% |
| R5 | *(vacío)* | *(vacío)* | Taladro Bosch | *(vacío)* | 3% |
| R6 | Acme SA | *(vacío)* | *(vacío)* | *(vacío)* | 6% |
| R7 | Acme SA | Buenos Aires | *(vacío)* | Herramientas | 13% |

**Qué pasa al facturar:**

| Factura para... | Zona | Producto | Regla | % | Por qué |
|-----------------|------|----------|:-----:|:-:|---------|
| López SRL (Mendoza) | *(sin zona)* | Tornillos | R1 | 2% | Nada matchea → default |
| López SRL (Mendoza) | *(sin zona)* | Taladro Bosch | R5 | 3% | Producto específico (puntaje 2) |
| Distribuidora BA (Bs.As.) | Buenos Aires | Tornillos | R2 | 4% | Zona Buenos Aires (puntaje 4) |
| Distribuidora BA (Bs.As.) | Buenos Aires | Taladro Bosch | R2 | 4% | Zona (4) > producto (2) |
| Ferretería Norte (Bs.As.) | Norte BA | Tornillos | R3 | 5% | Sub-zona Norte BA (puntaje 4) |
| Metalúrgica Cba (Córdoba) | Córdoba | Llave francesa | R4 | 3.5% | Zona + categoría Herramientas (puntaje 5) |
| Metalúrgica Cba (Córdoba) | Córdoba | Tornillos | R1 | 2% | Zona Córdoba sin regla para Insumos → default |
| Acme SA (Bs.As.) | Buenos Aires | Tornillos | R6 | 6% | Cliente (8) > zona (4) |
| Acme SA (Bs.As.) | Buenos Aires | Llave francesa | R7 | 13% | Cliente + zona + categoría (puntaje 13) |

### Factura mixta (varias líneas con distintas reglas)

Si una factura tiene líneas de distintos productos/categorías, cada línea busca su propia regla. Se generan registros de comisión agrupados por porcentaje.

**Factura de Acme SA (Buenos Aires) con 3 líneas:**

| Línea | Producto | Categoría | Subtotal sin IVA | Regla | % |
|-------|----------|-----------|:----------------:|:-----:|:-:|
| 1 | Llave francesa | Herramientas | $50.000 | R7 | 13% |
| 2 | Tornillos x1000 | Insumos | $10.000 | R6 | 6% |
| 3 | Guantes | Insumos | $5.000 | R6 | 6% |

**Comisiones generadas (agrupadas por %):**

| Regla | Base | % | Comisión total | 50% Facturación | 50% Cobro |
|:-----:|:----:|:-:|:--------------:|:---------------:|:---------:|
| R7 | $50.000 | 13% | $6.500 | $3.250 (devengado) | $3.250 (pendiente) |
| R6 | $15.000 | 6% | $900 | $450 (devengado) | $450 (pendiente) |
| **Total** | **$65.000** | | **$7.400** | **$3.700** | **$3.700** |

## Reportes

### Vista de lista

Todas las comisiones con columnas sumables al pie:

```
┌──────────┬─────────────────────┬────────────┬───────────┬──────────┬───────┬───────────┬─────────────┬──────────┬──────────────┬──────────┐
│ Fecha    │ Factura             │ Vendedor   │ Cliente   │ Base     │ %     │ Comisión  │ Facturación │ Estado   │ Cobro        │ Estado   │
├──────────┼─────────────────────┼────────────┼───────────┼──────────┼───────┼───────────┼─────────────┼──────────┼──────────────┼──────────┤
│ 01/02/26 │ FA-A 0001-00000020  │ Juan Pérez │ Acme SA   │ $100.000 │ 6,00  │ $6.000,00 │ $3.000,00   │ Deveng.  │ $3.000,00    │ Pendient.│
│ 01/02/26 │ FA-A 0001-00000021  │ Juan Pérez │ López SRL │ $50.000  │ 2,00  │ $1.000,00 │ $500,00     │ Deveng.  │ $500,00      │ Deveng.  │
│ 03/02/26 │ NC-A 0001-00000005  │ Juan Pérez │ Acme SA   │ -$20.000 │ 6,00  │-$1.200,00 │ -$600,00    │ Deveng.  │ -$600,00     │ Deveng.  │
├──────────┼─────────────────────┼────────────┼───────────┼──────────┼───────┼───────────┼─────────────┼──────────┼──────────────┼──────────┤
│          │                     │            │  TOTALES  │ $130.000 │       │ $5.800,00 │ $2.900,00   │          │ $2.900,00    │          │
└──────────┴─────────────────────┴────────────┴───────────┴──────────┴───────┴───────────┴─────────────┴──────────┴──────────────┴──────────┘
```

**Filtros:** Facturas / Notas de Crédito / Facturación Pendiente / Cobro Pendiente

**Agrupar por:** Vendedor, Cliente, Fecha (mes)

### Vista pivot (tabla dinámica)

Cruza vendedores en filas con meses en columnas. Ideal para liquidación mensual:

```
                          │  Enero 2026  │  Febrero 2026  │    Total
──────────────────────────┼──────────────┼────────────────┼───────────
  Juan Pérez              │              │                │
    Comisión Total        │    $8.500    │     $5.800     │  $14.300
    50% Facturación       │    $4.250    │     $2.900     │   $7.150
    50% Cobro             │    $4.250    │     $2.900     │   $7.150
    Base                  │  $180.000    │   $130.000     │ $310.000
──────────────────────────┼──────────────┼────────────────┼───────────
  María García            │              │                │
    Comisión Total        │    $3.200    │     $4.100     │   $7.300
──────────────────────────┼──────────────┼────────────────┼───────────
  TOTAL                   │   $11.700    │     $9.900     │  $21.600
```

Personalizable: arrastrar campos a filas/columnas/medidas.

### Vista gráfico

Barras con comisión total por vendedor para comparar rendimiento:

```
  Juan Pérez    ████████████████████████████  $14.300
  María García  ██████████████████           $7.300
  Pedro López   ████████████                 $5.100
```

---

# Bloque 3: Parametrización

## Paso 1: Crear zonas geográficas

**Ir a: Facturación → Comisiones → Zonas**

### Zonas provinciales (matcheo automático)

Se crean con país + provincia. Cualquier cliente que tenga esa provincia en su ficha se asocia automáticamente, sin intervención manual.

| Zona | País | Provincia | Comportamiento |
|------|------|-----------|----------------|
| Buenos Aires | Argentina | Buenos Aires | Auto-matchea todos los clientes con provincia Buenos Aires |
| Córdoba | Argentina | Córdoba | Auto-matchea todos los clientes con provincia Córdoba |
| Santa Fe | Argentina | Santa Fe | Auto-matchea todos los clientes con provincia Santa Fe |

### Sub-zonas (asignación manual)

Cuando una provincia necesita dividirse, se crean sub-zonas con el mismo país + provincia pero nombre diferente. Requieren asignación manual en el contacto.

| Zona | País | Provincia | Comportamiento |
|------|------|-----------|----------------|
| Norte Buenos Aires | Argentina | Buenos Aires | Solo para clientes asignados manualmente |
| Sur Buenos Aires | Argentina | Buenos Aires | Solo para clientes asignados manualmente |

## Paso 2: Asignar zonas a contactos (solo para sub-zonas)

**Ir a: Contactos → Abrir contacto → Pestaña "Ventas y compras"**

El campo **"Zona de Comisión"** se filtra automáticamente por el país y provincia del contacto.

**Cuándo asignar manualmente:**
- Si el cliente debe pertenecer a una sub-zona específica (ej: "Norte Buenos Aires")

**Cuándo NO es necesario:**
- Si solo se usan zonas provinciales (el matcheo es automático)

### Cómo resuelve la zona el sistema

```
1. ¿El contacto tiene "Zona de Comisión" asignada?
   → SÍ: Usa esa zona
   → NO: Continúa...

2. ¿El contacto tiene provincia?
   → SÍ: Busca zona con esa provincia y país → la usa
   → NO: Sin zona
```

| Contacto | Provincia | Zona manual | Zona resuelta |
|----------|-----------|-------------|---------------|
| Acme SA | Buenos Aires | *(vacío)* | Buenos Aires (automático) |
| Ferretería López | Buenos Aires | Norte Buenos Aires | Norte Buenos Aires (manual) |
| Cliente Nuevo | Mendoza | *(vacío)* | *(sin zona)* — no existe zona Mendoza |

## Paso 3: Crear reglas de comisión

**Ir a: Facturación → Comisiones → Reglas de Comisión**

### Campos de una regla

| Campo | Obligatorio | Descripción |
|-------|:-----------:|-------------|
| Vendedor | Sí | El vendedor al que aplica |
| Cliente | No | Vacío = todos los clientes |
| País / Provincia / Zona | No | Filtro cascada: país filtra provincia, provincia filtra zona |
| Producto | No | Vacío = todos los productos |
| Categoría de Producto | No | Vacío = todas las categorías |
| Comisión (%) | Sí | Porcentaje sobre el neto sin IVA |

### Cómo cargar una regla

1. Click en **"Nuevo"**
2. Seleccionar **Vendedor** y **Comisión (%)**
3. Opcionalmente completar Cliente, Zona, Producto y/o Categoría para hacer la regla más específica
4. Para zona: primero seleccionar País → luego Provincia → luego Zona (se filtran en cascada)
5. Guardar

### Regla default (obligatoria por vendedor)

Siempre crear al menos una regla **sin cliente, sin zona, sin producto, sin categoría** para cada vendedor. Esta es la comisión base que aplica cuando ninguna otra regla más específica matchea.

### Columnas visibles en la lista de reglas

Vendedor | Cliente | País | Provincia | Zona | Producto | Categoría | Comisión (%)

---

# Bloque 4: Referencia técnica

## Arquitectura

```
┌─────────────────────────────┐
│      commission.zone         │  ← Zonas geográficas (provincia/sub-zona)
└──────────────┬──────────────┘
               │ resuelve zona del partner
               ▼
┌─────────────────────────────┐
│       res.partner            │  ← Campo commission_zone_id (override manual)
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  salesperson.commission.rule │  ← Reglas (% por vendedor/cliente/zona/producto/categoría)
└──────────────┬──────────────┘
               │ busca regla más específica (1 query, ORDER BY DESC)
               ▼
┌─────────────────────────────┐
│   salesperson.commission     │  ← Comisión calculada (50/50)
└──────────────┬──────────────┘
               │ vinculada a
               ▼
┌─────────────────────────────┐
│   account.move (herencia)    │  ← Factura/NC con smart button + triggers
└─────────────────────────────┘
```

## Código: `commission.zone`

```python
class CommissionZone(models.Model):
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
        """
        if partner.commission_zone_id:
            return partner.commission_zone_id
        if partner.state_id:
            zone = self.search([
                ('state_id', '=', partner.state_id.id),
                ('country_id', '=', partner.country_id.id),
            ], limit=1)
            if zone:
                return zone
        return self.browse()
```

## Código: `res.partner`

```python
class ResPartner(models.Model):
    _inherit = 'res.partner'

    commission_zone_id = fields.Many2one(
        'commission.zone', string='Zona de Comisión',
        help='Asignar manualmente para sub-zonas. '
             'Si está vacío, se resuelve automáticamente por provincia.')
```

Vista con filtro dinámico por país/provincia del contacto:

```xml
<field name="commission_zone_id"
       domain="[('country_id', '=', country_id), ('state_id', '=', state_id)]"/>
```

## Código: `salesperson.commission.rule`

```python
class SalespersonCommissionRule(models.Model):
    _name = 'salesperson.commission.rule'
    _description = 'Regla de Comisión de Vendedor'
    _order = 'salesperson_id, partner_id, zone_id, product_id, product_category_id'

    salesperson_id = fields.Many2one('res.users', string='Vendedor', required=True, index=True)
    partner_id = fields.Many2one('res.partner', string='Cliente')
    # Campos auxiliares stored para filtro cascada país → provincia → zona
    zone_country_id = fields.Many2one('res.country', string='País')
    zone_state_id = fields.Many2one('res.country.state', string='Provincia')
    zone_id = fields.Many2one('commission.zone', string='Zona')
    product_id = fields.Many2one('product.product', string='Producto')
    product_category_id = fields.Many2one('product.category', string='Categoría de Producto')
    commission_percentage = fields.Float(string='Comisión (%)', required=True, digits=(5, 2))
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('unique_rule',
         'UNIQUE(salesperson_id, partner_id, zone_id, product_id, product_category_id, company_id)',
         'Ya existe una regla para esta combinación.'),
    ]

    @api.onchange('zone_country_id')
    def _onchange_zone_country_id(self):
        self.zone_state_id = False
        self.zone_id = False

    @api.onchange('zone_state_id')
    def _onchange_zone_state_id(self):
        self.zone_id = False

    @api.onchange('zone_id')
    def _onchange_zone_id(self):
        if self.zone_id:
            self.zone_country_id = self.zone_id.country_id
            self.zone_state_id = self.zone_id.state_id

    @api.model
    def _get_commission_percentage(self, salesperson, partner, product, category, zone=None):
        """Una sola query ordenada por especificidad.

        Puntaje implícito: partner(+8) > zone(+4) > product(+2) > category(+1)
        ORDER BY ... DESC pone campos NOT NULL primero → más específica gana.
        """
        commercial_partner = partner.commercial_partner_id
        zone_id = zone.id if zone else False
        product_id = product.id if product else False

        domain = [
            ('salesperson_id', '=', salesperson.id),
            ('company_id', 'in', [self.env.company.id, False]),
            '|', ('partner_id', '=', commercial_partner.id), ('partner_id', '=', False),
            '|', ('zone_id', '=', zone_id), ('zone_id', '=', False),
            '|', ('product_id', '=', product_id), ('product_id', '=', False),
            '|', ('product_category_id', '=', category.id), ('product_category_id', '=', False),
        ]
        rule = self.search(
            domain,
            order='partner_id DESC, zone_id DESC, product_id DESC, product_category_id DESC',
            limit=1,
        )
        if rule:
            return rule, rule.commission_percentage
        return self.browse(), 0.0
```

## Código: `account.move`

```python
class AccountMove(models.Model):
    _inherit = 'account.move'

    commission_ids = fields.One2many('salesperson.commission', 'move_id', string='Comisiones')
    commission_count = fields.Integer(compute='_compute_commission_count')

    def _post(self, soft=True):
        """Trigger 1: Al confirmar factura/NC, genera comisiones."""
        posted = super()._post(soft=soft)
        for move in posted:
            if move.move_type in ('out_invoice', 'out_refund'):
                move._generate_commissions()
        return posted

    @api.depends('amount_residual', 'move_type', 'state', 'company_id')
    def _compute_payment_state(self):
        """Trigger 2: Al cobrar, devenga el 50% de cobro.

        Por qué override de _compute y NO de write():
        payment_state es stored computed field. Los stored computed se
        persisten vía _write() interno, que NO pasa por write() público.
        """
        super()._compute_payment_state()
        for move in self:
            if (move.move_type == 'out_invoice'
                    and move.payment_state in ('paid', 'in_payment')
                    and move.commission_ids):
                move.commission_ids.filtered(
                    lambda c: c.collection_status == 'pending'
                ).write({'collection_status': 'accrued'})

    def _generate_commissions(self):
        """Resuelve zona → busca regla por línea → agrupa por % → crea comisión 50/50."""
        self.ensure_one()
        if self.commission_ids:
            return

        salesperson = self.invoice_user_id
        if not salesperson:
            return

        partner = self.partner_id
        zone = self.env['commission.zone']._resolve_zone(partner)

        grouped = defaultdict(float)  # {(rule_id, %): sum(price_subtotal)}

        for line in self.invoice_line_ids:
            if line.display_type != 'product' or not line.product_id:
                continue
            product = line.product_id
            category = product.categ_id
            rule, percentage = self.env['salesperson.commission.rule'] \
                ._get_commission_percentage(salesperson, partner, product, category, zone)
            if percentage > 0:
                grouped[(rule.id, percentage)] += line.price_subtotal

        is_refund = self.move_type == 'out_refund'
        for (rule_id, percentage), base_amount in grouped.items():
            if is_refund:
                base_amount = -abs(base_amount)
            commission_amount = base_amount * percentage / 100.0

            self.env['salesperson.commission'].create({
                'move_id': self.id,
                'salesperson_id': salesperson.id,
                'rule_id': rule_id or False,
                'base_amount': base_amount,
                'commission_percentage': percentage,
                'commission_amount': commission_amount,
                'invoice_commission': commission_amount / 2.0,
                'collection_commission': commission_amount / 2.0,
                'invoice_status': 'accrued',
                'collection_status': 'accrued' if is_refund else 'pending',
            })
```

## Decisiones técnicas

### Por qué una sola query en vez de N búsquedas secuenciales

Con 5 dimensiones opcionales (cliente, zona, producto, categoría), las combinaciones posibles son 16. Hacer 16 búsquedas secuenciales es ineficiente. La implementación usa un solo `search()` con domain OR por campo y `ORDER BY ... DESC` que pone los campos NOT NULL primero. La regla más específica siempre queda primera. Una query en vez de dieciséis.

### Por qué `_compute_payment_state` y no `write()`

Los stored computed fields se persisten vía `_write()` interno, que NO pasa por `write()` público. Un override de `write()` nunca detectaría el cambio de `payment_state`.

### Por qué `price_subtotal` como base

El vendedor cobra sobre el valor del producto, no sobre los impuestos. `price_subtotal` es el neto sin IVA por línea.

### Por qué `commercial_partner_id` para buscar reglas

Un cliente puede tener múltiples contactos (envío, facturación). `commercial_partner_id` normaliza al partner comercial raíz, asegurando que la regla aplique sin importar qué contacto se use en la factura.

### Por qué campos auxiliares `zone_country_id` y `zone_state_id` stored en la regla

Son campos auxiliares para filtrar el dropdown de zona en cascada (país → provincia → zona). Se almacenan para que al reabrir una regla existente se muestren correctamente. Los onchange en cascada mantienen la consistencia: cambiar país limpia provincia y zona, cambiar provincia limpia zona, seleccionar zona autocompleta país y provincia.

## Seguridad

| Grupo | Zonas | Reglas | Comisiones |
|-------|-------|--------|------------|
| Gerente contable (`account.group_account_manager`) | CRUD completo | CRUD completo | CRUD completo |
| Facturación (`account.group_account_invoice`) | Solo lectura | Solo lectura | Solo lectura |

## Dependencias

```python
'depends': ['account', 'sale', 'product', 'contacts']
```

| Módulo | Razón |
|--------|-------|
| `account` | `account.move`, monedas, `payment_state`, conciliación |
| `sale` | `invoice_user_id` propagado desde `sale.order` |
| `product` | `product.product` y `product.category` para reglas |
| `contacts` | `res.partner` con `state_id`/`country_id` para zonas |

## Verificación

1. **Zonas**: Crear "Buenos Aires", "Norte Buenos Aires", "Córdoba"
2. **Sub-zona**: Asignar contacto de BA → Zona de Comisión = "Norte Buenos Aires"
3. **Regla default**: Vendedor solo → 2%
4. **Regla por zona**: Vendedor + zona "Norte Buenos Aires" → 5%
5. **Regla por producto**: Vendedor + producto "Taladro Bosch" → 3%
6. **Regla por categoría**: Vendedor + zona "Córdoba" + categoría "Herramientas" → 3.5%
7. **Regla por cliente**: Vendedor + cliente "Acme SA" → 6%
8. **Facturar con sub-zona**: Verificar que aplica 5% (zona)
9. **Facturar con zona automática**: Partner BA sin sub-zona → matchea zona provincial
10. **Prioridad cliente > zona**: Cliente específico (8 pts) gana sobre zona (4 pts)
11. **Prioridad producto > categoría**: Producto (2 pts) gana sobre categoría (1 pt)
12. **Factura mixta**: Dos productos con distintas reglas → dos registros de comisión
13. **Cobro**: Pago total → 50% cobro pasa a Devengado
14. **NC**: Comisión negativa, ambos 50% devengados al instante
15. **Pivot**: Agrupar por vendedor/mes → verificar totales
