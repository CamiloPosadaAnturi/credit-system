# Reglas financieras y de aplicacion de pagos

Documento de referencia del sistema. Si un calculo del codigo no coincide con
lo descrito aqui, es un error del codigo o de este documento: hay que corregir
uno de los dos, nunca dejarlos en desacuerdo.

Moneda: **pesos mexicanos (MXN)**. Zona horaria: **America/Mexico_City**.

---

## 1. Politica monetaria

| Regla | Valor |
|---|---|
| Tipo de dato | `Decimal` (`DecimalField`). Nunca `float`. |
| Unidad minima | 1 centavo (2 decimales) |
| Redondeo | `ROUND_HALF_UP` (medio hacia arriba) |
| Diferencias de redondeo al dividir en cuotas | Se absorben en la **ultima cuota** |

Implementacion: `apps/core/dinero.py` (`q`, `dividir_en_cuotas`, `prorratear`).

Garantia verificable (probada en `apps/creditos/tests/test_calculos.py`):

```
sum(cuota.capital_programado) == credito.capital
sum(cuota.interes_programado) == credito.interes_total
sum(cuota.importe_programado) == credito.total_a_pagar
```

---

## 2. Calculo del interes

El interes se calcula **una sola vez**, sobre el **capital inicial**, al crear y
al aprobar el credito. No hay interes compuesto y el interes **no se recalcula
con cada pago**.

Modalidades (`apps/core/opciones.py`, `ModalidadInteres`):

| Modalidad | Formula | Uso |
|---|---|---|
| `fijo_capital` (predeterminada) | `interes = capital x tasa` | Regla comercial inicial |
| `simple_periodo` | `interes = capital x tasa x numero_cuotas` | Interes simple por periodo |
| `sin_interes` | `interes = 0` | Prestamos sin costo |

### Regla comercial inicial

**Por cada $1,000 MXN prestados se cobran $400 MXN de interes**, es decir una
tasa fija del **40 % sobre el capital inicial** por el periodo contractual
definido.

| Capital | Interes | Total a pagar |
|---:|---:|---:|
| $1,000 | $400 | $1,400 |
| $2,000 | $800 | $2,800 |
| $3,000 | $1,200 | $4,200 |
| $5,000 | $2,000 | $7,000 |
| $10,000 | $4,000 | $14,000 |

```
interes        = capital * 0.40
total_a_pagar  = capital + interes
saldo_pendiente = total_a_pagar - pagos_aplicados
```

### Advertencias importantes

- El 40 % **no** es una tasa mensual ni anual: corresponde al **periodo
  contractual** que se define en el campo `periodo_tasa` del credito y que
  debe quedar explicito en el contrato firmado.
- La tasa es **configurable por negocio** y se **copia al credito** al crearlo
  y al aprobarlo (snapshot). Cambiar la tasa del negocio **no** altera los
  creditos ya aprobados.
- Solo los creditos futuros usan la tasa nueva. Cambiar las condiciones de un
  credito desembolsado requiere una **reestructuracion autorizada**.
- Antes de operar con clientes reales hay que revisar que las condiciones
  comerciales y el contrato cumplan la normativa mexicana aplicable
  (informacion al consumidor, CAT, cobranza extrajudicial, proteccion de datos
  personales). **El sistema no valida el cumplimiento legal.**

---

## 3. Calendario de pagos

Se genera automaticamente al crear el credito y se regenera al aprobarlo
(mientras no tenga pagos aplicados).

| Frecuencia | Separacion entre cuotas |
|---|---|
| Diario | +1 dia |
| Semanal | +7 dias |
| Quincenal | +15 dias |
| Mensual | +1 mes de calendario (31/01 + 1 mes = 28/02) |
| Personalizado | +N dias definidos por el usuario |

El capital y el interes se reparten en partes iguales entre las cuotas; la
ultima absorbe la diferencia de redondeo.

Ejemplo (1,000 de capital, 400 de interes, 4 cuotas semanales):

| # | Capital | Interes | Cuota |
|---|---:|---:|---:|
| 1 | 250.00 | 100.00 | 350.00 |
| 2 | 250.00 | 100.00 | 350.00 |
| 3 | 250.00 | 100.00 | 350.00 |
| 4 | 250.00 | 100.00 | 350.00 |

---

## 4. Aplicacion de pagos

Orden de aplicacion (`apps/pagos/servicios.py`):

1. **Entre cuotas**: primero las **vencidas mas antiguas**, despues las
   siguientes por orden de vencimiento.
2. **Dentro de cada cuota**: primero el **interes** programado y despues el
   **capital**.

Cada reparto se guarda como un registro `AplicacionPago` (pago, cuota, importe,
capital, interes). Gracias a eso el saldo **siempre puede reconstruirse**:

```
importe_pagado(cuota)    = suma de aplicaciones confirmadas de esa cuota
capital_pagado(credito)  = suma de la parte de capital de esas aplicaciones
interes_pagado(credito)  = suma de la parte de interes
saldo_pendiente(credito) = total_a_pagar - capital_pagado - interes_pagado
```

### Reglas obligatorias implementadas

| Regla | Como se cumple |
|---|---|
| Abonos parciales | Un pago menor a la cuota la deja en estado `parcial` |
| Liquidacion anticipada | `liquidar_anticipadamente()` con descuento configurable |
| Actualizacion de saldos | `recalcular_credito()` tras cada pago o reverso |
| Cuotas pagadas | Estado `pagada` cuando `importe_pagado >= importe_programado` |
| Credito liquidado | Estado `liquidado` cuando el saldo exigible llega a cero |
| Sin pagos duplicados | Clave de idempotencia unica + bloqueo de pagos identicos en 120 s |
| Sin excedentes accidentales | Un pago mayor al saldo exige autorizacion explicita |
| Sin borrado de pagos | Los pagos confirmados solo se **reversan**, nunca se eliminan |
| Concurrencia | `transaction.atomic` + `select_for_update` sobre credito y cuotas |

### Reversos

Un reverso marca el pago como `reversado` (con motivo, autor y fecha), conserva
el registro y las aplicaciones, y recalcula el credito ignorando los pagos no
confirmados. Si el credito estaba liquidado, vuelve a `activo` o `en_mora`.

### Liquidacion anticipada

```
interes_no_devengado = suma del interes pendiente de las cuotas que AUN NO vencen
descuento            = interes_no_devengado * descuento_liquidacion_anticipada
importe_liquidacion  = saldo_pendiente - descuento
```

El descuento se registra como un pago de tipo **condonacion**: cierra el saldo
pero **no cuenta como dinero recibido** en los indicadores de recaudacion.

---

## 5. Mora y cartera vencida

| Concepto | Definicion |
|---|---|
| Dias de atraso de una **cuota** | Dias naturales entre su vencimiento y hoy, si sigue con saldo |
| Dias de atraso del **credito** | Los de su cuota vencida mas antigua |
| **Saldo vencido** | Suma de los saldos de las cuotas ya vencidas |
| **Saldo total pendiente** | Todo lo que falta por pagar del contrato, vencido o no |
| **Credito en mora** | Tiene al menos una cuota vencida sin pagar, pasados los dias de gracia |

Los **dias de gracia** se configuran por negocio y solo afectan al **estado**
del credito, no al calculo del saldo vencido.

### Cargos moratorios

El sistema **no agrega cargos por atraso de forma automatica**. Solo si el
negocio activa `aplica_mora` y define `tasa_mora` se puede calcular, de forma
informativa:

```
cargo = suma( saldo_cuota_vencida * tasa_mora * dias_de_atraso )
```

Ese calculo **no se guarda ni se cobra solo**: requiere una politica
documentada, autorizada y comunicada al cliente.

---

## 6. Estados del credito

```
borrador -> pendiente_aprobacion -> aprobado -> desembolsado -> activo
                                                                  |
                              +-----------------------------------+
                              |                |                  |
                          en_mora          liquidado        reestructurado
```

`cancelado` es posible desde cualquier estado previo al pago (sin pagos
aplicados). Un credito **desembolsado no se edita**: los ajustes se hacen con
reversos auditados o reestructuraciones.

---

## 7. Indicadores: que significa cada numero

Confundir estos conceptos es el error mas comun en este tipo de negocio.

| Indicador | Que es | Que NO es |
|---|---|---|
| Capital colocado | Dinero prestado (sale del negocio) | No es un ingreso |
| Interes contractual | Interes pactado de los creditos desembolsados | No es utilidad cobrada |
| Total recaudado | Dinero recibido (pagos confirmados, sin condonaciones) | No es utilidad: incluye capital |
| Saldo pendiente | Lo que falta por cobrar de creditos vigentes | No incluye creditos liquidados |
| Saldo vencido | La parte del saldo pendiente ya vencida | No es una perdida declarada |
| % recuperacion | recaudado / total contractual del periodo | |
| % cartera vencida | saldo vencido / saldo pendiente | |

El monto recibido por un cobrador es **cobranza**, no utilidad del negocio.

---

## 8. Auditoria

Se registran en `apps/auditoria`: creacion y edicion de creditos, aprobaciones,
desembolsos, cancelaciones, reestructuraciones, pagos, reversos, gestiones de
cobranza y exportaciones de reportes, con usuario, negocio, IP y datos clave.
La bitacora es de solo lectura desde la aplicacion.
