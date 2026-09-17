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
2. Copiá `sondeo.py` a la raíz.
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
| `spread_bruto_pct` | diferencia entre las dos mejores puntas, sin costos |
| `spread_neto_pct` | lo mismo descontando el fee de red. **Esta es la columna que importa** |
| `rutas_pos_con_fee` | cuántas de las ~1.000 rutas dan positivo. Si alguna vez es > 0, pasó algo |
| `mejor_ruta` | la ruta concreta, para poder verificarla a mano |
| `descartadas` | qué plazas se filtraron y por qué |

**`data/raw/YYYY-MM-DD.csv`** — todas las puntas de todas las plazas, por
corrida. Sirve para re-analizar con otros supuestos (otro fee, otro capital,
otro filtro) sin haber perdido nada.

## Cómo leer los resultados

La consulta que contesta la pregunta del repo:

```bash
# ¿Se abrió alguna ventana alguna vez?
awk -F, 'NR>1 && $16>0' data/metricas.csv

# Distribución del spread neto por hora del día
awk -F, 'NR>1 {s[$3]+=$13; n[$3]++} END {for (h in s) printf "%02d hs  %+.4f%%\n", h, s[h]/n[h]}' data/metricas.csv | sort
```

Si después de dos semanas `rutas_pos_con_fee` es cero en todas las filas, la
respuesta es que no hay rulo, y ahorraste construir el bot.

## Parámetros

Arriba de `sondeo.py`, en la sección `parametros del modelo`:

- **`FEE_RED_USDT`** (default `1.0`) — costo fijo de mover el USDT entre
  plataformas. Ponelo en `0` si vas a operar con capital ya posicionado en
  ambos lados, que es como se hace en serio: no transferís en el momento,
  rebalanceás después.
- **`MAX_SPREAD_INTERNO`** (default `0.05`) — una plaza cuyo ask y bid difieren
  más que esto tiene el libro vacío o la cotización congelada. Bajarlo filtra
  más agresivo; subirlo deja entrar basura.
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
