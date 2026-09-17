#!/usr/bin/env python3
"""
Sondeo de arbitraje USDT/ARS.

Baja las puntas de todos los exchanges argentinos, descarta las cotizaciones
podridas, evalua todas las rutas compra/venta posibles descontando comisiones
y costo de red, y guarda el resultado en CSV.

Sin dependencias: solo stdlib. Corre en cualquier Python 3.9+.

Uso:
    python sondeo.py                 # baja datos en vivo y appendea
    python sondeo.py --dry-run       # imprime sin escribir archivos
    python sondeo.py --from x.json   # usa un JSON local (para testear)
"""

import argparse
import csv
import datetime as dt
import itertools
import json
import os
import sys
import urllib.error
import urllib.request

API_USDT = "https://criptoya.com/api/usdt/ars/1"

# --- parametros del modelo -------------------------------------------------
# Capital de referencia para expresar la ganancia en pesos. No afecta los
# porcentajes, solo la columna de ganancia absoluta.
CAPITAL_ARS = 1_000_000

# Costo fijo de mover el USDT entre plataformas, en USDT.
# 1.0 es lo tipico en TRC20. Ponelo en 0 si vas a operar con capital ya
# posicionado en ambos lados (no transferis, solo rebalanceas despues).
FEE_RED_USDT = 1.0

# Una plaza cuyo spread interno (ask vs bid) supera esto tiene el libro vacio,
# la cotizacion congelada o es iliquida. Incluirla genera oportunidades fantasma.
MAX_SPREAD_INTERNO = 0.05  # 5%

# Un ask menor al bid en la misma plaza es imposible: dato corrupto.
# (En P2P suele pasar cuando ask y bid vienen de anuncios con medios de pago
# distintos, que no son cruzables entre si.)
MIN_SPREAD_INTERNO = -0.001

# Antiguedad maxima de una cotizacion, en segundos. Una punta congelada es
# peor que ninguna punta: parece operable y no lo es. Se mide contra el reloj
# de la propia respuesta (la cotizacion mas fresca del lote), no contra el
# reloj local, asi tambien funciona al reprocesar un JSON guardado.
MAX_EDAD_SEG = 300  # 5 minutos

TIMEOUT = 20
ART = dt.timezone(dt.timedelta(hours=-3))

DIR_DATOS = "data"
CSV_METRICAS = os.path.join(DIR_DATOS, "metricas.csv")
DIR_RAW = os.path.join(DIR_DATOS, "raw")

COLS_METRICAS = [
    "ts_utc", "ts_art", "hora_art", "dow",
    "n_total", "n_limpias", "n_descartadas",
    "mejor_ask_ex", "mejor_ask", "mejor_bid_ex", "mejor_bid",
    "edad_ask_seg", "edad_bid_seg", "edad_max_seg",
    "spread_bruto_pct", "spread_neto_pct", "ganancia_neta_ars",
    "rutas_pos_sin_fee", "rutas_pos_con_fee", "rutas_totales",
    "mejor_ruta", "descartadas",
]


# --- obtencion -------------------------------------------------------------

def bajar(url):
    req = urllib.request.Request(url, headers={"User-Agent": "sondeo-arbitraje/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status} en {url}")
        return json.loads(r.read().decode("utf-8"))


# --- limpieza --------------------------------------------------------------

def reloj_del_lote(data):
    """
    Timestamp de referencia: la cotizacion mas fresca de la respuesta.

    Usamos esto y no time.time() por dos razones: permite reprocesar un JSON
    guardado con el mismo criterio, y evita que un desfasaje del reloj local
    descarte todo el lote.
    """
    tiempos = []
    for v in data.values():
        try:
            t = int(v["time"])
            if t > 0:
                tiempos.append(t)
        except (KeyError, TypeError, ValueError):
            continue
    return max(tiempos) if tiempos else None


def separar(data):
    """Devuelve (limpias, descartadas). Cada valor necesita totalAsk y totalBid."""
    ref = reloj_del_lote(data)
    limpias, descartadas = {}, {}
    for nombre, v in data.items():
        try:
            ask = float(v["totalAsk"])
            bid = float(v["totalBid"])
        except (KeyError, TypeError, ValueError):
            descartadas[nombre] = "campos faltantes o no numericos"
            continue
        if ask <= 0 or bid <= 0:
            descartadas[nombre] = "precio no positivo"
            continue

        # Antiguedad primero: una punta vieja no merece ni que le miremos el spread.
        #
        # Si el lote entero vino sin timestamps (ref is None) este filtro no puede
        # correr. En ese caso la edad queda en None y no en 0: un 0 se lee como
        # "recien cotizada" y es justo la mentira que este filtro existe para
        # evitar. None viaja al CSV como celda vacia, que es la verdad.
        edad = None
        if ref is not None:
            try:
                edad = ref - int(v["time"])
            except (KeyError, TypeError, ValueError):
                edad = None
            if edad is None:
                descartadas[nombre] = "sin timestamp"
                continue
            if edad > MAX_EDAD_SEG:
                descartadas[nombre] = f"congelada hace {edad // 60}m{edad % 60:02d}s"
                continue

        interno = (ask - bid) / ask
        if interno > MAX_SPREAD_INTERNO:
            descartadas[nombre] = f"spread interno {interno:.1%}"
        elif interno < MIN_SPREAD_INTERNO:
            descartadas[nombre] = f"ask<bid ({interno:.1%})"
        else:
            limpias[nombre] = {"ask": ask, "bid": bid, "edad": edad}
    return limpias, descartadas


# --- evaluacion ------------------------------------------------------------

def evaluar(limpias, fee_red):
    """Todas las rutas comprar-en-X / vender-en-Y, ordenadas por rendimiento."""
    rutas = []
    for (ex_c, v_c), (ex_v, v_v) in itertools.permutations(limpias.items(), 2):
        ask, bid = v_c["ask"], v_v["bid"]
        usdt = CAPITAL_ARS / ask
        neto = usdt - fee_red
        if neto <= 0:
            continue
        pnl = neto * bid - CAPITAL_ARS
        rutas.append({
            "pct": pnl / CAPITAL_ARS * 100,
            "pnl": pnl,
            "comprar": ex_c, "ask": ask,
            "vender": ex_v, "bid": bid,
        })
    rutas.sort(key=lambda r: r["pct"], reverse=True)
    return rutas


def analizar(data, ahora=None):
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    limpias, descartadas = separar(data)
    if len(limpias) < 2:
        raise RuntimeError(f"solo {len(limpias)} plazas limpias, no hay nada que comparar")

    mejor_ask_ex = min(limpias, key=lambda k: limpias[k]["ask"])
    mejor_bid_ex = max(limpias, key=lambda k: limpias[k]["bid"])
    mejor_ask = limpias[mejor_ask_ex]["ask"]
    mejor_bid = limpias[mejor_bid_ex]["bid"]

    sin_fee = evaluar(limpias, 0.0)
    con_fee = evaluar(limpias, FEE_RED_USDT)
    top = con_fee[0]
    local = ahora.astimezone(ART)

    # Si la respuesta no trajo timestamps, todas las edades son None y el filtro
    # de frescura no corrio. Las columnas de edad quedan vacias en el CSV para
    # que el analisis pueda excluir estas filas en vez de confiar en ellas.
    edades = [v["edad"] for v in limpias.values() if v["edad"] is not None]

    return {
        "ts_utc": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ts_art": local.strftime("%Y-%m-%d %H:%M:%S"),
        "hora_art": local.hour,
        "dow": local.strftime("%a"),
        "n_total": len(data),
        "n_limpias": len(limpias),
        "n_descartadas": len(descartadas),
        "mejor_ask_ex": mejor_ask_ex,
        "mejor_ask": round(mejor_ask, 4),
        "mejor_bid_ex": mejor_bid_ex,
        "mejor_bid": round(mejor_bid, 4),
        # Antiguedad de las dos puntas que definen la oportunidad: si una
        # ventana aparece con estas en alto, sospechar del dato antes que
        # festejar.
        "edad_ask_seg": limpias[mejor_ask_ex]["edad"],
        "edad_bid_seg": limpias[mejor_bid_ex]["edad"],
        "edad_max_seg": max(edades) if edades else None,
        "spread_bruto_pct": round((mejor_bid - mejor_ask) / mejor_ask * 100, 4),
        "spread_neto_pct": round(top["pct"], 4),
        "ganancia_neta_ars": round(top["pnl"], 2),
        "rutas_pos_sin_fee": sum(1 for r in sin_fee if r["pct"] > 0),
        "rutas_pos_con_fee": sum(1 for r in con_fee if r["pct"] > 0),
        "rutas_totales": len(con_fee),
        "mejor_ruta": f"{top['comprar']}@{top['ask']:.2f}->{top['vender']}@{top['bid']:.2f}",
        "descartadas": ";".join(f"{k}({v})" for k, v in descartadas.items()),
        "_limpias": limpias,
    }


# --- persistencia ----------------------------------------------------------

def appendear(path, cols, filas):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    nuevo = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if nuevo:
            w.writeheader()
        w.writerows(filas)


def guardar(res):
    fila = {c: res[c] for c in COLS_METRICAS}
    appendear(CSV_METRICAS, COLS_METRICAS, [fila])

    # Snapshot crudo del dia: permite re-analizar con otros supuestos mas
    # adelante sin haber perdido nada.
    dia = res["ts_art"][:10]
    crudo = [
        {"ts_art": res["ts_art"], "exchange": ex,
         "ask": round(v["ask"], 4), "bid": round(v["bid"], 4), "edad_seg": v["edad"]}
        for ex, v in sorted(res["_limpias"].items())
    ]
    appendear(os.path.join(DIR_RAW, f"{dia}.csv"),
              ["ts_art", "exchange", "ask", "bid", "edad_seg"], crudo)


# --- salida legible --------------------------------------------------------

def edad_legible(seg):
    return "edad desconocida" if seg is None else f"cotizada hace {seg}s"


def imprimir(res):
    sin_edades = res["edad_max_seg"] is None

    print(f"[{res['ts_art']} ART]  {res['n_limpias']}/{res['n_total']} plazas limpias")
    if sin_edades:
        print("  !! la respuesta no trajo timestamps: el filtro de frescura NO corrio.")
        print("     Cualquier punta de aca abajo puede estar congelada.")
    print(f"  mejor compra : {res['mejor_ask_ex']} @ {res['mejor_ask']:.2f} "
          f"({edad_legible(res['edad_ask_seg'])})")
    print(f"  mejor venta  : {res['mejor_bid_ex']} @ {res['mejor_bid']:.2f} "
          f"({edad_legible(res['edad_bid_seg'])})")
    print(f"  spread bruto : {res['spread_bruto_pct']:+.4f}%")
    print(f"  spread neto  : {res['spread_neto_pct']:+.4f}%  "
          f"({res['ganancia_neta_ars']:+,.0f} ARS por millon, fee {FEE_RED_USDT} USDT)")
    print(f"  rutas rentables: {res['rutas_pos_con_fee']}/{res['rutas_totales']} con fee, "
          f"{res['rutas_pos_sin_fee']}/{res['rutas_totales']} sin fee")
    print(f"  mejor ruta   : {res['mejor_ruta']}")
    if res["descartadas"]:
        print(f"  descartadas  : {res['descartadas']}")
    if res["rutas_pos_con_fee"] > 0:
        if sin_edades:
            print("  >>> VENTANA ABIERTA, PERO SIN VERIFICAR FRESCURA <<<")
        else:
            print("  >>> VENTANA ABIERTA <<<")


# --- main ------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="no escribe archivos")
    p.add_argument("--from", dest="origen", help="leer un JSON local en vez de la API")
    args = p.parse_args()

    try:
        data = json.load(open(args.origen, encoding="utf-8")) if args.origen else bajar(API_USDT)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        # La API caida no es un fallo del sondeo: salimos limpio y sin escribir,
        # asi la corrida no ensucia el CSV ni marca el workflow en rojo.
        print(f"API inaccesible ({e}). Sin datos esta corrida.", file=sys.stderr)
        return 0
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Respuesta ilegible ({e}).", file=sys.stderr)
        return 0

    if not isinstance(data, dict) or not data:
        print("Respuesta vacia o con forma inesperada.", file=sys.stderr)
        return 0

    try:
        res = analizar(data)
    except RuntimeError as e:
        print(f"Datos insuficientes: {e}", file=sys.stderr)
        return 0

    imprimir(res)
    if not args.dry_run:
        guardar(res)
        print(f"  -> {CSV_METRICAS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
