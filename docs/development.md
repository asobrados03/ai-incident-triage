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
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-deps -e .
uvicorn backend.main:app --reload
```

La API queda en `http://127.0.0.1:8000`, la documentación OpenAPI está disponible en `/docs` y el health check público
en `/health`. SQLite usa por defecto una ruta absoluta en la raíz del proyecto (`incidents.db`) para no depender del
directorio desde el que se arranque Uvicorn. El backend de análisis por defecto es `fake`, por lo que este arranque no
necesita Ollama.

`requirements-dev.lock` fija las dependencias de desarrollo (runtime, test y herramientas) con hashes; para un entorno
solo de ejecución usa `requirements.lock`. Instalar el proyecto con `--no-deps` evita que pip vuelva a resolver
versiones. Si solo necesitas un entorno rápido y no te importa la reproducibilidad,
`python -m pip install -e ".[test,dev]"` sigue funcionando.

## Lock de dependencias

Hay dos locks generados con [uv](https://docs.astral.sh/uv/) `0.13.7` en modo universal: el mismo archivo sirve en
Windows, macOS y Linux (por ejemplo, `uvloop` solo se instala fuera de Windows).

- `requirements.lock`: solo runtime. Es el que usa la imagen Docker.
- `requirements-dev.lock`: runtime + extras `test` y `dev` (pytest, pytest-cov, Ruff y mypy). Es el que usa la CI y el
  entorno local de desarrollo.

```powershell
python -m pip install "uv==0.13.7"
uv pip compile --universal --generate-hashes pyproject.toml -o requirements.lock
uv pip compile --universal --extra test --extra dev --generate-hashes pyproject.toml -o requirements-dev.lock
```

Reglas:

- Si cambias las dependencias en `pyproject.toml`, regenera **los dos** locks en el mismo cambio.
- Instala con `python -m pip install --require-hashes -r requirements-dev.lock` en desarrollo, o
  `-r requirements.lock` si solo necesitas runtime.
- No edites los locks a mano: la cabecera y los hashes los genera uv.
- La CI recompila ambos y falla si no coinciden, así que un `pyproject.toml` sin locks actualizados no pasa.

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
sesión local y redirige al acceso; si el backend informa `authenticated: false` (bootstrap anónimo habilitado), la app
funciona en modo anónimo.

## Configuración

| Variable | Default | Uso |
|---|---|---|
| `APP_NAME` | nombre del proyecto | Título de FastAPI. |
| `DATABASE_URL` | SQLite local absoluta | URL SQLAlchemy; el MVP usa `create_all` más una migración aditiva ligera para columnas nuevas. |
| `ANALYZER_BACKEND` | `fake` | `fake` para desarrollo/tests o `ollama` explícito. |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Runtime local de Ollama. |
| `OLLAMA_MODEL` | `qwen3.5:4b` | Modelo Ollama; el valor por defecto es el único medido en `evaluation/results/`. Acepta cualquier etiqueta instalada. |
| `OLLAMA_TIMEOUT_SECONDS` | `180` | Timeout finito del adaptador. |
| `AUTH_USERS` | vacío | Semilla inicial `name:role:password,...` para la tabla `users`. Solo crea usuarios que falten; después la BD manda. Vacío no siembra nada. |
| `JWT_SECRET` | vacío | Secreto HS256; mínimo 32 caracteres para emitir y validar tokens. |
| `JWT_EXPIRATION_MINUTES` | `15` | Duración del access token (por defecto 15 minutos). |
| `REFRESH_TOKEN_EXPIRATION_DAYS` | `7` | Duración del refresh token de larga duración (por defecto 7 días). |
| `LOGIN_MAX_ATTEMPTS` | `5` | Intentos fallidos permitidos por usuario e IP dentro de la ventana antes de responder `429`. |
| `LOGIN_WINDOW_SECONDS` | `300` | Duración en segundos de la ventana fija del limitador de login. |
| `ALLOW_ANONYMOUS_BOOTSTRAP` | `false` | Con `true`, permite acceso anónimo con rol `admin` cuando `AUTH_USERS` está vacío y la tabla `users` no tiene filas. Solo para demos locales; en producción debe quedar en `false`. |
| `CORS_ORIGINS` | `http://localhost:5173` | Orígenes HTTP(S) separados por comas; `*` no está permitido. |
| `RETENTION_DAYS` | `90` | Antigüedad mínima de incidencias antes de poder purgarlas. |
| `AUDIT_RETENTION_DAYS` | `365` | Antigüedad mínima de registros de auditoría antes de purgarlos. |

La configuración puede definirse mediante variables de entorno o a través de un archivo `.env` en la raíz del proyecto
(se proporciona una plantilla en `.env.example`). La plantilla usa `ANALYZER_BACKEND=fake` para arrancar sin
dependencias; descomenta `ollama` cuando tengas el runtime local disponible.

El arranque valida backend, URL HTTP(S), modelo no vacío, timeout positivo, días de retención positivos, el formato de
`AUTH_USERS`, la longitud de `JWT_SECRET` y los orígenes CORS. La autenticación es fail-closed por defecto: si no hay
`AUTH_USERS` ni usuarios persistidos, los endpoints protegidos devuelven `401`. El acceso anónimo con rol `admin` solo
se habilita explícitamente con `ALLOW_ANONYMOUS_BOOTSTRAP=true` para demos locales; el arranque registra un aviso
cuando ese modo está activo. Si `AUTH_USERS` está configurado, la autenticación se exige aunque la tabla `users` esté
vacía. El comportamiento de autenticación, roles y revocación se detalla en
[architecture.md](architecture.md#autenticación-y-autorización).

## Tests y validaciones

La suite usa el backend determinista y no realiza llamadas a Ollama. Estado actual: **151 tests backend** (131 en
`backend/tests` y 20 en `evaluation/tests`) y **37 tests frontend** (7 archivos).

```powershell
python -m pip install "ruff==0.17.4" "mypy==2.4.1"
python -m ruff check backend evaluation
python -m ruff format --check backend evaluation
python -m mypy
python -m pytest -q --cov --cov-report=term-missing
Set-Location frontend
npm ci
npm run lint
npm run format:check
npm test -- --run
npm run build
```

- `python -m ruff check backend evaluation` ejecuta el lint de Python (configuración en `pyproject.toml`).
- `python -m ruff format --check backend evaluation` comprueba el formato; para aplicarlo, quita `--check`.
- `python -m mypy` comprueba los tipos de `backend` y `evaluation` con `disallow_untyped_defs` y `warn_return_any`;
  el resto de opciones también está en `pyproject.toml`.
- `python -m pytest -q --cov --cov-report=term-missing` ejecuta la suite con cobertura de `backend` y `evaluation`. El
  umbral mínimo es **90%** (`fail_under`) y la configuración vive en `pyproject.toml`.
- Los tests viven en `backend/tests/` y `evaluation/tests/`, junto al código que prueban, igual que en el frontend.
  Quedan fuera de la imagen Docker (`.dockerignore`), de la distribución instalada (`setuptools`), de la cobertura
  (`omit`) y del type-check (`mypy.exclude`).
- Pytest usa `--import-mode=importlib` (en `addopts`). Con dos raíces de tests, da a cada módulo un nombre único por
  ruta y evita que dos archivos con el mismo nombre colisionen en la recolección.
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

El token solo se usa para construir la cabecera `Authorization`; no se imprime ni se escribe en disco. Sin
`AUTH_USERS`, el script requiere `ALLOW_ANONYMOUS_BOOTSTRAP=true` para ejecutarse sin credenciales.

## Docker

La imagen es multi-stage: un stage de `node:24-alpine` compila el frontend con Vite y el stage final de
`python:3.12-slim` sirve la API y el SPA desde el mismo origen. `VITE_API_URL` se fija en build-time con `/` para que
el cliente use rutas relativas.

```powershell
docker build -t triaje-api .
docker run --rm -p 8000:8000 -v triaje-data:/data triaje-api
```

La imagen define `DATABASE_URL=sqlite:////data/incidents.db`. El volumen es obligatorio para conservar incidencias y
usuarios: sin él, el contenedor escribe en su capa efímera y los datos desaparecen al recrearlo. Se recomienda un
volumen nombrado porque el proceso corre como usuario `app` (UID 10001); si prefieres un bind mount en Linux, ajusta
los permisos del directorio (`chown -R 10001:10001 ./data`). La imagen declara además un `HEALTHCHECK` contra `/health`.

La interfaz queda en `http://127.0.0.1:8000/`, la documentación OpenAPI sigue en `/docs` y el health check en
`/health`. FastAPI sirve `frontend/dist` y devuelve `index.html` en las rutas del SPA (`/metrics`, `/incidents/:id`,
etc.) para que funcionen al refrescar o entrar directamente.

La imagen no incluye `incidents.db`, tests, `evaluation/`, `.venv`, artefactos locales ni secretos. El contenedor no
inicia Ollama: debe ejecutarse aparte. Si lo usas desde el contenedor, ajusta `OLLAMA_BASE_URL` a una dirección
alcanzable (por ejemplo `http://host.docker.internal:11434`; en Linux añade
`--add-host=host.docker.internal:host-gateway`). La imagen arranca en modo fail-closed: sin `AUTH_USERS` y sin usuarios
en la BD, los endpoints protegidos devuelven `401`. Para el primer arranque inyecta `AUTH_USERS` y `JWT_SECRET` con
`--env-file` o un gestor de secretos; no los incluyas en la imagen. `ALLOW_ANONYMOUS_BOOTSTRAP=true` queda reservado a
demos locales.

Si necesitas compilar el frontend contra otro origen de API, usa
`docker build --build-arg VITE_API_URL=https://api.example.com -t triaje-api .` y configura `CORS_ORIGINS` en la API.

PostgreSQL no se incorpora todavía: SQLite cubre el MVP local y evita añadir operación, driver y migraciones antes de
necesitar despliegue multiinstancia.

## Integración continua

GitHub Actions en `.github/workflows/ci.yml` separa dos jobs:

- **Backend:** instala las versiones fijadas de `requirements-dev.lock` con `--require-hashes`, comprueba que ambos locks
  están al día, ejecuta el lint y el formato con Ruff, el type-check con mypy y la suite con cobertura (`--cov`, umbral
  90%), construye la imagen Docker y hace un smoke test del contenedor: `/health`, `/`, `/metrics` (fallback del SPA) y
  `401` en `/incidents` sin credenciales.
- **Frontend:** instala con `npm ci`, ejecuta `npm run lint`, `npm run format:check`, `npm test -- --run` y
  `npm run build`.

## Estructura del repositorio

```text
backend/            API FastAPI por capas (api, domain, services, infrastructure, analyzers, security)
backend/tests/      Suite de pytest del backend, junto al código que prueba
frontend/           Aplicación Vite + React + TypeScript
evaluation/         runner.py, data/ y results/ para la evaluación offline
evaluation/tests/   Suite de pytest de la evaluación offline
scripts/            Utilidades, incluida demo.ps1
docs/               Esta documentación
Dockerfile          Imagen multi-stage de API + frontend
pyproject.toml      Metadatos, dependencias y configuración de pytest, Ruff y mypy
requirements.lock      Versiones fijadas con hashes para runtime (imagen Docker)
requirements-dev.lock  Versiones fijadas con hashes para CI y desarrollo (test + herramientas)
README.md           Presentación y puesta en marcha rápida
```
