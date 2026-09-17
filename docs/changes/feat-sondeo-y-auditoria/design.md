# Decisiones técnicas

## La edad desconocida se registra vacía, no como cero

**Contexto:** el filtro de antigüedad mide cada cotización contra la más fresca
de la propia respuesta. Si ninguna entrada trae el campo `time` no hay contra qué
medir, y el filtro no puede ejecutarse. La especificación original indicaba
registrar edad `0` en ese caso, con el argumento de que descartar todo el lote
haría que el script dejara de funcionar en silencio ante un cambio de contrato
de la API.

El problema es que `0` no es un valor disponible. Por construcción, en cada
corrida hay al menos una plaza con edad exactamente `0`: la más fresca del lote,
que es la referencia. Es un valor legítimo y frecuente.

**Decisión:** las plazas siguen entrando al análisis, pero la edad se registra
sin valor y las columnas correspondientes quedan vacías. La corrida lo informa
por consola y degrada el aviso de ventana abierta cuando la frescura no pudo
verificarse.

**Alternativas descartadas:**

- Registrar `0`, como indicaba la especificación — colisiona con un valor real y
  recurrente. Una vez escrito, el CSV es de solo anexado y no se puede
  reprocesar: la ambigüedad sería permanente.
- Descartar todas las plazas cuando falta el timestamp — es justamente lo que la
  especificación quería evitar. Un cambio de contrato de la API dejaría la serie
  vacía sin explicación.
- Agregar una columna booleana `edad_verificada` — sería redundante, porque el
  dato se deriva de que la columna de edad esté vacía. Dos representaciones del
  mismo hecho se terminan desincronizando.

**Consecuencias:** la distinción entre "medido en cero" y "no medido" queda
preservada en el dato y es consultable con una comparación contra celda vacía.
El costo es que una consulta numérica ingenua sigue tratando la celda vacía como
cero, así que la comprobación explícita es necesaria y queda documentada en el
README. El comportamiento se aparta de la letra de la especificación original,
aunque conserva su intención: el script no se detiene ante un cambio de contrato.

## La auditoría de calidad mide pero no filtra

**Contexto:** el recolector no puede detectar, desde una sola corrida, la plaza
que actualiza su timestamp sin mover el precio. Esa detección requiere comparar
la serie histórica. La opción inmediata sería excluir automáticamente a las
plazas sospechosas del cálculo.

**Decisión:** `calidad.py` vive separado del recolector, lee los datos ya
guardados y solo emite un informe. No modifica archivos ni altera qué plazas
entran al análisis.

**Alternativas descartadas:**

- Integrar la detección como un cuarto filtro dentro del recolector — obligaría
  a mantener estado histórico durante la recolección y, sobre todo, produciría
  exclusiones automáticas basadas en un criterio estadístico que todavía no está
  validado contra datos reales.

**Consecuencias:** las plazas marcadas como congeladas siguen entrando al
cálculo hasta que alguien decida lo contrario, lo cual mantiene la serie
comparable a lo largo del tiempo y deja la decisión de exclusión documentada
como acto deliberado. El costo es que el informe hay que leerlo: nada obliga a
mirarlo antes de sacar conclusiones.
