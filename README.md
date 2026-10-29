# Sistema inteligente de triaje de incidencias

API base para registrar incidencias y consultarlas antes de incorporar el análisis automático.

## Instalación

Se requiere Python 3.11 o superior:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

La configuración se realiza mediante variables de entorno:

- `APP_NAME`: nombre de la aplicación.
- `DATABASE_URL`: URL SQLAlchemy de la base de datos. Por defecto apunta de forma absoluta a `incidents.db` en la raíz del proyecto, independientemente del directorio desde el que se arranque Uvicorn.

## Ejecución

```powershell
uvicorn app.main:app --reload
```

La API estará disponible en `http://127.0.0.1:8000` y la documentación interactiva en `/docs`.

## Tests

```powershell
pytest
```

Las incidencias se almacenan en SQLite. Se crean en estado `created` y el análisis se solicita explícitamente:

```powershell
curl -X POST http://127.0.0.1:8000/incidents/{incident_id}/analysis
```

El análisis actual usa `FakeAnalyzer`, un adaptador determinista y explicable para desarrollo y tests. Persiste el
resultado en `triage_results` y cambia el estado de la incidencia de `created` a `analyzing` y finalmente
a `analyzed`. Si ya existe un análisis, el endpoint devuelve `409 Conflict`. La integración con un LLM o proveedor
externo se añadirá en otra fase. El archivo local `incidents.db` se ignora en Git.

## Revisión humana

Después de analizar una incidencia, se puede aceptar la propuesta o corregir parcialmente sus campos:

```powershell
curl.exe -X PATCH http://127.0.0.1:8000/incidents/{incident_id}/triage `
  -H "Content-Type: application/json" `
  --data-raw '{"severity":"critical","priority":"urgent","review_comment":"Impacto confirmado"}'
```

La respuesta conserva los campos actuales de `triage` como propuesta original de IA y añade `triage.review.final`
con los valores finales revisados, además de `reviewed`, `source`, `review_comment` y `reviewed_at`. El estado pasa
de `analyzed` a `reviewed`. Un comentario sin correcciones acepta la propuesta sin cambios; una petición vacía,
una incidencia sin análisis o una revisión duplicada se rechazan. En los dos últimos casos se devuelve `409`.

## Analizador LLM local opcional

El proyecto puede usar Ollama como runtime local con el modelo `qwen3.5:4b`. `FakeAnalyzer` sigue siendo el valor
por defecto y es el backend usado por los tests; pytest no realiza llamadas reales a Ollama.

Instala Ollama en Windows y descarga el modelo:

```powershell
irm https://ollama.com/install.ps1 | iex
ollama serve
ollama pull qwen3.5:4b
ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

Configura el backend antes de arrancar la API:

```powershell
$env:ANALYZER_BACKEND = "ollama"
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:OLLAMA_MODEL = "qwen3.5:4b"
$env:OLLAMA_TIMEOUT_SECONDS = "60"
uvicorn app.main:app --reload
```

El adaptador solicita una respuesta JSON y la valida estrictamente contra `TriageResult`. Si Ollama no está
disponible o devuelve una respuesta inválida, la API responde `502` y marca el análisis como `analysis_failed`;
si supera el timeout, responde `504`. La aplicación no inicia Ollama ni descarga modelos automáticamente.

## Evaluación offline

El dataset versionado `eval/data/incidents.json` contiene ocho incidencias de referencia con etiquetas esperadas.
La evaluación compara únicamente campos estructurados: `category`, `severity` y `priority` requieren igualdad exacta;
`missing_information` requiere igualdad exacta de la lista; y `confidence` se compara como indicador de incertidumbre.
También informa respuestas válidas, errores y tasa de errores. No puntúa `summary` o `justification` por similitud de
texto libre, por lo que el resultado no representa una evaluación completa de calidad lingüística.

Ejecuta el baseline determinista sin Ollama:

```powershell
python -m app.evaluation
```

El backend fake es el predeterminado y está diseñado como baseline estable de plumbing, no como medida de calidad
del LLM. Para evaluar explícitamente con Ollama, con el servidor y modelo ya disponibles:

```powershell
$env:ANALYZER_BACKEND = "ollama"
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:OLLAMA_MODEL = "qwen3.5:4b"
python -m app.evaluation --backend ollama
```

Esta ejecución puede producir resultados variables y no se mezcla con pytest. Los tests usan `FakeAnalyzer` o
analizadores locales controlados y nunca hacen llamadas reales a Ollama.
