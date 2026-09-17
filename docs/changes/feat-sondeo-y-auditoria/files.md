# Archivos tocados

## `sondeo.py`

**Cambio:** añadido

Recolector. Existía en el árbol de trabajo sin estar versionado; esta rama lo
incorpora al repositorio y le aplica dos correcciones.

La primera afecta el contrato de datos: cuando ninguna entrada de la respuesta
trae el campo `time`, el filtro de antigüedad no puede ejecutarse. Antes esa
situación se registraba con edad `0`; ahora se registra sin valor, y las
columnas `edad_ask_seg`, `edad_bid_seg` y `edad_max_seg` salen vacías en ambos
CSV. La corrida lo anuncia por consola y, si además hay rutas positivas, el
aviso de ventana abierta se emite indicando que la frescura no fue verificada.
Las plazas siguen entrando al cálculo: el comportamiento que cambia es cómo se
deja registrado, no qué se analiza.

La segunda es de forma: se reemplaza el único carácter acentuado que quedaba en
un comentario, para cumplir la convención de código sin tildes.

## `calidad.py`

**Cambio:** añadido

Auditor de las series históricas guardadas en `data/raw/`. Por cada plaza mide
cantidad de muestras, valores distintos, porcentaje de muestras consecutivas sin
cambio, racha máxima con el valor exacto repetido, rango y desvío, y emite un
veredicto: CONGELADA con un solo valor distinto, SOSPECHOSA cuando repite el
valor en más de la mitad de las muestras consecutivas, SIN DATOS por debajo de
seis muestras, y OK en el resto.

Acepta `--lado ask|bid` (por defecto `bid`) y `--dias N` para limitar la lectura
a los últimos N archivos diarios. No escribe ni modifica ningún archivo. Si no
encuentra datos, informa el motivo y termina con código 1, sin traza de error.

## `README.md`

**Cambio:** modificado

Se documenta `MIN_SPREAD_INTERNO`, que no figuraba entre los parámetros, junto
con la razón por la que existe: en las plazas P2P el ask y el bid pueden venir
de anuncios con medios de pago distintos, que no son cruzables entre sí.

Se agrega la sección de auditoría de calidad con los veredictos y su criterio.

Se corrige la descripción de `data/raw/`, que afirmaba guardar todas las plazas
y permitir un reanálisis con otros filtros. Guarda solo las limpias, así que ese
reanálisis no es posible; la limitación queda explícita.

Se explica la diferencia entre una celda de edad vacía y un cero, y se suma una
consulta para aislar las filas cuya frescura no pudo verificarse.

## `.github/workflows/sondeo.yml`

**Cambio:** añadido

Workflow programado cada 15 minutos, con disparo manual disponible. Existía sin
estar versionado y se incorpora sin modificaciones.

## `.gitignore`

**Cambio:** añadido

Excluye `__pycache__/` y el directorio `.atl/` de herramientas locales. `data/`
queda deliberadamente fuera de la exclusión: es el producto del repositorio y el
workflow lo commitea en cada corrida.
