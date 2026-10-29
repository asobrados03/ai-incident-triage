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
