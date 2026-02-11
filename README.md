# Sur Técnica - Comisiones de Vendedores (Odoo 17)

## Problema

El cálculo de comisiones de vendedores se hacía manualmente, generando errores y demoras. Se necesitaba un sistema automático que:
- Calcule comisiones al facturar y al cobrar (50/50)
- Soporte porcentajes variables por vendedor, cliente, **zona geográfica** y categoría de producto
- Revierta comisiones automáticamente con Notas de Crédito

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

### Flujo estándar de facturación/cobro en Odoo 17

```
Pedido de Venta (sale.order)
  → user_id = vendedor
  → Confirmar → Crear Factura
      → invoice_user_id = user_id (heredado)
      → _post() → state = 'posted', payment_state = 'not_paid'
      → Registrar Pago → Conciliación
          → _compute_payment_state() → payment_state = 'paid'
```

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

**Punto crítico**: los stored computed fields **NO pasan por `write()`**. Odoo los persiste directo a DB vía `_write()` interno. Esto significa que un override de `write()` **nunca detectaría** el cambio de `payment_state`. La forma correcta de interceptarlo es overrideando `_compute_payment_state`.

---

## Solución implementada

### Arquitectura: 4 modelos

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

---

### Modelo 0: `commission.zone`

Define zonas geográficas para las reglas de comisión. Dos niveles:

- **Zona provincial**: `state_id` seteado → matchea automáticamente por provincia del partner
- **Sub-zona**: misma provincia, zona más específica → requiere asignación manual vía `commission_zone_id` en el partner

#### Campos

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `name` | Char | Nombre (ej: "Buenos Aires", "Norte Buenos Aires") |
| `country_id` | Many2one(`res.country`) | País (required) |
| `state_id` | Many2one(`res.country.state`) | Provincia (vacío = todo el país) |
| `active` | Boolean | Activo (default True) |
| `company_id` | Many2one(`res.company`) | Compañía |

#### Lógica de resolución: `_resolve_zone(partner)`

```python
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

#### Ejemplo de zonas

| Zona | País | Provincia |
|------|------|-----------|
| Buenos Aires | Argentina | Buenos Aires |
| Norte Buenos Aires | Argentina | Buenos Aires |
| Sur Buenos Aires | Argentina | Buenos Aires |
| Córdoba | Argentina | Córdoba |
| Santa Fe | Argentina | Santa Fe |

#### Asignación de partners

- **"Acme SA"** (state_id = Buenos Aires, commission_zone_id = vacío) → **auto-matchea zona "Buenos Aires"**
- **"Ferretería López"** (state_id = Buenos Aires, commission_zone_id = "Norte Buenos Aires") → **usa sub-zona manual**
- **"Constructor Sur SRL"** (state_id = Buenos Aires, commission_zone_id = "Sur Buenos Aires") → **usa sub-zona manual**

### Extensión de `res.partner`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `commission_zone_id` | Many2one(`commission.zone`) | Zona de comisión (override manual) |

---

### Modelo 1: `salesperson.commission.rule`

Define los porcentajes de comisión. La búsqueda usa **puntaje por especificidad** (una sola query):

| Dimensión | Puntos |
|-----------|--------|
| `partner_id` presente | +4 |
| `zone_id` presente | +2 |
| `product_category_id` presente | +1 |

Orden resultante (de mayor a menor prioridad):

| Puntaje | Combinación |
|---------|-------------|
| 7 | vendedor + cliente + zona + categoría |
| 6 | vendedor + cliente + zona |
| 5 | vendedor + cliente + categoría |
| 4 | vendedor + cliente |
| 3 | vendedor + zona + categoría |
| 2 | vendedor + zona |
| 1 | vendedor + categoría |
| 0 | vendedor solo (default) |

#### Cómo configurar las reglas

Las reglas se cargan en **Facturación → Comisiones → Reglas de Comisión** (acceso solo gerentes contables).

**Regla sin cliente/zona/categoría = aplica a TODOS.** Es la comisión default del vendedor. Para diferenciar, se crean reglas adicionales más específicas que la overridean.

#### Ejemplo práctico con zonas

| # | Vendedor | Cliente | Zona | Categoría | % |
|---|----------|---------|------|-----------|---|
| R1 | Juan | *(vacío)* | *(vacío)* | *(vacío)* | 2% |
| R2 | Juan | *(vacío)* | Buenos Aires | *(vacío)* | 4% |
| R3 | Juan | *(vacío)* | Norte Buenos Aires | *(vacío)* | 5% |
| R4 | Juan | *(vacío)* | Córdoba | Herramientas | 3% |
| R5 | Juan | Acme SA | *(vacío)* | *(vacío)* | 6% |

**Factura de "Ferretería López" (Norte BA)** → aplica R3 = 5% (zona Norte BA, puntaje 2)
**Factura de "Acme SA" (BA)** → aplica R5 = 6% (cliente específico, puntaje 4 > zona puntaje 2)
**Factura de cliente en Córdoba con Herramientas** → aplica R4 = 3% (zona + categoría, puntaje 3)
**Factura de cliente en Santa Fe** → aplica R1 = 2% (default, no hay zona Santa Fe con regla)

#### Campos

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `salesperson_id` | Many2one(`res.users`) | Vendedor (required) |
| `partner_id` | Many2one(`res.partner`) | Cliente específico (vacío = todos) |
| `zone_id` | Many2one(`commission.zone`) | Zona geográfica (vacío = todas) |
| `product_category_id` | Many2one(`product.category`) | Categoría (vacío = todas) |
| `commission_percentage` | Float | Porcentaje de comisión |
| `active` | Boolean | Activo (default True) |
| `company_id` | Many2one(`res.company`) | Compañía |

#### Método principal: `_get_commission_percentage(salesperson, partner, category, zone)`

```python
@api.model
def _get_commission_percentage(self, salesperson, partner, category, zone=None):
    """Busca la regla más específica con una sola query ordenada por puntaje.

    Patrón: Single-query specificity lookup — en vez de N búsquedas
    secuenciales, usa domain con OR por campo y ordena por campos NOT NULL.
    La regla más específica queda primera.
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

---

### Modelo 2: `salesperson.commission`

Un registro por cada combinación (factura, porcentaje). Si una factura tiene líneas con distintos porcentajes, se crean múltiples registros.

#### Campos

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `move_id` | Many2one(`account.move`) | Factura origen |
| `salesperson_id` | Many2one(`res.users`) | Vendedor |
| `rule_id` | Many2one(`salesperson.commission.rule`) | Regla aplicada |
| `partner_id` | Many2one (related) | Cliente |
| `base_amount` | Monetary | Neto sin IVA (suma de `price_subtotal`) |
| `commission_percentage` | Float | % aplicado |
| `commission_amount` | Monetary | Comisión total = base × % |
| `invoice_commission` | Monetary | 50% por facturación |
| `collection_commission` | Monetary | 50% por cobro |
| `invoice_status` | Selection | `pending` / `accrued` |
| `collection_status` | Selection | `pending` / `accrued` |
| `currency_id` | Many2one (related) | Moneda de la factura |
| `date` | Date (related) | Fecha factura |
| `move_type` | Selection (related) | Tipo de movimiento |

---

### Modelo 3: `account.move` (herencia)

Extiende la factura con comisiones y dos triggers automáticos.

#### Campos agregados

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `commission_ids` | One2many(`salesperson.commission`) | Comisiones de esta factura |
| `commission_count` | Integer (computed) | Cantidad (para smart button) |

#### Override 1: `_post()` — Trigger de facturación

```python
def _post(self, soft=True):
    """Al confirmar factura/NC, calcula comisiones automáticamente."""
    posted = super()._post(soft=soft)
    for move in posted:
        if move.move_type in ('out_invoice', 'out_refund'):
            move._generate_commissions()
    return posted
```

#### Override 2: `_compute_payment_state()` — Trigger de cobro

```python
@api.depends('amount_residual', 'move_type', 'state', 'company_id')
def _compute_payment_state(self):
    """Detecta cuando la factura pasa a 'paid' o 'in_payment'."""
    super()._compute_payment_state()
    for move in self:
        if (move.move_type == 'out_invoice'
                and move.payment_state in ('paid', 'in_payment')
                and move.commission_ids):
            move.commission_ids.filtered(
                lambda c: c.collection_status == 'pending'
            ).write({'collection_status': 'accrued'})
```

#### Método: `_generate_commissions()` — Cálculo con resolución de zona

```python
def _generate_commissions(self):
    """Genera registros de comisión agrupados por regla/porcentaje.

    Algoritmo:
    1. Resuelve la zona del partner (manual → automática por provincia)
    2. Para cada línea de producto (display_type == 'product')
    3. Busca la regla más específica para vendedor/cliente/zona/categoría
    4. Agrupa montos (price_subtotal) por (rule_id, percentage)
    5. Crea un registro de comisión por grupo con split 50/50
    """
    self.ensure_one()
    if self.commission_ids:
        return

    salesperson = self.invoice_user_id
    if not salesperson:
        return

    partner = self.partner_id
    RuleModel = self.env['salesperson.commission.rule']
    ZoneModel = self.env['commission.zone']

    # Resuelve zona una sola vez por factura
    zone = ZoneModel._resolve_zone(partner)

    grouped = defaultdict(float)

    for line in self.invoice_line_ids:
        if line.display_type != 'product':
            continue
        if not line.product_id:
            continue

        category = line.product_id.categ_id
        rule, percentage = RuleModel._get_commission_percentage(
            salesperson, partner, category, zone)

        if percentage <= 0:
            continue

        grouped[(rule.id, percentage)] += line.price_subtotal

    is_refund = self.move_type == 'out_refund'
    CommissionModel = self.env['salesperson.commission']

    for (rule_id, percentage), base_amount in grouped.items():
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
            'invoice_status': 'accrued',
            'collection_status': 'accrued' if is_refund else 'pending',
        })
```

---

## Flujo completo

### Factura de cliente

```
Factura confirmada (_post)
  │
  ├── Resuelve zona del partner:
  │     └── commission_zone_id manual → o → búsqueda por state_id
  │
  ├── Por cada línea de producto:
  │     └── Busca regla más específica (vendedor/cliente/zona/categoría) → obtiene %
  │
  ├── Agrupa líneas por (regla, %)
  │
  └── Crea registro(s) de comisión:
        ├── commission_amount = base × %
        ├── invoice_commission = 50% → invoice_status = 'accrued' ✓
        └── collection_commission = 50% → collection_status = 'pending' ⏳

Pago registrado → Conciliación → _compute_payment_state()
  │
  └── payment_state = 'paid'
        └── collection_status = 'accrued' ✓
```

### Nota de Crédito

```
NC confirmada (_post)
  │
  └── Crea comisión NEGATIVA:
        ├── base_amount = -|subtotal|
        ├── commission_amount = negativo
        ├── invoice_status = 'accrued' ✓ (inmediato)
        └── collection_status = 'accrued' ✓ (inmediato)
```

### Ejemplo numérico

Factura FA-A 0001-00000020 por $100.000 + IVA, vendedor Juan (comisión 5%):

| Concepto | Valor |
|----------|-------|
| Base imponible | $100.000,00 |
| Comisión total (5%) | $5.000,00 |
| 50% facturación (devengado al confirmar) | $2.500,00 |
| 50% cobro (devengado al cobrar) | $2.500,00 |

Si después se emite NC por $20.000:

| Concepto | Valor |
|----------|-------|
| Base imponible | -$20.000,00 |
| Comisión total (5%) | -$1.000,00 |
| 50% facturación | -$500,00 (devengado inmediato) |
| 50% cobro | -$500,00 (devengado inmediato) |

**Comisión neta del vendedor**: $5.000 - $1.000 = **$4.000**

---

## Seguridad

| Grupo | Zonas | Reglas | Comisiones |
|-------|-------|--------|------------|
| Gerente contable (`account.group_account_manager`) | CRUD completo | CRUD completo | CRUD completo |
| Facturación (`account.group_account_invoice`) | Solo lectura | Solo lectura | Solo lectura |

---

## Vistas

| Vista | Modelo | Descripción |
|-------|--------|-------------|
| Tree + Form + Search | `commission.zone` | ABM de zonas geográficas |
| Tree + Form + Search | `salesperson.commission.rule` | ABM de reglas |
| Tree + Form + Search | `salesperson.commission` | Listado de comisiones |
| Pivot | `salesperson.commission` | Tabla cruzada vendedor × mes |
| Graph | `salesperson.commission` | Gráfico de barras por vendedor |
| Smart button | `account.move` (herencia) | Botón "Comisiones" en factura |

### Menú

```
Facturación
  └── Comisiones
        ├── Comisiones (listado)
        ├── Reglas de Comisión (solo gerentes)
        └── Zonas (solo gerentes)
```

---

## Decisiones técnicas

### Por qué una sola query en vez de N búsquedas secuenciales

El método anterior hacía 4 búsquedas (prioridad 1 → 4). Con zonas serían 8. La nueva implementación usa un solo `search()` con domain OR y `ORDER BY ... DESC` que ordena los campos NOT NULL primero. El resultado: la regla más específica siempre queda primera. Más eficiente y escalable a nuevas dimensiones.

### Por qué `_compute_payment_state` y no `write()`

Los **stored computed fields** en Odoo 17 se recomputan cuando cambian sus dependencias (`amount_residual`, `state`, etc.) y se persisten a DB vía el método interno `_write()`, que **no pasa por el `write()` público**. Un override de `write()` nunca detectaría el cambio de `payment_state`.

### Por qué `payment_state` y no `amount_residual == 0`

En operaciones multi-moneda, diferencias de tipo de cambio pueden hacer que `amount_residual` no llegue exactamente a 0. El campo `payment_state` considera la reconciliación contable completa y es más confiable.

### Por qué `price_subtotal` como base

`price_subtotal` es el neto sin IVA por línea. Es el estándar para comisiones comerciales — el vendedor cobra sobre el valor del producto, no sobre los impuestos.

### Por qué `commercial_partner_id` para buscar reglas

En Odoo, un cliente puede tener múltiples contactos (direcciones de envío, facturación). `commercial_partner_id` normaliza al partner comercial raíz, asegurando que la regla aplique sin importar qué contacto se use en la factura.

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

1. **Zonas**: Crear zonas "Buenos Aires", "Norte Buenos Aires", "Córdoba"
2. **Partners**: Asignar partner a sub-zona "Norte Buenos Aires" vía `commission_zone_id`
3. **Reglas**: Crear regla vendedor + zona "Norte Buenos Aires" → 5%
4. **Facturación con zona**: Facturar al partner → verificar que aplica 5%
5. **Zona automática**: Facturar a partner en Buenos Aires sin sub-zona → verificar matcheo provincial
6. **Prioridad cliente > zona**: Facturar a partner con regla de cliente específica → verificar que cliente gana sobre zona
7. **Cobro**: Registrar pago total → verificar `collection_status = accrued`
8. **NC**: Crear NC → verificar comisión negativa con ambos status `accrued`
9. **Reportes**: Pivot por vendedor/mes → verificar totales
