# Desarrollo

Este documento cubre el entorno local, la configuración, las validaciones y la entrega. Para entender las capas y el
flujo de datos, consulta [architecture.md](architecture.md); para los conjuntos y las métricas, [evaluation.md](evaluation.md).

## Requisitos

- Python 3.11 o superior.
- Node 24 o superior (el frontend usa Vite + React + TypeScript).
- Opcional: Docker, para construir la imagen de la API.
- Opcional: Ollama, solo si quieres ejecutar el analizador semántico en lugar del backend `fake`.

## Instalación del backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
uvicorn backend.main:app --reload
```

La API queda en `http://127.0.0.1:8000`, la documentación OpenAPI está disponible en `/docs` y el health check público
en `/health`. SQLite usa por defecto una ruta absoluta en la raíz del proyecto (`incidents.db`) para no depender del
directorio desde el que se arranque Uvicorn. El backend de análisis por defecto es `fake`, por lo que este arranque no
necesita Ollama.

## Instalación del frontend

El frontend vive en `frontend/`:

```powershell
Set-Location frontend
npm install
npm run dev
```

El frontend usa `VITE_API_URL` como origen del backend y, si no se define, apunta a `http://127.0.0.1:8000` (sin
añadir `/api`). El servidor de desarrollo de Vite mantiene proxies para las rutas de la API, útiles si prefieres
servirlas por el mismo origen.

La base incluye Vite + React + TypeScript, Tailwind, componentes compatibles con shadcn/ui, TanStack Query, React
Router, react-hook-form, zod, Vitest, Testing Library, MSW, ESLint y Prettier. El código se organiza por `features/`
(`incidents`, `review`, `metrics`) y `shared/` (componentes y utilidades reutilizables); `src/api` sigue siendo el
cliente tipado único.

Rutas frontend disponibles:

- `/`: bandeja con filtros por estado y confianza, vista de pendientes priorizada por confianza baja y paginación.
- `/new`: creación con chips de componentes y errores 422 por campo.
- `/incidents/:id`: detalle, análisis, aviso de confianza baja y de Ollama, diff IA→humano y revisión con checklist de
  faltantes.
- `/metrics`: métricas con matriz de confusión y aviso de fiabilidad.
- `/users`: gestión de usuarios, solo `admin`.
- `/login`: autenticación.

La UI conoce el rol: `reader` no ve acciones de escritura y solo `admin` ve Usuarios. Una respuesta 401 limpia la
sesión local y redirige al acceso; si el backend informa `authenticated: false`, la app funciona en modo anónimo.

## Configuración

| Variable | Default | Uso |
|---|---|---|
| `APP_NAME` | nombre del proyecto | Título de FastAPI. |
| `DATABASE_URL` | SQLite local absoluta | URL SQLAlchemy; el MVP usa `create_all` más una migración aditiva ligera para columnas nuevas. |
| `ANALYZER_BACKEND` | `fake` | `fake` para desarrollo/tests o `ollama` explícito. |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Runtime local de Ollama. |
| `OLLAMA_MODEL` | `qwen2.5:14b` | Modelo Ollama (por ejemplo `qwen2.5:14b`, `qwen2.5:7b` o `qwen2.5:3b`). |
| `OLLAMA_TIMEOUT_SECONDS` | `180` | Timeout finito del adaptador. |
| `AUTH_USERS` | vacío | Semilla inicial `name:role:password,...` para la tabla `users`. Solo crea usuarios que falten; después la BD manda. Vacío no siembra nada. |
| `JWT_SECRET` | vacío | Secreto HS256; mínimo 32 caracteres para emitir y validar tokens. |
| `JWT_EXPIRATION_MINUTES` | `15` | Duración del access token (por defecto 15 minutos). |
| `REFRESH_TOKEN_EXPIRATION_DAYS` | `7` | Duración del refresh token de larga duración (por defecto 7 días). |
| `CORS_ORIGINS` | `http://localhost:5173` | Orígenes HTTP(S) separados por comas; `*` no está permitido. |
| `RETENTION_DAYS` | `90` | Antigüedad mínima de incidencias antes de poder purgarlas. |
| `AUDIT_RETENTION_DAYS` | `365` | Antigüedad mínima de registros de auditoría antes de purgarlos. |

La configuración puede definirse mediante variables de entorno o a través de un archivo `.env` en la raíz del proyecto
(se proporciona una plantilla en `.env.example`). La plantilla de ejemplo activa Ollama; si no defines
`ANALYZER_BACKEND`, el valor por defecto del código es `fake`.

El arranque valida backend, URL HTTP(S), modelo no vacío, timeout positivo, días de retención positivos, el formato de
`AUTH_USERS`, la longitud de `JWT_SECRET` y los orígenes CORS. Si `AUTH_USERS` está configurado, la autenticación se
exige aunque la tabla `users` esté vacía (fail-closed): no se degrada a modo anónimo por un fallo de bootstrap. El
comportamiento de autenticación, roles y revocación se detalla en [architecture.md](architecture.md#autenticación-y-autorización).

## Tests y validaciones

La suite usa el backend determinista y no realiza llamadas a Ollama. Estado actual: **148 tests backend** y **37 tests
frontend** (7 archivos).

```powershell
python -m pytest -q
Set-Location frontend
npm ci
npm run lint
npm run format:check
npm test -- --run
npm run build
```

- `npm run lint` ejecuta ESLint y `tsc -b` (type-check).
- `npm run format:check` comprueba el formato con Prettier.
- `npm test -- --run` ejecuta Vitest en modo no interactivo.
- `npm run build` compila TypeScript y genera el bundle de producción con Vite.

La evaluación offline se ejecuta aparte; consulta [evaluation.md](evaluation.md) para los comandos y las métricas.

## Demo reproducible

Con la API arrancada en otra terminal:

```powershell
.\scripts\demo.ps1
```

El script ejecuta health → create → analysis → GET → review, no contiene secretos y solo usa `curl.exe` y herramientas
incluidas en PowerShell. También acepta una URL alternativa y credenciales JWT opcionales:

```powershell
.\scripts\demo.ps1 -BaseUrl "http://localhost:8000"
.\scripts\demo.ps1 -Username "soporte" -Password $env:WRITER_PASSWORD
```

El token solo se usa para construir la cabecera `Authorization`; no se imprime ni se escribe en disco. Con la
autenticación deshabilitada (`AUTH_USERS` vacío) el script funciona sin credenciales.

## Docker

La imagen es multi-stage: un stage de `node:24-alpine` compila el frontend con Vite y el stage final de
`python:3.12-slim` sirve la API y el SPA desde el mismo origen. `VITE_API_URL` se fija en build-time con `/` para que
el cliente use rutas relativas.

```powershell
docker build -t triaje-api .
docker run --rm -p 8000:8000 -v "${PWD}/data:/data" `
  -e DATABASE_URL=sqlite:////data/incidents.db triaje-api
```

La interfaz queda en `http://127.0.0.1:8000/`, la documentación OpenAPI sigue en `/docs` y el health check en
`/health`. FastAPI sirve `frontend/dist` y devuelve `index.html` en las rutas del SPA (`/metrics`, `/incidents/:id`,
etc.) para que funcionen al refrescar o entrar directamente.

La imagen no incluye `incidents.db`, tests, `evaluation/`, `.venv`, artefactos locales ni secretos. El contenedor no
inicia Ollama: debe ejecutarse aparte. Si lo usas desde el contenedor, ajusta `OLLAMA_BASE_URL` a una dirección
alcanzable (por ejemplo `http://host.docker.internal:11434`; en Linux añade
`--add-host=host.docker.internal:host-gateway`). Si activas la autenticación, inyecta `AUTH_USERS` y `JWT_SECRET` con
`--env-file` o un gestor de secretos; no la incluyas en la imagen.

Si necesitas compilar el frontend contra otro origen de API, usa
`docker build --build-arg VITE_API_URL=https://api.example.com -t triaje-api .` y configura `CORS_ORIGINS` en la API.

PostgreSQL no se incorpora todavía: SQLite cubre el MVP local y evita añadir operación, driver y migraciones antes de
necesitar despliegue multiinstancia.

## Integración continua

GitHub Actions en `.github/workflows/ci.yml` separa dos jobs:

- **Backend:** instala el proyecto con `python -m pip install -e ".[test]"`, ejecuta `python -m pytest -q`, construye
  la imagen Docker y hace un smoke test del contenedor: `/health`, `/` y `/metrics` (fallback del SPA).
- **Frontend:** instala con `npm ci`, ejecuta `npm run lint`, `npm run format:check`, `npm test -- --run` y
  `npm run build`.

## Estructura del repositorio

```text
backend/            API FastAPI por capas (api, domain, services, infrastructure, analyzers, security)
frontend/           Aplicación Vite + React + TypeScript
evaluation/         runner.py, data/ y results/ para la evaluación offline
tests/backend/      Suite de pytest del backend
scripts/            Utilidades, incluida demo.ps1
docs/               Esta documentación
Dockerfile          Imagen multi-stage de API + frontend
pyproject.toml      Metadatos, dependencias y configuración de pytest
README.md           Presentación y puesta en marcha rápida
```
