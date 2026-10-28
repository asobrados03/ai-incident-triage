# Sistema inteligente de triaje de incidencias

API base para registrar incidencias y consultarlas antes de incorporar el análisis automático.

## Instalación

Se requiere Python 3.11 o superior:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

La configuración se realiza mediante variables de entorno. Actualmente se admite `APP_NAME` para cambiar el nombre de la aplicación.

## Ejecución

```powershell
uvicorn app.main:app --reload
```

La API estará disponible en `http://127.0.0.1:8000` y la documentación interactiva en `/docs`.

## Tests

```powershell
pytest
```

Las incidencias se almacenan en memoria en esta primera fase. Se crean en estado `created`; el análisis explícito y el resto del flujo de triaje quedan para fases posteriores.
