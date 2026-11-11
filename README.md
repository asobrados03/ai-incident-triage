# Sistema inteligente de triaje de incidencias

API y frontend para registrar incidencias, generar una propuesta de triaje y permitir que una persona la acepte o la
corrija. El proyecto es un MVP demostrable: mantiene separadas la entrada, el análisis, la persistencia y la revisión
humana, y añade autenticación con usuarios persistidos y contraseñas Argon2id, JWT versionados, autorización por roles,
gestión administrativa de usuarios, auditoría y retención de datos. No incluye todavía RAG ni agentes.

Estados principales: `created → analyzing → analyzed → reviewed`. Si el análisis falla, el estado es
`analysis_failed`.

## Puesta en marcha rápida

Requiere Python 3.11 o superior y Node 24 o superior.

Backend:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-deps -e .
uvicorn backend.main:app --reload
```

La API queda en `http://127.0.0.1:8000`, la documentación OpenAPI en `/docs` y el health check público en `/health`.
La plantilla `.env` usa el backend `fake`, así que no necesitas Ollama para arrancar, y siembra los usuarios de ejemplo:
`admin` / `admin-password-12345678`, `soporte` / `soporte-pass-12345678` y `auditor` / `auditor-pass-12345678`.
Cambia esas credenciales antes de exponer la API fuera de localhost. Las versiones están fijadas en `requirements.lock`;
si cambias `pyproject.toml`, regenéralo con uv según [Desarrollo](docs/development.md).

Frontend, en otra terminal:

```powershell
Set-Location frontend
npm install
npm run dev
```

El frontend usa `VITE_API_URL` como origen del backend y, si no se define, apunta a `http://127.0.0.1:8000`.

Para comprobar la instalación:

```powershell
python -m pytest -q
Set-Location frontend
npm run lint
npm test -- --run
npm run build
```

Estado actual: **151 tests backend** y **37 tests frontend** (7 archivos). La suite no realiza llamadas a Ollama.

## Documentación

- [Arquitectura](docs/architecture.md): flujo general, capas, autenticación, API, auditoría, retención y analizadores.
- [Desarrollo](docs/development.md): instalación detallada, configuración, tests, lint, demo, Docker y CI.
- [Evaluación](docs/evaluation.md): datasets, métricas, holdouts y comparación entre `FakeAnalyzer` y Ollama.

## Licencia

MIT. Consulta [LICENSE](LICENSE).
