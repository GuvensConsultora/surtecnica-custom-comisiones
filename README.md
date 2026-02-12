# Sur Técnica - Comisiones de Vendedores (Odoo 17)

## Problema

El cálculo de comisiones de vendedores se hacía manualmente, generando errores y demoras. Se necesitaba un sistema automático que:
- Calcule comisiones al facturar y al cobrar (50/50)
- Soporte porcentajes variables por vendedor, cliente, **zona geográfica** y categoría de producto
- Revierta comisiones automáticamente con Notas de Crédito

---

## Guía de parametrización paso a paso

### Paso 1: Crear zonas geográficas

**Ir a: Facturación → Comisiones → Zonas**

Las zonas representan regiones geográficas donde operan los vendedores. Hay dos tipos:

#### Zonas provinciales (matcheo automático)

Se crean con país + provincia. Cualquier cliente que tenga esa provincia en su ficha se asocia automáticamente a la zona, sin intervención manual.

| Zona | País | Provincia | Comportamiento |
|------|------|-----------|----------------|
| Buenos Aires | Argentina | Buenos Aires | Auto-matchea todos los clientes con provincia = Buenos Aires |
| Córdoba | Argentina | Córdoba | Auto-matchea todos los clientes con provincia = Córdoba |
| Santa Fe | Argentina | Santa Fe | Auto-matchea todos los clientes con provincia = Santa Fe |

#### Sub-zonas (asignación manual)

Cuando una provincia necesita dividirse en áreas comerciales distintas, se crean sub-zonas con el mismo país + provincia pero nombre diferente. Estas **requieren asignación manual** en el contacto.

| Zona | País | Provincia | Comportamiento |
|------|------|-----------|----------------|
| Norte Buenos Aires | Argentina | Buenos Aires | Solo para clientes asignados manualmente |
| Sur Buenos Aires | Argentina | Buenos Aires | Solo para clientes asignados manualmente |
| Centro Córdoba | Argentina | Córdoba | Solo para clientes asignados manualmente |

### Paso 2: Asignar zonas a contactos (solo para sub-zonas)

**Ir a: Contactos → Abrir un contacto → Pestaña "Ventas y compras"**

El campo **"Zona de Comisión"** aparece en la sección de Ventas. Este campo se filtra automáticamente según el país y la provincia del contacto: si el contacto tiene Argentina / Buenos Aires, solo muestra las zonas de Buenos Aires.

**Cuándo asignar manualmente:**
- Si el cliente debe pertenecer a una sub-zona específica (ej: "Norte Buenos Aires")
- Si el matcheo automático por provincia no es suficiente

**Cuándo NO es necesario:**
- Si solo se usan zonas provinciales (el matcheo es automático por provincia)
- Si el cliente no tiene reglas diferenciadas por zona

#### Lógica de resolución de zona

Cuando se confirma una factura, el sistema determina la zona del cliente así:

```
1. ¿El contacto tiene "Zona de Comisión" asignada manualmente?
   → SÍ: Usa esa zona (sub-zona manual)
   → NO: Continúa...

2. ¿El contacto tiene provincia (state_id)?
   → SÍ: Busca una zona que tenga esa provincia y país
         → Encontró: Usa esa zona (matcheo automático provincial)
         → No encontró: Sin zona
   → NO: Sin zona
```

**Ejemplo concreto:**

| Contacto | Provincia | Zona manual | Zona resuelta | Por qué |
|----------|-----------|-------------|---------------|---------|
| Acme SA | Buenos Aires | *(vacío)* | Buenos Aires | Auto-matcheo por provincia |
| Ferretería López | Buenos Aires | Norte Buenos Aires | Norte Buenos Aires | Override manual |
| Constructor Sur SRL | Buenos Aires | Sur Buenos Aires | Sur Buenos Aires | Override manual |
| Metalúrgica Centro | Córdoba | *(vacío)* | Córdoba | Auto-matcheo por provincia |
| Cliente Nuevo | Mendoza | *(vacío)* | *(sin zona)* | No existe zona para Mendoza |

### Paso 3: Crear reglas de comisión

**Ir a: Facturación → Comisiones → Reglas de Comisión**

Cada regla define un porcentaje de comisión para un vendedor. Los campos opcionales (cliente, zona, categoría) refinan cuándo aplica la regla. **Cuantos más campos completos, más específica es la regla y mayor prioridad tiene.**

#### Campos de una regla

| Campo | Obligatorio | Descripción |
|-------|:-----------:|-------------|
| Vendedor | Sí | El vendedor al que aplica |
| Cliente | No | Dejar vacío = aplica a todos los clientes |
| Zona | No | Dejar vacío = aplica a todas las zonas |
| Categoría de Producto | No | Dejar vacío = aplica a todas las categorías |
| Comisión (%) | Sí | Porcentaje sobre el neto sin IVA |

#### Sistema de prioridad (la regla más específica gana)

Cada campo opcional que se completa suma puntos de prioridad:

| Campo completado | Puntos |
|------------------|:------:|
| Cliente | +4 |
| Zona | +2 |
| Categoría de producto | +1 |

La regla con mayor puntaje es la que se aplica. Tabla de prioridades:

| Puntaje | Regla tiene... | Ejemplo |
|:-------:|----------------|---------|
| 7 | Cliente + Zona + Categoría | Acme SA + Buenos Aires + Herramientas → 10% |
| 6 | Cliente + Zona | Acme SA + Buenos Aires → 8% |
| 5 | Cliente + Categoría | Acme SA + Herramientas → 7% |
| 4 | Cliente | Acme SA → 6% |
| 3 | Zona + Categoría | Córdoba + Herramientas → 3.5% |
| 2 | Zona | Buenos Aires → 4% |
| 1 | Categoría | Herramientas → 3% |
| 0 | *(todo vacío)* | Default del vendedor → 2% |

#### Ejemplo completo de parametrización

**Vendedor: Juan Pérez** — Configuramos 6 reglas:

| # | Cliente | Zona | Categoría | % | Uso |
|---|---------|------|-----------|:-:|-----|
| R1 | *(vacío)* | *(vacío)* | *(vacío)* | 2% | Default para todas las ventas de Juan |
| R2 | *(vacío)* | Buenos Aires | *(vacío)* | 4% | Clientes de Buenos Aires pagan más |
| R3 | *(vacío)* | Norte Buenos Aires | *(vacío)* | 5% | Sub-zona Norte BA es premium |
| R4 | *(vacío)* | Córdoba | Herramientas | 3.5% | Herramientas en Córdoba tiene margen especial |
| R5 | Acme SA | *(vacío)* | *(vacío)* | 6% | Acme SA es cliente VIP |
| R6 | Acme SA | Buenos Aires | Herramientas | 10% | Máxima comisión: VIP + BA + Herramientas |

**Resultados al facturar:**

| Factura para... | Zona resuelta | Categoría | Regla aplicada | % | Razón |
|-----------------|---------------|-----------|:--------------:|:-:|-------|
| López SRL (Mendoza) | *(sin zona)* | Insumos | R1 | 2% | No matchea zona ni categoría → default |
| López SRL (Mendoza) | *(sin zona)* | Herramientas | R1 | 2% | No hay regla solo-categoría de Herramientas sin zona |
| Distribuidora BA (Bs.As.) | Buenos Aires | Insumos | R2 | 4% | Matchea zona Buenos Aires |
| Ferretería Norte (Bs.As.) | Norte Buenos Aires | Insumos | R3 | 5% | Sub-zona Norte BA (asignada manualmente) |
| Metalúrgica Cba (Córdoba) | Córdoba | Herramientas | R4 | 3.5% | Zona Córdoba + categoría Herramientas |
| Metalúrgica Cba (Córdoba) | Córdoba | Insumos | R1 | 2% | Zona Córdoba sin regla para Insumos → default |
| Acme SA (Bs.As.) | Buenos Aires | Insumos | R5 | 6% | Cliente específico (puntaje 4) > zona (puntaje 2) |
| Acme SA (Bs.As.) | Buenos Aires | Herramientas | R6 | 10% | Cliente + zona + categoría (puntaje 7) |

#### Factura mixta (varias categorías)

Si una factura tiene líneas de distintas categorías, cada línea busca su propia regla. Se generan registros de comisión agrupados por porcentaje.

**Factura de Acme SA con 3 líneas:**

| Línea | Producto | Categoría | Subtotal sin IVA | Regla | % |
|-------|----------|-----------|:----------------:|:-----:|:-:|
| 1 | Taladro Bosch | Herramientas | $50.000 | R6 | 10% |
| 2 | Tornillos x1000 | Insumos | $10.000 | R5 | 6% |
| 3 | Guantes | Insumos | $5.000 | R5 | 6% |

**Registros de comisión generados (agrupados por %):**

| Regla | Base | % | Comisión total | 50% Facturación | 50% Cobro |
|:-----:|:----:|:-:|:--------------:|:---------------:|:---------:|
| R6 | $50.000 | 10% | $5.000 | $2.500 (devengado) | $2.500 (pendiente) |
| R5 | $15.000 | 6% | $900 | $450 (devengado) | $450 (pendiente) |
| **Total** | **$65.000** | | **$5.900** | **$2.950** | **$2.950** |

---

## Cómo funciona el cálculo

### Trigger 1: Al confirmar factura (50% facturación)

Cuando se confirma una factura o nota de crédito de cliente:

1. El sistema identifica al **vendedor** (`invoice_user_id`)
2. **Resuelve la zona** del cliente (manual → automática por provincia → sin zona)
3. Por cada **línea de producto**:
   - Identifica la **categoría** del producto
   - Busca la **regla más específica** que matchee vendedor + cliente + zona + categoría
   - Obtiene el **porcentaje**
4. **Agrupa** las líneas que comparten el mismo porcentaje
5. Calcula la comisión: `base_neta_sin_iva × porcentaje / 100`
6. Divide 50/50:
   - **50% facturación** → se devenga inmediatamente (estado: `Devengado`)
   - **50% cobro** → queda pendiente (estado: `Pendiente`)

### Trigger 2: Al cobrar la factura (50% cobro)

Cuando la factura pasa a estado de pago `paid` o `in_payment` (pago total registrado):

- El **50% de cobro** pendiente pasa a `Devengado`
- La comisión queda 100% devengada

### Notas de Crédito

Las NC generan comisión **negativa** (restan). Ambos 50% se devengan al instante porque la NC no tiene cobro pendiente.

### Ejemplo numérico completo

**Paso 1:** Factura FA-A 0001-00000020 a Acme SA por $100.000 + IVA (vendedor Juan, comisión 6%):

| Momento | Evento | Comisión total | 50% Facturación | 50% Cobro |
|---------|--------|:--------------:|:---------------:|:---------:|
| Confirmar factura | `_post()` | $6.000 | $3.000 ✓ Devengado | $3.000 ⏳ Pendiente |
| Registrar pago | `_compute_payment_state()` | $6.000 | $3.000 ✓ Devengado | $3.000 ✓ Devengado |

**Paso 2:** NC por $20.000 (misma regla 6%):

| Momento | Evento | Comisión total | 50% Facturación | 50% Cobro |
|---------|--------|:--------------:|:---------------:|:---------:|
| Confirmar NC | `_post()` | -$1.200 | -$600 ✓ Devengado | -$600 ✓ Devengado |

**Resultado neto de Juan:** $6.000 - $1.200 = **$4.800**

---

## Reportes

### Menú de acceso

```
Facturación
  └── Comisiones
        ├── Comisiones          ← Listado, pivot, gráfico
        ├── Reglas de Comisión  ← Solo gerentes contables
        └── Zonas               ← Solo gerentes contables
```

### Vista de lista (Comisiones)

Muestra todas las comisiones generadas con columnas sumables:

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

**Filtros disponibles:**
- Facturas / Notas de Crédito
- Facturación Pendiente / Cobro Pendiente

**Agrupar por:** Vendedor, Cliente, Fecha (mes)

### Vista pivot (tabla dinámica)

Cruza vendedores en filas con meses en columnas. Ideal para reportes mensuales de liquidación:

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
    50% Facturación       │    $1.600    │     $2.050     │   $3.650
    50% Cobro             │    $1.600    │     $2.050     │   $3.650
    Base                  │   $95.000    │   $120.000     │ $215.000
──────────────────────────┼──────────────┼────────────────┼───────────
  TOTAL                   │   $11.700    │     $9.900     │  $21.600
```

Se puede personalizar arrastrando campos a filas/columnas/medidas. Ejemplos:
- **Filas:** Vendedor → Cliente (sub-agrupamiento)
- **Columnas:** Fecha por mes, por trimestre o por año
- **Medidas:** Comisión Total, Base, 50% Facturación, 50% Cobro

### Vista gráfico (barras)

Gráfico de barras con el total de comisiones por vendedor. Útil para comparar rendimiento visual rápido.

```
  Comisión Total por Vendedor

  Juan Pérez    ████████████████████████████  $14.300
  María García  ██████████████████           $7.300
  Pedro López   ████████████                 $5.100
```

### Smart button en factura

Cada factura muestra un botón **"Comisiones"** (icono $) que lleva directo a los registros de comisión de esa factura. Solo visible si la factura tiene comisiones generadas.

---

## Cómo funciona Odoo 17 (sin este módulo)

Odoo 17 asigna un vendedor a cada factura vía `invoice_user_id` (heredado de `sale.order.user_id`), pero **no calcula comisiones**. Los campos estándar que aprovechamos:

| Campo | Modelo | Uso |
|-------|--------|-----|
| `invoice_user_id` | `account.move` | Vendedor asignado a la factura |
| `payment_state` | `account.move` | Estado de pago (`not_paid`, `paid`, `in_payment`) |
| `price_subtotal` | `account.move.line` | Neto sin IVA por línea |
| `display_type` | `account.move.line` | `'product'` = línea de producto |
| `commercial_partner_id` | `res.partner` | Partner comercial (agrupa contactos hijos) |
| `categ_id` | `product.product` | Categoría del producto |
| `state_id` | `res.partner` | Provincia del partner |
| `country_id` | `res.partner` | País del partner |

### Detalle técnico: `payment_state` es un stored computed field

```python
# Odoo 17 core: account/models/account_move.py
payment_state = fields.Selection(
    selection=PAYMENT_STATE_SELECTION,
    compute='_compute_payment_state', store=True,
)

@api.depends('amount_residual', 'move_type', 'state', 'company_id')
def _compute_payment_state(self):
    # Analiza reconciliación de apuntes contables
    # Determina: not_paid | partial | in_payment | paid | reversed
```

**Punto crítico**: los stored computed fields **NO pasan por `write()`**. Odoo los persiste directo a DB vía `_write()` interno. La forma correcta de interceptar el cambio de `payment_state` es overrideando `_compute_payment_state`.

---

## Arquitectura técnica

### 4 modelos

```
┌─────────────────────────────┐
│      commission.zone         │  ← Zonas geográficas (provincia/sub-zona)
└──────────────┬──────────────┘
               │ resuelve zona del partner
               ▼
┌─────────────────────────────┐
│  salesperson.commission.rule │  ← Reglas (% por vendedor/cliente/zona/categoría)
└──────────────┬──────────────┘
               │ busca regla más específica
               ▼
┌─────────────────────────────┐
│   salesperson.commission     │  ← Comisión calculada (50/50)
└──────────────┬──────────────┘
               │ vinculada a
               ▼
┌─────────────────────────────┐
│   account.move (herencia)    │  ← Factura/NC con smart button
└─────────────────────────────┘
```

### Código: `commission.zone` — Modelo de zonas

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

### Código: `res.partner` — Campo zona en contacto

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

### Código: `salesperson.commission.rule` — Reglas con búsqueda por especificidad

```python
class SalespersonCommissionRule(models.Model):
    _name = 'salesperson.commission.rule'

    salesperson_id = fields.Many2one('res.users', required=True, index=True)
    partner_id = fields.Many2one('res.partner')
    zone_id = fields.Many2one('commission.zone')
    product_category_id = fields.Many2one('product.category')
    commission_percentage = fields.Float(digits=(5, 2))
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('unique_rule',
         'UNIQUE(salesperson_id, partner_id, zone_id, product_category_id, company_id)',
         'Ya existe una regla para esta combinación.'),
    ]

    @api.model
    def _get_commission_percentage(self, salesperson, partner, category, zone=None):
        """Una sola query ordenada por especificidad.

        ORDER BY partner_id DESC, zone_id DESC, product_category_id DESC
        pone los campos NOT NULL primero → la regla más específica queda primera.
        """
        commercial_partner = partner.commercial_partner_id
        zone_id = zone.id if zone else False

        domain = [
            ('salesperson_id', '=', salesperson.id),
            ('company_id', 'in', [self.env.company.id, False]),
            '|', ('partner_id', '=', commercial_partner.id), ('partner_id', '=', False),
            '|', ('zone_id', '=', zone_id), ('zone_id', '=', False),
            '|', ('product_category_id', '=', category.id), ('product_category_id', '=', False),
        ]
        rule = self.search(
            domain,
            order='partner_id DESC, zone_id DESC, product_category_id DESC',
            limit=1,
        )
        if rule:
            return rule, rule.commission_percentage
        return self.browse(), 0.0
```

### Código: `account.move` — Triggers de facturación y cobro

```python
class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        """Trigger 1: Al confirmar factura/NC, genera comisiones."""
        posted = super()._post(soft=soft)
        for move in posted:
            if move.move_type in ('out_invoice', 'out_refund'):
                move._generate_commissions()
        return posted

    @api.depends('amount_residual', 'move_type', 'state', 'company_id')
    def _compute_payment_state(self):
        """Trigger 2: Al cobrar, devenga el 50% de cobro."""
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
            category = line.product_id.categ_id
            rule, percentage = self.env['salesperson.commission.rule'] \
                ._get_commission_percentage(salesperson, partner, category, zone)
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

---

## Seguridad

| Grupo | Zonas | Reglas | Comisiones |
|-------|-------|--------|------------|
| Gerente contable (`account.group_account_manager`) | CRUD completo | CRUD completo | CRUD completo |
| Facturación (`account.group_account_invoice`) | Solo lectura | Solo lectura | Solo lectura |

---

## Decisiones técnicas

### Por qué una sola query en vez de N búsquedas secuenciales

El método anterior hacía 4 búsquedas (prioridad 1 → 4). Con zonas serían 8. La nueva implementación usa un solo `search()` con domain OR y `ORDER BY ... DESC` que ordena los campos NOT NULL primero. La regla más específica siempre queda primera. Una query en vez de ocho.

### Por qué `_compute_payment_state` y no `write()`

Los stored computed fields se persisten vía `_write()` interno, que NO pasa por `write()` público. Un override de `write()` nunca detectaría el cambio de `payment_state`.

### Por qué `price_subtotal` como base

El vendedor cobra sobre el valor del producto, no sobre los impuestos. `price_subtotal` es el neto sin IVA por línea.

### Por qué `commercial_partner_id` para buscar reglas

Un cliente puede tener múltiples contactos (envío, facturación). `commercial_partner_id` normaliza al partner comercial raíz, asegurando que la regla aplique sin importar qué contacto se use en la factura.

---

## Dependencias

```python
'depends': ['account', 'sale', 'product', 'contacts']
```

| Módulo | Razón |
|--------|-------|
| `account` | `account.move`, monedas, `payment_state`, conciliación |
| `sale` | `invoice_user_id` propagado desde `sale.order` |
| `product` | `product.category` para reglas por categoría |
| `contacts` | `res.partner` con `state_id`/`country_id` para zonas |

---

## Verificación

1. **Crear zonas**: "Buenos Aires" (provincia BA), "Norte Buenos Aires" (provincia BA), "Córdoba" (provincia Cba)
2. **Asignar sub-zona**: Abrir un contacto de BA → Ventas y compras → Zona de Comisión = "Norte Buenos Aires"
3. **Crear reglas**: Vendedor + zona "Norte Buenos Aires" → 5%, Vendedor solo → 2%
4. **Facturar al contacto con sub-zona**: Verificar que aplica 5%
5. **Facturar a contacto de BA sin sub-zona**: Verificar matcheo automático zona "Buenos Aires"
6. **Facturar a contacto con regla de cliente**: Verificar que cliente (puntaje 4) gana sobre zona (puntaje 2)
7. **Factura mixta**: Dos categorías con distintas reglas → verificar dos registros de comisión
8. **Registrar pago total**: Verificar que 50% cobro pasa a `Devengado`
9. **Emitir NC**: Verificar comisión negativa con ambos 50% devengados
10. **Pivot**: Agrupar por vendedor y mes → verificar totales
