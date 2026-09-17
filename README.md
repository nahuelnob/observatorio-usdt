# Sondeo de arbitraje USDT/ARS

Mide, cada 15 minutos, si existe una oportunidad real de arbitraje espacial de
USDT contra pesos entre los exchanges argentinos. No opera: solo registra.

La pregunta que este repo intenta contestar es una sola:

> ¿Alguna vez se abre una ventana rentable, y si se abre, cuándo y por cuánto tiempo?

## Por qué existe

Un sondeo puntual del 17/09/2026 dio esto sobre 36 plazas:

- 3 plazas con cotizaciones podridas (spreads internos de 5% a 42%) que un
  dashboard ingenuo reportaría como oportunidades gigantes.
- Sobre las 33 restantes, el mejor spread bruto entre las dos mejores puntas
  de todo el mercado fue **0,052%**.
- Descontando 1 USDT de costo de red, **0 rutas rentables de 1.056**.

O sea: el mercado está arbitrado y no hay rulo simple. Pero eso es una foto.
Este repo saca la película, que es la única forma de saber si hay ventanas
en horarios donde los market makers aflojan.

## Setup

1. Creá un repo (privado está bien).
2. Copiá `sondeo.py` y `calidad.py` a la raíz.
3. Copiá `sondeo.yml` a `.github/workflows/sondeo.yml`.
4. Push.
5. Andá a la pestaña **Actions** y habilitá los workflows si te lo pide.
6. Corré el workflow a mano una vez (**Run workflow**) para verificar que anda.

Después no tocás nada. Los datos aparecen solos en `data/`.

> GitHub desactiva los workflows programados si el repo queda 60 días sin
> actividad. Como este commitea todo el tiempo, no debería pasar.

## Qué genera

**`data/metricas.csv`** — una fila por corrida, la serie principal:

| columna | qué es |
|---|---|
| `ts_art` | timestamp en hora argentina |
| `hora_art`, `dow` | hora del día y día de semana, para buscar patrones horarios |
| `n_limpias` / `n_descartadas` | cuántas plazas pasaron el filtro de calidad |
| `mejor_ask_ex`, `mejor_ask` | dónde y a cuánto se compra más barato |
| `mejor_bid_ex`, `mejor_bid` | dónde y a cuánto se vende más caro |
| `edad_ask_seg`, `edad_bid_seg` | hace cuántos segundos se cotizó cada punta. **Si aparece una ventana con estos valores altos, sospechá del dato antes de festejar.** Vacío = la respuesta no trajo timestamps y el filtro de frescura no pudo correr |
| `edad_max_seg` | la punta más vieja que entró al cálculo. Vacío, igual que arriba |
| `spread_bruto_pct` | diferencia entre las dos mejores puntas, sin costos |
| `spread_neto_pct` | lo mismo descontando el fee de red. **Esta es la columna que importa** |
| `rutas_pos_con_fee` | cuántas de las ~1.000 rutas dan positivo. Si alguna vez es > 0, pasó algo |
| `mejor_ruta` | la ruta concreta, para poder verificarla a mano |
| `descartadas` | qué plazas se filtraron y por qué |

**`data/raw/YYYY-MM-DD.csv`** — las puntas de las plazas **limpias**, una fila
por plaza por corrida. Sirve para re-analizar con otro fee o con otro capital
sin volver a pedirle nada a la API.

Lo que no permite, y conviene saberlo: **no podés re-analizar con otro filtro.**
De las plazas descartadas solo queda el motivo en la columna `descartadas` de
`metricas.csv`; su `ask` y su `bid` no se guardan en ningún lado. Si mañana
querés subir `MAX_SPREAD_INTERNO` y ver qué pasaba con las que hoy quedan
afuera, esos precios ya no están.

## Cómo leer los resultados

La consulta que contesta la pregunta del repo:

```bash
# ¿Se abrió alguna ventana alguna vez?  (col 19 = rutas_pos_con_fee)
awk -F, 'NR>1 && $19>0' data/metricas.csv

# Distribución del spread neto por hora del día  (col 3 = hora, col 16 = neto)
awk -F, 'NR>1 {s[$3]+=$16; n[$3]++} END {for (h in s) printf "%02d hs  %+.4f%%\n", h, s[h]/n[h]}' data/metricas.csv | sort

# Plazas que más se descartan, y por qué
awk -F, 'NR>1 {print $22}' data/metricas.csv | tr ';' '\n' | sort | uniq -c | sort -rn | head

# Filas sin frescura verificada (col 14 vacía) — excluilas de cualquier conclusión
awk -F, 'NR>1 && $14==""' data/metricas.csv
```

Si alguna fila da `rutas_pos_con_fee > 0`, antes de festejar mirá `edad_ask_seg`
y `edad_bid_seg` de esa fila. Una ventana sostenida por una punta de hace
4 minutos probablemente no existió nunca.

Si esas columnas están **vacías**, la respuesta de la API no trajo timestamps y
el filtro de frescura no corrió: la fila se guarda igual (el dato crudo sirve)
pero no alcanza como evidencia de nada. Un cero significa "recién cotizada";
vacío significa "no sé". No son lo mismo.

Si después de dos semanas `rutas_pos_con_fee` es cero en todas las filas, la
respuesta es que no hay rulo, y ahorraste construir el bot.

## Auditoría de calidad

`sondeo.py` filtra por antigüedad del *timestamp*. Pero hay un caso que no puede
ver desde una sola corrida: **la plaza que actualiza el timestamp y no el
precio**. Esa pasa los tres filtros, se ve fresca, y contamina las mejores
puntas. Un latido no es un pulso.

Detectarla necesita historia, y por eso vive aparte:

```bash
python calidad.py                 # lado bid, toda la historia
python calidad.py --lado ask      # la punta de compra
python calidad.py --dias 3        # solo los últimos 3 archivos diarios
```

Lee `data/raw/*.csv` y por cada plaza reporta muestras, valores distintos,
porcentaje de muestras consecutivas sin cambio, racha más larga con el valor
exacto repetido, rango y desvío. Con eso marca:

| veredicto | criterio |
|---|---|
| `CONGELADA` | un solo valor distinto en toda la serie |
| `SOSPECHOSA` | repite el valor exacto en más del 50% de las muestras consecutivas |
| `SIN DATOS` | menos de 6 muestras: no alcanza para opinar, hay que esperar |
| `OK` | se mueve como se mueve un mercado |

**`calidad.py` no filtra ni modifica nada.** Solo mide y te lo dice. Es a
propósito: un filtro que descarta en silencio es exactamente lo que hace que
después no confíes en tus propios datos. Si una plaza aparece como congelada,
`sondeo.py` la va a seguir incluyendo hasta que vos decidas otra cosa.

## Parámetros

Arriba de `sondeo.py`, en la sección `parametros del modelo`:

- **`FEE_RED_USDT`** (default `1.0`) — costo fijo de mover el USDT entre
  plataformas. Ponelo en `0` si vas a operar con capital ya posicionado en
  ambos lados, que es como se hace en serio: no transferís en el momento,
  rebalanceás después.
- **`MAX_SPREAD_INTERNO`** (default `0.05`) — una plaza cuyo ask y bid difieren
  más que esto tiene el libro vacío o la cotización congelada. Bajarlo filtra
  más agresivo; subirlo deja entrar basura.
- **`MIN_SPREAD_INTERNO`** (default `-0.001`) — el piso del mismo filtro. Un ask
  por debajo del bid en la misma plaza sería plata gratis sin moverse de ahí, y
  no existe: en P2P pasa cuando ask y bid vienen de anuncios con medios de pago
  distintos, que no son cruzables entre sí. La tolerancia negativa deja pasar el
  redondeo, no la fantasía.
- **`MAX_EDAD_SEG`** (default `300`) — antigüedad máxima de una cotización. Se
  mide contra la punta más fresca de la misma respuesta, no contra el reloj
  local, así que también funciona al reprocesar un JSON viejo con `--from`.
  Es el filtro más importante de los tres: una punta congelada parece operable
  y no lo es. Si la respuesta no trae ningún timestamp el filtro no puede correr;
  la corrida avisa por consola y deja las columnas de edad vacías en vez de
  escribir un cero que se leería como "recién cotizada".
- **`CAPITAL_ARS`** — solo afecta la columna de ganancia en pesos, no los
  porcentajes.

## Lo que este sondeo NO mide

Importante tenerlo presente antes de sacar conclusiones:

- **Profundidad.** Los precios son la punta del libro. Si querés mover un monto
  grande, el precio real es peor. Medir esto requiere la API de orderbook de
  cada exchange, que es el siguiente paso si los datos justifican seguir.
- **Latencia.** Entre que se detecta y se ejecuta pasa tiempo. Una ventana de
  30 segundos no es operable a mano.
- **Límites y verificación.** Montos mínimos, KYC, límites diarios, y si la
  plaza efectivamente te deja retirar.
- **Riesgo de contraparte** en las plazas P2P, que son varias de las que
  aparecen con las mejores puntas.

## Fuente

[CriptoYa API](https://criptoya.com/api) — pública y gratuita, sin API key.
