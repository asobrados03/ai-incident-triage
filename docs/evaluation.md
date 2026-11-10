# Evaluación

La evaluación es offline y vive en `evaluation/`: `runner.py` ejecuta un analizador sobre un dataset JSON y calcula
métricas reproducibles. No depende de FastAPI ni de la API en marcha. Los tests del proyecto usan el backend
determinista y nunca llaman a Ollama.

Para el comportamiento de `FakeAnalyzer` y `OllamaAnalyzer`, consulta
[architecture.md](architecture.md#analizadores-fakeanalyzer-y-ollama). Para instalar el proyecto y ejecutar la suite,
consulta [development.md](development.md#tests-y-validaciones).

## Conjuntos de datos

Hay varios conjuntos con propósitos distintos:

- `evaluation/data/incidents.json`: 28 casos de desarrollo, usados para ajustar las reglas.
- `evaluation/data/incidents-holdout.json`: 12 casos del primer holdout. Se usó para detectar el fallo de credenciales,
  así que después de corregirlo ya no es una referencia ciega.
- `evaluation/data/incidents-regression.json`: 12 casos que encontraron falsos positivos durante esta iteración
  (“documento” interpretado como documentación, guías que mencionan configuración). Se conserva como regresión.
- `evaluation/data/incidents-holdout-v2.json`: 12 casos escritos después de los cambios y ejecutados una sola vez. Es la
  referencia más honesta de generalización de esta iteración.

## Comandos

```powershell
python -m evaluation
python -m evaluation --dataset evaluation/data/incidents-holdout-v2.json
python -m evaluation --dataset evaluation/data/incidents-regression.json
python -m evaluation --dataset evaluation/data/incidents-holdout.json
python -m evaluation --verbose
python -m evaluation --summary
python -m evaluation --summary --dataset evaluation/data/incidents-holdout-v2.json
python -m evaluation --backend fake --compare-with ollama --summary
```

`--verbose` imprime en `stderr` el resultado por caso y los campos que no coinciden. `--summary` imprime en `stderr` un
resumen legible (accuracy, macro-F1, calibración de confianza, errores por categoría esperada y principales
confusiones). En ambos casos el JSON de métricas permanece en `stdout` para poder redirigirlo. La salida se fuerza a
UTF-8. Si rediriges desde PowerShell y aparecen acentos corruptos, ejecuta antes
`[Console]::OutputEncoding = [Text.UTF8Encoding]::new()` (y lo mismo para `$OutputEncoding`); en pantalla no hace falta.

## Resultados del baseline `FakeAnalyzer`

Las métricas de calidad son reproducibles; solo varía la latencia. Una ejecución reciente del baseline `FakeAnalyzer`
produce:

| Conjunto | Casos | Category | Severity | Priority | Missing info | Confidence | Errores |
|---|---:|---:|---:|---:|---:|---:|---:|
| Desarrollo (ajuste) | 28 | 1.000 | 1.000 | 1.000 | 1.000 | 0.893 | 0 |
| Holdout original (ya no ciego) | 12 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0 |
| Regresión | 12 | 1.000 | 0.917 | 1.000 | 1.000 | 1.000 | 0 |
| Holdout v2 (ciego) | 12 | 1.000 | 0.917 | 0.917 | 1.000 | 0.917 | 0 |

## Métricas del JSON

Además de la accuracy, el JSON incluye:

- `category_macro_f1`, `severity_macro_f1` y `priority_macro_f1`.
- `per_class`: precisión, recall, F1 y soporte por clase.
- `confusion_matrix`: matriz esperado × predicho por campo.
- `missing_information_precision`, `missing_information_recall` y `missing_information_f1` en micro.
- `latency_ms_p50` y `latency_ms_p95`.
- `confidence_calibration`: para cada nivel (`low`, `medium`, `high`), número de casos, casos totalmente correctos y
  accuracy. Sirve para comprobar si la confianza declarada se corresponde con los aciertos reales.
- `errors_by_category`: número de fallos agrupados por la categoría esperada, para localizar qué clases concentran el
  error.

## Comparación entre backends

`--compare-with` ejecuta dos backends sobre el mismo conjunto y compara resultados. El backend de `--backend` es la
referencia y `--compare-with` el candidato; deben ser distintos. Imprime mejoras, empeoramientos, cambios entre fallos
y deltas de accuracy, macro-F1, latencia y errores. En este modo el JSON cambia de forma: incluye `baseline.metrics`,
`candidate.metrics`, `deltas` y `cases` (con `cases.detail` por caso: esperado, resultado y fallos de cada backend). Es
la forma reproducible de responder si Ollama mejora al baseline:

```powershell
python -m evaluation --backend fake --compare-with ollama --summary
```

Ese comando sí necesita Ollama levantado; los tests siguen sin llamar al LLM.

## Lectura del holdout v2

En el holdout v2, la categoría acierta 12/12 y los dos fallos son ilustrativos: “no está disponible” no activa la
criticidad porque la regla solo reconoce “no disponible”, y un bug sin señal léxica clara queda en confianza `low`
frente a `medium`. No se ajustaron las reglas después de ver ese resultado. En desarrollo, la confianza `medium` acierta
2/2 y `high` 23/26; los tres desacuerdos son casos etiquetados como `medium` que el motor considera `high`.

Un acierto de enum exige igualdad exacta. `missing_information` se sigue comparando como lista exacta para la accuracy,
pero las métricas de precisión/recall/F1 permiten distinguir entre olvidar un concepto y añadir uno de más. `summary` y
`justification` no se puntúan por similitud de texto libre.

El 1.000 de desarrollo es optimista porque esas reglas se ajustaron con ese conjunto. Los holdouts tienen 12 casos: un
solo fallo mueve la accuracy unos 8 puntos, así que los resultados deben leerse como una señal de robustez del
baseline, no como una estimación precisa. Para Ollama, con el runtime ya disponible:

```powershell
python -m evaluation --backend ollama
```

## Comparación real `fake` frente a `ollama`

Ejecutada el 30 de octubre de 2026 sobre `evaluation/data/incidents-holdout-v2.json` (12 casos), con:

- Modelo `qwen3.5:4b` (Q4_K_M, 4.2B) servido por Ollama en local.
- Equipo de desarrollo: Intel Core i7-1255U, 32 GB de RAM, gráficos Intel Iris Xe. La latencia depende del hardware.
- Comando:
  `python -m evaluation --backend fake --compare-with ollama --dataset evaluation/data/incidents-holdout-v2.json --summary`
- Artefactos: `evaluation/results/ollama-vs-fake-holdout-v2.json` (detalle por caso) y
  `evaluation/results/ollama-vs-fake-holdout-v2.txt` (resumen).

| Backend | Category | Severity | Priority | Missing info | Confidence | Macro-F1 cat / sev / prio | p50 | p95 | Errores | Casos completos |
|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|
| `fake` | 1.000 | 0.917 | 0.917 | 1.000 | 0.917 | 1.000 / 0.889 / 0.914 | 0.14 ms | 1.23 ms | 0 | 10/12 |
| `ollama` | 0.833 | 0.583 | 0.417 | 0.083 | 0.167 | 0.853 / 0.586 / 0.250 | 19 167.57 ms | 21 738.72 ms | 0 | 0/12 |

Deltas de Ollama respecto al fake: category `-0.167`, severity `-0.333`, priority `-0.500`, missing `-0.917`,
confidence `-0.750`; macro-F1 `-0.147 / -0.303 / -0.664`; p50 `+19 167.43 ms`; p95 `+21 737.49 ms`. De los 12 casos,
Ollama no mejora ninguno, empeora 10 y cambia otros 2 sin llegar a acertarlos completos. Dos ejecuciones consecutivas
dieron las mismas métricas de calidad; la latencia p50 varió entre 19.2 s y 22.4 s.

| Caso | Esperado (cat / sev / prio) | Ollama (cat / sev / prio) | Fallos |
|---|---|---|---|
| `invoice-download-permission` | bug / critical / urgent | bug / high / high | sev, prio, missing, conf |
| `form-values-not-persisted` | bug / high / high | bug / high / high | missing, conf |
| `filter-dropdown-missing` | bug / medium / medium | bug / medium / medium | missing, conf |
| `report-export-timeout` | performance / high / high | performance / high / high | missing, conf |
| `database-url-missing` | configuration / medium / high | configuration / critical / high | sev |
| `cors-header-not-configured` | configuration / medium / high | bug / high / high | cat, sev, missing, conf |
| `dark-theme-request` | feature / low / low | feature / low / medium | prio, missing, conf |
| `changelog-guide-outdated` | documentation / low / medium | documentation / medium / low | sev, prio, missing, conf |
| `delete-account-request` | feature / low / low | feature / low / medium | prio, missing, conf |
| `api-502-after-deploy` | bug / high / urgent | performance / critical / high | cat, sev, prio, missing, conf |
| `memory-growth-after-update` | performance / critical / urgent | performance / critical / high | prio, missing, conf |
| `search-results-outdated` | bug / medium / medium | bug / medium / high | prio, missing |

El patrón dominante no parece ser un problema de comprensión: Ollama acierta la categoría en 10 de 12 casos, pero no
sigue el contrato campo a campo:

- **`missing_information`:** añade datos faltantes en 11 de 12 casos. En `filter-dropdown-missing` llega a devolver una
  lista con `"Ninguna información faltante identificada en el reporte proporcionado."` en vez de `[]`. El prompt actual
  no define cuándo la lista debe quedar vacía ni limita su contenido a datos imprescindibles.
- **Confianza:** devuelve `medium` en 11 casos y `high` en 1, mientras que el esperado es `high` en 11 y `medium` en 1.
  Acierta el nivel en 2 de 12, pero ningún caso queda completamente correcto. La confianza no está calibrada contra el
  contrato.
- **Prioridad y severidad:** tiende a valores intermedios. Rebaja urgencias (`invoice`, `api-502` y `memory` pasan de
  `urgent` a `high`), sube peticiones `low` a `medium` (`dark-theme`, `delete-account`) y baja documentación `medium` a
  `low` (`changelog`). En severidad acierta 7 de 12.
- **Categoría:** es el campo que mejor resuelve (10 de 12). Falla donde los conceptos se solapan:
  `cors-header-not-configured` pasa de `configuration` a `bug` y `api-502-after-deploy` de `bug` a `performance`.
- **Latencia:** unos 19 s por caso en mediana y 22 s en p95, frente a 0.14 ms y 1.23 ms del fake. Es un coste relevante
  incluso si la calidad fuera equivalente.

La lectura honesta es que el adaptador actual de Ollama no compite con el baseline en este conjunto. No se cambió el
prompt ni las reglas después de ver estos resultados: hacerlo sobre el holdout v2 lo convertiría en un conjunto de
ajuste. El siguiente paso razonable es definir una rúbrica explícita (categorías, política de severidad/prioridad,
cuándo `missing_information` va vacío y cómo calibrar `confidence`), añadir ejemplos y validarla sobre un holdout nuevo
o con validación cruzada. Solo tendría sentido promover Ollama a backend por defecto si supera al fake con un coste de
latencia aceptable.

Limitaciones de esta comparación: 12 casos (un fallo mueve la accuracy unos 8 puntos), un único modelo y cuantización,
un único equipo, sin intervalos de confianza y con un prompt mínimo sin rúbrica ni ejemplos. El 10/12 del fake tampoco
es una estimación neutral: sus reglas se ajustaron con otros conjuntos. Los resultados describen este adaptador y este
conjunto, no el techo del modelo.

## Benchmark y evaluación comparativa de LLMs locales

Se evaluaron múltiples modelos LLM locales ejecutados sobre Ollama con inferencia en CPU en el hardware de desarrollo
de referencia (Intel Core i7-1255U, 32 GB RAM, gráficos Intel Iris Xe):

| Modelo | Parámetros / RAM | Latencia media (CPU) | Exactitud semántica | Idioma / Redacción | Caso de uso recomendado |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`qwen2.5:14b`** *(Default)* | 14B / ~9.0 GB | **~35 – 42 s** | **Máxima (100% acierto categórico)** | 100% español técnico | **Producción / Máxima precisión analítica** y mínimo retrabajo humano. |
| **`qwen2.5:7b`** | 7B / ~4.7 GB | **~20 – 25 s** | Alta (ligero sesgo a *performance*) | 100% español fluido | **Baja latencia** / mayor frecuencia de peticiones. |
| **`deepseek-r1:7b`** | 7B / ~4.7 GB | **~70 – 110 s** | Buena (sobreanálisis en casos simples) | Mixto (inglés/español) | Tareas de razonamiento deductivo explícito (`<think>`). |
| **`qwen3.5:4b`** | 4.2B / ~3.3 GB | **~50 – 60 s** | Moderada | Español | Modelo ligero previo de evaluación inicial. |

**Conclusiones de la comparativa:**

- `qwen2.5:14b` es el modelo configurado por defecto para Ollama en el backend (`backend/infrastructure/config.py` y
  `.env`), ya que elimina errores de clasificación entre fallos de código (`bug`), configuración (`configuration`) y
  degradación de rendimiento (`performance`), además de identificar exhaustivamente campos ausentes
  (`steps_to_reproduce`, `actual_behavior`, `environment`).
- Para entornos que prioricen velocidad sobre exhaustividad analítica, `qwen2.5:7b` reduce el tiempo de respuesta a la
  mitad con excelente solidez.

## Regenerar los artefactos

```powershell
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Text.UTF8Encoding]::new()
python -m evaluation --backend fake --compare-with ollama `
  --dataset evaluation/data/incidents-holdout-v2.json --summary `
  2> evaluation/results/ollama-vs-fake-holdout-v2.txt `
  > evaluation/results/ollama-vs-fake-holdout-v2.json
```

## Limitaciones de la evaluación

- **Calidad y cobertura del análisis:** la evaluación sigue basándose en conjuntos pequeños y etiquetados manualmente.
  El holdout v2 tiene 12 casos, por lo que un solo fallo cambia la accuracy aproximadamente ocho puntos; además, el
  conjunto de desarrollo se utilizó para ajustar las reglas. Hace falta ampliar los casos, medir el acuerdo entre
  etiquetadores, incorporar ejemplos reales anonimizados y validar los cambios en un holdout nuevo o mediante
  validación cruzada.
- **Límites del `FakeAnalyzer`:** es un baseline de reglas determinista y explicable, no un sistema de comprensión
  semántica. Puede fallar ante formulaciones nuevas, ambigüedad o señales de impacto implícitas, y su `confidence`
  todavía no está calibrada con suficiente volumen. Deben añadirse reglas solo cuando estén respaldadas por datos y
  regresiones, no por ajustar repetidamente el mismo holdout.
- **Backend de análisis por defecto y trade-offs de Ollama:** `FakeAnalyzer` se mantiene como backend por defecto para
  garantizar tests instantáneos y desarrollo reproducible sin dependencias externas. Para inferencia semántica con LLMs
  locales, `qwen2.5:14b` ofrece máxima precisión y redacción técnica en español (eliminando errores de clasificación en
  producción), asumiendo una latencia de ~35–42 s por ticket en CPU de desarrollo. Para escenarios de alta concurrencia
  o menor latencia, `qwen2.5:7b` (~20–25 s) o modelos más ligeros como `qwen2.5:3b` son alternativas recomendables.
- **Utilidad de la revisión humana:** `missing_information` se evalúa con listas exactas y micro-F1, pero una
  coincidencia de métricas no garantiza que las preguntas sean accionables. Conviene medir la utilidad de las preguntas,
  registrar feedback de las personas revisoras y recalibrar las propuestas a partir de las correcciones acumuladas.
