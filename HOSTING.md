# Hosting Vakeel AI

Deploy the frontend and backend as separate services. The browser receives
only `VITE_API_BASE_URL`; Gemini and Groq keys remain backend-only.

## Backend

Build from `backend/Dockerfile`. The image downloads the four official India
Code PDFs and builds a product-only SQLite corpus during the image build.
Vector retrieval is disabled in this baseline image because the embedding
model is intentionally local-only; BM25, direct statute routing, citation
verification, and all safety gates remain active.

Required production environment variables:

```env
DEPLOY_MODE=CLOUD
CORS_ORIGINS=https://your-frontend.example
TRUSTED_HOSTS=your-api.example
GEMINI_API_KEY=...
GROQ_API_KEY=...
LLM_PROVIDER_ORDER=gemini,groq,ollama
RATE_LIMIT_REQUESTS=20
RATE_LIMIT_WINDOW_SECONDS=60
EXPOSE_PROVIDER_ERRORS=false
USE_GPU=false
ENABLE_VECTOR_RETRIEVAL=false
ENABLE_CROSS_ENCODER=false
```

Use `/api/v1/health` as the platform health check. Run one process per
container: SQLite and the in-memory rate limiter are single-instance design
choices. For horizontal scaling, move the corpus to Postgres and rate-limit
state to Redis or an API gateway first.

## Frontend

Set the project root to `frontend`, build with `npm run build`, and publish
`frontend/dist`.

```env
VITE_API_BASE_URL=https://your-api.example
```

`frontend/vercel.json` and `frontend/public/_headers` provide SPA routing and
baseline browser security headers. Replace both example domains above with the
real deployed origins before the first public release.

## Release checks

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp ..\.pytest_release
.\.venv\Scripts\python.exe -m app.eval.product_quality

cd ..\frontend
npm ci
npm run build
```

Never commit `.env`, expose provider errors publicly, use wildcard CORS/host
settings, or deploy an empty corpus. Free model quotas are still abuse targets;
put a platform-level rate limit in front of the included process limiter when
the demo becomes public.
