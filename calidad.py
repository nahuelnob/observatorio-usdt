#!/usr/bin/env python3
"""
Auditoria de calidad de las series de data/raw/.

Contesta lo que sondeo.py no puede contestar solo, porque necesita historia.

El filtro de antiguedad de sondeo.py descarta las cotizaciones viejas, pero no
detecta el caso peor: la plaza que actualiza el timestamp y no el precio. Esa
pasa los tres filtros, se ve fresca, y contamina las mejores puntas. Un latido
no es un pulso.

Este script NO filtra ni modifica nada: solo mide y reporta. Es a proposito.
Un filtro que descarta en silencio es lo que hace que despues no confies en tus
propios datos.

Sin dependencias: solo stdlib. Corre en cualquier Python 3.9+.

Uso:
    python calidad.py                  # lado bid, toda la historia
    python calidad.py --lado ask       # audita la punta de compra
    python calidad.py --dias 3         # solo los ultimos 3 archivos
"""

import argparse
import csv
import glob
import os
import statistics
import sys

DIR_RAW = os.path.join("data", "raw")

# Debajo de esto no hay estadistica que valga: decimos que hay que esperar en
# vez de dibujar un veredicto sobre cuatro puntos.
MIN_MUESTRAS = 6

# Si mas de esta fraccion de las muestras consecutivas repite el valor exacto,
# la plaza esta quieta de una forma que un mercado real no explica.
UMBRAL_SOSPECHA = 0.50


# --- carga -----------------------------------------------------------------

def archivos(dias=None):
    """Los CSV diarios en orden cronologico. El nombre es YYYY-MM-DD, asi que
    ordenar alfabeticamente alcanza."""
    todos = sorted(glob.glob(os.path.join(DIR_RAW, "*.csv")))
    return todos[-dias:] if dias else todos


def series(paths, lado):
    """{exchange: [valores en orden cronologico]}.

    Las filas rotas se saltean en vez de romper la corrida: este script audita
    datos posiblemente sucios, seria absurdo que se caiga con uno.
    """
    datos, ignoradas = {}, 0
    for path in paths:
        try:
            with open(path, newline="", encoding="utf-8") as f:
                for fila in csv.DictReader(f):
                    try:
                        valor = float(fila[lado])
                    except (KeyError, TypeError, ValueError):
                        ignoradas += 1
                        continue
                    if valor > 0:
                        datos.setdefault(fila["exchange"], []).append(valor)
                    else:
                        ignoradas += 1
        except OSError as e:
            print(f"No pude leer {path} ({e}), lo salteo.", file=sys.stderr)
    return datos, ignoradas


# --- medicion --------------------------------------------------------------

def racha_mas_larga(valores):
    """Cantidad maxima de muestras consecutivas con el valor exacto repetido."""
    mejor = actual = 1
    for i in range(1, len(valores)):
        actual = actual + 1 if valores[i] == valores[i - 1] else 1
        mejor = max(mejor, actual)
    return mejor


def medir(valores):
    n = len(valores)
    distintos = len(set(valores))
    repetidas = sum(1 for i in range(1, n) if valores[i] == valores[i - 1])
    pct_sin_cambio = repetidas / (n - 1) * 100 if n > 1 else 0.0

    piso, techo = min(valores), max(valores)
    promedio = statistics.fmean(valores)

    return {
        "n": n,
        "distintos": distintos,
        "pct_sin_cambio": pct_sin_cambio,
        "racha": racha_mas_larga(valores),
        "rango_pct": (techo - piso) / piso * 100 if piso else 0.0,
        "desvio_pct": (statistics.stdev(valores) / promedio * 100
                       if n > 1 and promedio else 0.0),
    }


def veredicto(m):
    """CONGELADA / SOSPECHOSA / OK / SIN DATOS. No modifica nada: solo opina."""
    if m["n"] < MIN_MUESTRAS:
        return "SIN DATOS"
    if m["distintos"] == 1:
        return "CONGELADA"
    if m["pct_sin_cambio"] > UMBRAL_SOSPECHA * 100:
        return "SOSPECHOSA"
    return "OK"


# --- salida ----------------------------------------------------------------

# Peor primero: lo que hay que mirar no deberia estar al fondo de la lista.
ORDEN = {"CONGELADA": 0, "SOSPECHOSA": 1, "SIN DATOS": 2, "OK": 3}


def informar(datos, lado, paths, ignoradas):
    filas = []
    for exchange, valores in datos.items():
        m = medir(valores)
        filas.append((veredicto(m), exchange, m))
    filas.sort(key=lambda f: (ORDEN[f[0]], -f[2]["pct_sin_cambio"], f[1]))

    print(f"Auditoria de calidad - lado {lado} - {len(paths)} archivo(s), "
          f"{len(datos)} plazas")
    print(f"Desde {os.path.basename(paths[0])} hasta {os.path.basename(paths[-1])}")
    if ignoradas:
        print(f"Filas ignoradas por ilegibles: {ignoradas}")
    print()

    cab = (f"{'veredicto':<11} {'exchange':<16} {'n':>4} {'dist':>5} "
           f"{'=consec':>8} {'racha':>6} {'rango%':>8} {'desvio%':>8}")
    print(cab)
    print("-" * len(cab))
    for v, exchange, m in filas:
        print(f"{v:<11} {exchange:<16} {m['n']:>4} {m['distintos']:>5} "
              f"{m['pct_sin_cambio']:>7.1f}% {m['racha']:>6} "
              f"{m['rango_pct']:>7.3f}% {m['desvio_pct']:>7.3f}%")

    resumen(filas)


def resumen(filas):
    cuenta = {}
    for v, _, _ in filas:
        cuenta[v] = cuenta.get(v, 0) + 1

    print()
    congeladas = [e for v, e, _ in filas if v == "CONGELADA"]
    sospechosas = [e for v, e, _ in filas if v == "SOSPECHOSA"]
    esperando = [e for v, e, _ in filas if v == "SIN DATOS"]

    if congeladas:
        print(f"CONGELADAS ({len(congeladas)}): {', '.join(congeladas)}")
        print("  Un solo valor distinto en toda la serie. El timestamp puede")
        print("  estar moviendose igual: por eso sondeo.py no las agarra.")
    if sospechosas:
        print(f"SOSPECHOSAS ({len(sospechosas)}): {', '.join(sospechosas)}")
        print(f"  Repiten el valor exacto en mas del {UMBRAL_SOSPECHA:.0%} de las")
        print("  muestras consecutivas. Miralas antes de creerles una ventana.")
    if esperando:
        print(f"SIN DATOS ({len(esperando)}): {', '.join(esperando)}")
        print(f"  Menos de {MIN_MUESTRAS} muestras. Hay que esperar mas corridas.")
    if cuenta.get("OK"):
        print(f"OK: {cuenta['OK']} plazas se mueven como un mercado real.")

    print()
    print("Este script no filtro ni modifico nada. Si una plaza figura aca,")
    print("sondeo.py la sigue incluyendo: la decision de excluirla es tuya.")


# --- main ------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Audita la calidad de las series guardadas en data/raw/.")
    p.add_argument("--lado", choices=["ask", "bid"], default="bid",
                   help="que punta auditar (default: bid)")
    p.add_argument("--dias", type=int,
                   help="mirar solo los ultimos N archivos diarios")
    args = p.parse_args()

    if args.dias is not None and args.dias < 1:
        print("--dias tiene que ser 1 o mas.", file=sys.stderr)
        return 1

    paths = archivos(args.dias)
    if not paths:
        print(f"No hay archivos en {DIR_RAW}/. Corre sondeo.py al menos una vez.",
              file=sys.stderr)
        return 1

    datos, ignoradas = series(paths, args.lado)
    if not datos:
        print(f"Los archivos existen pero no tienen filas legibles con '{args.lado}'.",
              file=sys.stderr)
        return 1

    informar(datos, args.lado, paths, ignoradas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
