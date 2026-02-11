# Sur Técnica - Comisiones de Vendedores (Odoo 17)

## Problema

El cálculo de comisiones de vendedores se hacía manualmente, generando errores y demoras. Se necesitaba un sistema automático que:
- Calcule comisiones al facturar y al cobrar (50/50)
- Soporte porcentajes variables por vendedor, cliente y categoría de producto
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

### Arquitectura: 3 modelos

```
┌─────────────────────────────┐
│  salesperson.commission.rule │  ← Reglas (% por vendedor/cliente/categoría)
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

### Modelo 1: `salesperson.commission.rule`

Define los porcentajes de comisión. La búsqueda usa **prioridad por especificidad** (la regla más precisa gana):

| Prioridad | Combinación | Ejemplo |
|:---------:|-------------|---------|
| 1 (max) | Vendedor + Cliente + Categoría | Juan → Acme SA → Herramientas: 8% |
| 2 | Vendedor + Cliente | Juan → Acme SA: 5% |
| 3 | Vendedor + Categoría | Juan → Herramientas: 3% |
| 4 (default) | Vendedor solo | Juan → todos: 2% |

#### Cómo configurar las reglas

Las reglas se cargan en **Facturación → Comisiones → Reglas de Comisión** (acceso solo gerentes contables).

**Regla sin cliente = aplica a TODOS los clientes por igual.** Es la comisión default del vendedor. Para diferenciar por cliente o categoría, se crean reglas adicionales más específicas que la overridean.

#### Ejemplo práctico: Vendedor "Juan Pérez"

Supongamos que configuramos estas 4 reglas para Juan:

| # | Vendedor | Cliente | Categoría | % | Uso |
|---|----------|---------|-----------|---|-----|
| R1 | Juan Pérez | *(vacío)* | *(vacío)* | 2% | Default para todos los clientes y productos |
| R2 | Juan Pérez | Acme SA | *(vacío)* | 5% | Acme SA paga más comisión por ser VIP |
| R3 | Juan Pérez | *(vacío)* | Herramientas | 3% | Herramientas tiene mayor margen |
| R4 | Juan Pérez | Acme SA | Herramientas | 8% | Acme SA + Herramientas = máxima comisión |

**Escenario 1: Factura a "López SRL" por productos de categoría "Insumos"**
- No hay regla para López SRL ni para Insumos
- Aplica **R1** (default) → **2%**

**Escenario 2: Factura a "Acme SA" por productos de categoría "Insumos"**
- Existe regla para Acme SA (R2), no hay regla para Insumos
- Aplica **R2** (vendedor + cliente) → **5%**

**Escenario 3: Factura a "López SRL" por productos de categoría "Herramientas"**
- No hay regla para López SRL, pero sí para Herramientas (R3)
- Aplica **R3** (vendedor + categoría) → **3%**

**Escenario 4: Factura a "Acme SA" por productos de categoría "Herramientas"**
- Existe regla exacta para Acme SA + Herramientas (R4)
- Aplica **R4** (vendedor + cliente + categoría) → **8%**

**Escenario 5: Factura mixta a "Acme SA" con 3 líneas**

| Línea | Producto | Categoría | Subtotal | Regla | % |
|-------|----------|-----------|----------|-------|---|
| 1 | Taladro | Herramientas | $50.000 | R4 | 8% |
| 2 | Tornillos | Insumos | $10.000 | R2 | 5% |
| 3 | Guantes | Insumos | $5.000 | R2 | 5% |

Se crean **2 registros de comisión** (agrupados por porcentaje):

| Regla | Base | % | Comisión | 50% Factura | 50% Cobro |
|-------|------|---|----------|-------------|-----------|
| R4 (Herramientas) | $50.000 | 8% | $4.000 | $2.000 | $2.000 |
| R2 (Acme SA) | $15.000 | 5% | $750 | $375 | $375 |
| **Total** | **$65.000** | | **$4.750** | **$2.375** | **$2.375** |

> **Tip:** Si solo necesitás una comisión fija para un vendedor, basta con crear una única regla sin cliente ni categoría. Esa regla aplica a todas sus ventas.

#### Campos

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `salesperson_id` | Many2one(`res.users`) | Vendedor (required) |
| `partner_id` | Many2one(`res.partner`) | Cliente específico (vacío = todos) |
| `product_category_id` | Many2one(`product.category`) | Categoría (vacío = todas) |
| `commission_percentage` | Float | Porcentaje de comisión |
| `active` | Boolean | Activo (default True) |
| `company_id` | Many2one(`res.company`) | Compañía |

#### Método principal: `_get_commission_percentage(salesperson, partner, category)`

```python
@api.model
def _get_commission_percentage(self, salesperson, partner, category):
    """Busca la regla más específica por prioridad descendente.

    Patrón: Specificity-based lookup — busca la combinación más precisa
    primero y cae a reglas más genéricas si no encuentra.

    Returns: (rule_record, percentage) o (empty_recordset, 0.0)
    """
    domain_base = [
        ('salesperson_id', '=', salesperson.id),
        ('company_id', 'in', [self.env.company.id, False]),
    ]
    # commercial_partner_id agrupa contactos hijos bajo el partner comercial
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
    """Al confirmar factura/NC, calcula comisiones automáticamente.

    Patrón: Herencia estándar — super() primero para que la factura
    quede posted, luego generamos las comisiones.
    """
    posted = super()._post(soft=soft)
    for move in posted:
        # Solo facturas y NC de cliente generan comisiones
        if move.move_type in ('out_invoice', 'out_refund'):
            move._generate_commissions()
    return posted
```

#### Override 2: `_compute_payment_state()` — Trigger de cobro

```python
@api.depends('amount_residual', 'move_type', 'state', 'company_id')
def _compute_payment_state(self):
    """Detecta cuando la factura pasa a 'paid' o 'in_payment'.

    Por qué override de _compute y NO de write():
    - payment_state es stored computed field
    - Los stored computed se persisten vía _write() interno, NO write()
    - Un override de write() NUNCA vería el cambio de payment_state
    - Override del compute es el patrón correcto para interceptar
      la transición de estado de pago
    """
    super()._compute_payment_state()
    for move in self:
        if (move.move_type == 'out_invoice'
                and move.payment_state in ('paid', 'in_payment')
                and move.commission_ids):
            move.commission_ids.filtered(
                lambda c: c.collection_status == 'pending'
            ).write({'collection_status': 'accrued'})
```

#### Método: `_generate_commissions()` — Cálculo por línea y agrupamiento

```python
def _generate_commissions(self):
    """Genera registros de comisión agrupados por regla/porcentaje.

    Algoritmo:
    1. Para cada línea de producto (display_type == 'product')
    2. Busca la regla más específica para ese vendedor/cliente/categoría
    3. Agrupa montos (price_subtotal) por (rule_id, percentage)
    4. Crea un registro de comisión por grupo con split 50/50

    Patrón: defaultdict para agrupar líneas con el mismo porcentaje
    en un solo registro de comisión.
    """
    self.ensure_one()
    # Evita duplicar comisiones si se re-confirma
    if self.commission_ids:
        return

    salesperson = self.invoice_user_id
    if not salesperson:
        return

    partner = self.partner_id
    RuleModel = self.env['salesperson.commission.rule']

    # key: (rule_id, percentage) → value: sum(price_subtotal)
    grouped = defaultdict(float)

    for line in self.invoice_line_ids:
        if line.display_type != 'product':
            continue
        if not line.product_id:
            continue

        category = line.product_id.categ_id
        rule, percentage = RuleModel._get_commission_percentage(
            salesperson, partner, category)

        if percentage <= 0:
            continue

        grouped[(rule.id, percentage)] += line.price_subtotal

    is_refund = self.move_type == 'out_refund'
    CommissionModel = self.env['salesperson.commission']

    for (rule_id, percentage), base_amount in grouped.items():
        # NC genera comisión negativa para revertir
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
  ├── Por cada línea de producto:
  │     └── Busca regla más específica → obtiene %
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

| Grupo | Reglas | Comisiones |
|-------|--------|------------|
| Gerente contable (`account.group_account_manager`) | CRUD completo | CRUD completo |
| Facturación (`account.group_account_invoice`) | Solo lectura | Solo lectura |

---

## Vistas

| Vista | Modelo | Descripción |
|-------|--------|-------------|
| Tree + Form + Search | `salesperson.commission.rule` | ABM de reglas |
| Tree + Form + Search | `salesperson.commission` | Listado de comisiones |
| Pivot | `salesperson.commission` | Tabla cruzada vendedor × mes |
| Graph | `salesperson.commission` | Gráfico de barras por vendedor |
| Smart button | `account.move` (herencia) | Botón "Comisiones" en factura |

### Filtros disponibles en comisiones

- Por tipo: Facturas / Notas de Crédito
- Por estado: Facturación Pendiente / Cobro Pendiente
- Agrupar por: Vendedor / Cliente / Fecha (mes)

### Menú

```
Facturación
  └── Comisiones
        ├── Comisiones (listado)
        └── Reglas de Comisión (solo gerentes)
```

---

## Decisiones técnicas

### Por qué `_compute_payment_state` y no `write()`

Los **stored computed fields** en Odoo 17 se recomputan cuando cambian sus dependencias (`amount_residual`, `state`, etc.) y se persisten a DB vía el método interno `_write()`, que **no pasa por el `write()` público**. Un override de `write()` nunca detectaría el cambio de `payment_state`.

Referencia: [OCA/commission](https://github.com/OCA/commission) usa un patrón de settlement wizard con chequeo de `payment_state`, pero para nuestro caso (devengamiento automático sin liquidación manual) el override del compute es más directo y confiable.

### Por qué `payment_state` y no `amount_residual == 0`

En operaciones multi-moneda, diferencias de tipo de cambio pueden hacer que `amount_residual` no llegue exactamente a 0. El campo `payment_state` considera la reconciliación contable completa y es más confiable.

### Por qué `price_subtotal` como base

`price_subtotal` es el neto sin IVA por línea. Es el estándar para comisiones comerciales — el vendedor cobra sobre el valor del producto, no sobre los impuestos.

### Por qué `commercial_partner_id` para buscar reglas

En Odoo, un cliente puede tener múltiples contactos (direcciones de envío, facturación). `commercial_partner_id` normaliza al partner comercial raíz, asegurando que la regla aplique sin importar qué contacto se use en la factura.

### Por qué `defaultdict` para agrupar

Si una factura tiene 10 líneas de "Herramientas" (3%) y 5 de "Servicios" (5%), se crean solo 2 registros de comisión (uno por porcentaje), no 15. Reduce ruido y simplifica reportes.

---

## Dependencias

```python
'depends': ['account', 'sale', 'product']
```

| Módulo | Razón |
|--------|-------|
| `account` | `account.move`, monedas, `payment_state`, conciliación |
| `sale` | `invoice_user_id` propagado desde `sale.order` |
| `product` | `product.category` para reglas por categoría |

---

## Verificación

1. **Reglas**: Crear reglas para un vendedor (general 2%, cliente VIP 5%, categoría Obras 3%)
2. **Facturación**: Crear y confirmar factura → verificar comisión con `invoice_status = accrued`
3. **Cobro**: Registrar pago total → verificar `collection_status = accrued`
4. **NC**: Crear NC → verificar comisión negativa con ambos status `accrued`
5. **Prioridad**: Facturar al cliente VIP con producto de Obras → debe aplicar 5% (regla vendedor+cliente) si no hay regla vendedor+cliente+categoría
6. **Reportes**: Pivot por vendedor/mes → verificar totales
