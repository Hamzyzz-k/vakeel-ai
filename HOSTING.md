# Hosting Vakeel AI

Deploy the frontend and backend as separate services, both on free tiers
that need no card or billing details. The browser receives only
`VITE_API_BASE_URL`; the Gemini and Groq keys stay backend-only.

## Backend: Hugging Face Space (primary)

A free CPU Space gives 2 vCPU and 16GB RAM and only sleeps after 48 hours
without traffic, so the embedding model and vector retrieval run in
production. Render's free tier (512MB, sleeps after ~15 minutes) cannot hold
them and was measured taking 30-90s to wake.

`backend/Dockerfile` builds everything at image build time: CPU-only torch,
the `BAAI/bge-small-en-v1.5` embedder, the 22 verified India Code PDFs, the
product SQLite corpus, and its vector index. The first build takes several
minutes; nothing is fetched on the first query.

One-time setup (all free):

1. Create a Hugging Face account and a new Space: SDK **Docker**, hardware
   **CPU basic (free)**, visibility **Public** (the browser must reach it;
   the backend code is already public on GitHub, and keys live in secrets).
2. In the Space's **Settings > Variables and secrets**, add:
   - secrets: `GEMINI_API_KEY`, `GROQ_API_KEY`
   - variables:
     ```env
     DEPLOY_MODE=CLOUD
     CORS_ORIGINS=https://your-frontend.vercel.app
     TRUSTED_HOSTS=your-username-vakeel-ai.hf.space
     TRUSTED_PROXY_HOPS=1
     LLM_PROVIDER_ORDER=groq,gemini,ollama
     RATE_LIMIT_REQUESTS=20
     EXPOSE_PROVIDER_ERRORS=false
     ```
   The image already sets `DEPLOY_MODE=CLOUD`, which also turns on daily
   chat caps (25 per address, 100 in total per UTC day) and a 7-day expiry
   on cached answers. Override them with `DAILY_CHAT_LIMIT_PER_CLIENT`,
   `DAILY_CHAT_BUDGET` and `LLM_CACHE_TTL_DAYS` if needed.
3. Create a **fine-grained** Hugging Face access token (Settings > Access
   Tokens > Create new token > Fine-grained) whose only permission is
   write access to this one Space's repository. An account-wide write
   token would let anyone who obtained it overwrite every repository and
   Space you own.
4. In the GitHub repo's **Settings > Secrets and variables > Actions**, add
   the secret `HF_TOKEN` (that token) and the variable `HF_SPACE`
   (`your-username/vakeel-ai`). `.github/workflows/deploy-hf.yml` then
   pushes `backend/` to the Space on every push to `master` that touches
   it, or on demand from the Actions tab.
5. Optional: add the variable `BACKEND_HEALTH_URL`
   (`https://your-username-vakeel-ai.hf.space/api/v1/health`) to enable the
   daily keep-awake ping in `.github/workflows/keep-warm.yml`.

### Rate limiting behind the proxy

The rate limiter keys on the client address. Behind a platform proxy the
socket peer is the proxy, so `TRUSTED_PROXY_HOPS` tells it how many
`X-Forwarded-For` entries the platform itself appends. After the first chat
request, the Space logs show a line like
`X-Forwarded-For has 1 entry; TRUSTED_PROXY_HOPS=1`. For a request you sent
without your own `X-Forwarded-For`, the entry count is the platform's hop
count; set `TRUSTED_PROXY_HOPS` to it. Too low and users share buckets; too
high and clients can choose their own bucket.

### What is not persistent

Space disks reset on restart, so the LLM response cache starts empty after
each restart. The corpus and vector index are rebuilt into the image, so
they are always present.

## Backend: Render (legacy)

`render.yaml` still describes the previous Render deployment, with vector
retrieval disabled to fit 512MB. Keep it only until the Space is verified.

## Frontend: Vercel

Set the project root to `frontend`, build with `npm run build`, and publish
`frontend/dist`. Set:

```env
VITE_API_BASE_URL=https://your-username-vakeel-ai.hf.space
```

`frontend/vercel.json` provides SPA routing and baseline browser security
headers. The workspace pings `/api/v1/health` when it opens and shows a
"waking the server" notice if that is slow.

## Free-tier limits that matter

- Groq `openai/gpt-oss-120b`: 8,000 tokens/minute, 1,000 requests/day and
  **200,000 tokens/day** (hit during evaluation). That daily cap is the real
  ceiling: roughly 50 answers a day across all users. Quotas are per model,
  so `LLM_PROVIDER_ORDER` accepts `provider:model` entries; adding
  `groq:qwen/qwen3.8-27b` (or `groq:openai/gpt-oss-20b`) after `groq` adds
  a second free daily budget. Check answer quality before relying on a new
  model: the citation checks will strip what it can't support, but a weaker
  model leaves shorter answers. The support judge already runs on
  `openai/gpt-oss-20b` (`SUPPORT_JUDGE_PROVIDERS`) so it doesn't spend the
  answer model's budget.
  One query uses roughly 3.5K tokens, plus ~1-2K for the citation support
  judge (`SUPPORT_CHECKER=llm`), so about 1-2 queries a minute run at full
  speed; beyond that requests fall back to Gemini. `SUPPORT_CHECKER=lexical`
  drops the judge call if throughput matters more than citation precision.
- Gemini free tier: `gemini-3.6-flash` is limited to **20 requests per
  day** (confirmed from a live 429), so as a fallback it covers about ten
  queries a day. Lite models (`gemini-flash-lite-latest`,
  `gemini-3.5-flash-lite`) have their own, separate quotas; check the current
  numbers at https://ai.dev/rate-limit (no billing needed) and set
  `GEMINI_MODEL` to a lite model if the fallback runs dry. Never enable
  billing on the Google Cloud project; that removes the free tier.

## Release checks

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp ..\.pytest_release
.\.venv\Scripts\python.exe -m app.eval.product_quality

cd ..\frontend
npm ci
npm run build
```

`.github/workflows/ci.yml` runs the same tests and build on every push and
pull request.

Never commit `.env`, expose provider errors publicly, use wildcard CORS/host
settings, or deploy an empty corpus.
