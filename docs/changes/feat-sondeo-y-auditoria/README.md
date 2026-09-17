# Sondeo de arbitraje y auditoría de calidad de los datos

**Rama:** `feat/sondeo-y-auditoria`
**Tipo:** `feat(sondeo)`

## Qué cambió

El repositorio pasa de tener solo un README a tener el pipeline de medición
completo: el recolector que corre cada 15 minutos, el auditor de calidad de las
series históricas, y el workflow que los ejecuta y commitea los datos.

Además, cuando la respuesta de la API no trae ningún timestamp, las columnas de
edad quedan vacías en lugar de registrarse como `0`.

## Por qué

El commit inicial dejó `sondeo.py` y el workflow sin versionar, y `calidad.py`
nunca se había escrito. Sin ese último script hay un defecto de datos que el
recolector no puede ver por sí solo: una plaza que actualiza su timestamp pero
no su precio pasa los tres filtros de calidad, se ve fresca y contamina las
mejores puntas. Detectarla exige comparar la serie histórica, no una corrida.

El cambio en las columnas de edad responde a una colisión concreta: en cada
corrida hay siempre al menos una plaza con edad exactamente `0`, porque es la
cotización más fresca del lote y define la referencia contra la que se miden
las demás. Usar ese mismo `0` para decir "no se pudo medir la edad" vuelve
indistinguibles los dos casos en un CSV que solo se escribe por append y que no
se puede reprocesar después.

## Alcance

Adentro:

- Recolector, auditor de calidad, workflow programado y `.gitignore`.
- Documentación de las columnas del CSV, los parámetros del modelo y las
  consultas de análisis, con los índices verificados contra el encabezado real.

Afuera, de forma deliberada:

- **`calidad.py` no filtra ni modifica nada.** Solo mide y reporta. Excluir una
  plaza marcada como congelada es una decisión de quien lee, no del script.
- **`data/raw/` guarda únicamente las plazas limpias.** Las descartadas
  conservan el motivo en `metricas.csv`, pero no su precio, así que no se puede
  reanalizar la serie con un umbral de filtro distinto. Queda documentado como
  limitación conocida en el README.
- Profundidad del libro, latencia, límites operativos y riesgo de contraparte
  siguen sin medirse.

## Historial de cambios

### 2026-09-17 — feat(sondeo)

- Se versionan `sondeo.py` y `.github/workflows/sondeo.yml`, que existían sin
  estar bajo control de versiones.
- Se agrega `calidad.py`: audita las series de `data/raw/` y clasifica cada
  plaza como CONGELADA, SOSPECHOSA, SIN DATOS u OK.
- La edad desconocida se registra como celda vacía y no como `0`, y la corrida
  lo avisa por consola.
- Se documenta `MIN_SPREAD_INTERNO`, que el README no mencionaba.
- Se corrige la descripción de `data/raw/`, que prometía un reanálisis con otros
  filtros que los datos guardados no permiten.
