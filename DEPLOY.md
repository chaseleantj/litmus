# Deploying Litmus to DigitalOcean

One container serves everything: FastAPI handles `/api/*` and serves the built Svelte app at `/`. State is a single SQLite file, so the deployment needs a persistent disk.

## Recommended: small droplet + Docker

DO App Platform has an ephemeral filesystem — the SQLite database would be wiped on every deploy. A $6/mo droplet with a Docker volume is the simplest fit.

1. Create a droplet (Docker image from the DO marketplace, smallest size).
2. Copy the repo to the droplet (git clone or `scp`).
3. Set the key and start:

   ```
   export OPENROUTER_API_KEY=sk-or-...
   docker compose up -d --build
   ```

4. App is on port 8000. Put it behind Caddy or nginx for TLS, e.g. Caddy with `reverse_proxy localhost:8000`.

The database persists in the `app-data` Docker volume across rebuilds. Back it up with:

```
docker compose cp app:/app/backend/data/app.db ./backup-app.db
```

## Alternative: App Platform

Works if you accept that examples reset to the seed file on each deploy, or you move the DB to DO Managed Postgres later. Point App Platform at the repo's Dockerfile, set `OPENROUTER_API_KEY` as an encrypted env var, HTTP port 8000.

## Local run (production build)

```
docker compose up --build
```

or without Docker: build the frontend (`npm run build` in frontend/), then run the backend (`uvicorn app.main:app` in backend/) — it serves `frontend/dist` automatically.
