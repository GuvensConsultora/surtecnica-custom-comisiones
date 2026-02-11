# Sur Técnica - Comisiones de Vendedores (Odoo 17)

## Funcionamiento Nativo de Odoo

Odoo 17 maneja vendedores en facturas mediante el campo `invoice_user_id` en `account.move`, que se hereda automáticamente del pedido de venta (`sale.order.user_id`). Sin embargo, Odoo **no incluye** un sistema de cálculo de comisiones nativo — solo asigna el vendedor.

### Campos estándar utilizados
- `account.move.invoice_user_id` → Vendedor asignado
- `account.move.partner_id` → Cliente
- `account.move.line.price_subtotal` → Neto sin IVA por línea
- `account.move.line.display_type` → `'product'` para líneas de producto
- `account.move.amount_residual` → Saldo pendiente
- `account.move.payment_state` → Estado de pago (`paid`, `in_payment`)
- `product.product.categ_id` → Categoría de producto

## Solución Propuesta

Módulo `surtecnica_custom_comisiones` que automatiza el cálculo de comisiones con un esquema **50/50**: la mitad se devenga al facturar, la otra mitad al cobrar.

### Modelos

#### `salesperson.commission.rule` — Reglas de Comisión

Define porcentajes de comisión con prioridad por especificidad:

| Prioridad | Combinación | Ejemplo |
|-----------|-------------|---------|
| 1 (máxima) | Vendedor + Cliente + Categoría | Juan → ClienteVIP → Obras: 8% |
| 2 | Vendedor + Cliente | Juan → ClienteVIP: 5% |
| 3 | Vendedor + Categoría | Juan → Obras: 3% |
| 4 (default) | Vendedor solo | Juan → todos: 2% |

#### `salesperson.commission` — Comisión Calculada

Un registro por cada combinación (factura, porcentaje). Campos principales:
- `base_amount`: Neto sin IVA
- `commission_amount`: Comisión total (base × %)
- `invoice_commission`: 50% por facturación
- `collection_commission`: 50% por cobro
- `invoice_status` / `collection_status`: `pending` o `accrued`

#### `account.move` (herencia)

- Smart button "Comisiones" en la factura
- Override `_post()`: genera comisiones automáticamente al confirmar
- Override `write()`: detecta pago total → marca cobro como devengado

### Flujo

```
Factura confirmada (posted)
  └─→ _post() genera comisiones
       ├── invoice_status = 'accrued' (50% devengado)
       └── collection_status = 'pending' (50% pendiente)

Factura cobrada (payment_state = 'paid')
  └─→ write() detecta el cambio
       └── collection_status = 'accrued' (50% devengado)

Nota de Crédito confirmada
  └─→ _post() genera comisión NEGATIVA
       ├── invoice_status = 'accrued'
       └── collection_status = 'accrued' (ambos inmediato)
```

### NC (Notas de Crédito)

Las NC generan comisiones con `base_amount` y `commission_amount` negativos. Ambos estados se marcan como `accrued` inmediatamente para descontar de las comisiones del vendedor.

## Métodos Principales

### `salesperson.commission.rule._get_commission_percentage(salesperson, partner, category)`

```python
# Patrón: Specificity-based lookup
# Busca la regla más específica primero y cae a reglas genéricas
# Prioridad: vendedor+cliente+categoría > vendedor+cliente > vendedor+categoría > vendedor
```

### `account.move._generate_commissions()`

```python
# Por cada línea de producto (display_type == 'product'):
#   1. Busca regla más específica
#   2. Agrupa montos por (rule_id, percentage)
#   3. Crea registros de comisión con split 50/50
# Patrón: defaultdict para agrupar líneas por porcentaje
```

### `account.move._post()` (override)

```python
# Herencia estándar: super() primero, luego genera comisiones
# Solo para out_invoice y out_refund
```

### `account.move.write()` (override)

```python
# Intercepta cambios en payment_state
# Si pasa a 'paid' o 'in_payment', devenga el 50% de cobro
```

## Instalación

1. Copiar el módulo en la carpeta de addons custom
2. Actualizar lista de aplicaciones
3. Instalar "Sur Técnica - Comisiones de Vendedores"

## Dependencias

- `account`: Facturas, monedas, conciliación
- `sale`: Campo `invoice_user_id` del pedido de venta
- `product`: Categorías de producto para reglas por categoría
