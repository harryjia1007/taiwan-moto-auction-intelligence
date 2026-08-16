# Deployment Configuration

The hosted database foundation is provisioned. The authenticated web deployment and scheduled-ingestion secrets remain gated on the owner email and deployment-provider configuration described below.

## Local managed server

`node scripts/local-web-server.mjs start` launches the local fixture dashboard as a detached, project-scoped process on `127.0.0.1:3000`. `status` verifies the stored PID, the exact Next.js command, and the `/api/health` response. Logs and runtime metadata stay under ignored `apps/web/.data/` files. The stop command refuses to signal a reused or unrelated PID.

The production build uses `.next-production`, while development uses `.next`, so running verification builds cannot overwrite a live development cache. The managed server is for local fixture use only; hosted deployment must use authenticated mode and real Supabase configuration.

## Supabase

The dedicated hosted project `taiwan-moto-auction` was created in `ap-southeast-1` on 2026-08-15 with project ref `hdxlhxqlkdipqkwisjyd`. All committed migrations through `202608150004_public_live_listing_feed` are applied. Production seeding intentionally loaded only organizations, sources, access policies, endpoints and aliases; real Shwoo records are added by the scheduled publisher. Hosted verification reports a private `raw-artifacts` bucket, RLS on every public table, anonymous SELECT access only to the sanitized live-listing projection, and no anonymous access to operational tables.

Run `pnpm run doctor` before bootstrapping. The Supabase CLI packages PostgreSQL, Auth, Storage, local email, and the pgTAP runner as a Docker-compatible local stack; installing the JavaScript CLI alone does not create those services. Docker Desktop is the default, while OrbStack, Podman, and Colima are documented compatible alternatives.

1. Link the repository to project ref `hdxlhxqlkdipqkwisjyd` when CLI access is configured.
2. Update `app_settings.owner_email` to the same lowercase value as `OWNER_EMAIL` before enabling login.
3. Keep the `raw-artifacts` bucket private.
4. Add the production callback URL to Auth redirect URLs.

## Vercel

Use `apps/web` through the root `vercel.json`. Configure `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and `OWNER_EMAIL`. Never configure `TM_FIXTURE_MODE=true` in production. The service-role key is not a frontend variable.

## GitHub Actions

Scheduled public ingestion requires encrypted `SUPABASE_URL` and `SUPABASE_SECRET_KEY` repository secrets; the legacy `SUPABASE_SERVICE_ROLE_KEY` remains a fallback during migration. The GitHub-hosted workflow validates both before making a source request, then runs the MOJ centralized-auction publisher twice daily at 09:30 and 21:30 Asia/Taipei. Taipei Shwoo repeatedly completed health checks but timed out on every full discovery attempt from GitHub-hosted runner addresses on 2026-08-17; it is therefore excluded from the cloud schedule instead of producing a misleading failing run. Shwoo remains an approved adapter and was successfully published from the owner's Taiwan network; unattended local scheduling requires a separately approved Keychain-backed credential and a Mac that is awake with network access. The publisher's bounded discovery is also the source-health signal, avoiding a duplicate preflight request to a slow official endpoint; the standalone healthcheck command remains available for diagnostics. Each publisher preserves raw artifacts privately before updating the public projection. Judicial discovery is disabled because the current robots policy disallows automated paths; Administrative Enforcement remains human-assisted because of CAPTCHA; Government e-Procurement remains paused for authorization review. The workflow never logs into or bids on a source site.

An adapter being healthy does not prove the hosted schedule is operating. Release verification must check the latest GitHub Actions conclusion and confirm a matching `sync_runs` row, nonzero source metrics when official results exist, artifact metadata, snapshots and `last_successful_at`. Missing repository secrets are a deployment blocker, not a source outage.

Administrative Enforcement is intentionally excluded from unattended schedules because the official discovery form requires a human-completed CAPTCHA. After a human performs the official `汽機車` search, save the validated detail URLs in the ignored `.data/moj-enforcement-manifest.json` file and run `pnpm ingest:moj-enforcement`. This imports only official detail pages and attachments; it does not read, submit, reuse, or bypass the CAPTCHA.

The source dashboard must retain truthful readiness states. `PARTIAL` means the adapter is usable under its documented limits, not that nationwide discovery is complete. Only promote a source to `ACTIVE` after a successful real database sync, raw-artifact persistence, and an operator review of source metrics.

## Public portfolio boundary

The portfolio page at `harryjia.com/projects/taiwan-moto-auction` reads only `public_live_motorcycle_listings` with a publishable key. Operational tables, `/motorcycles`, `/sources`, private APIs, cached artifacts, evidence and full snapshots remain owner-only. Public cards link to the publisher's official page and load only official source-image URLs; they never receive private Storage paths or a service-role key.

The separate `database-tests.yml` workflow needs no project secrets. It starts an isolated Supabase stack on the GitHub runner, replays every migration and the seed, runs the committed pgTAP suite, reports status on failure, and always stops the stack. Seed assertions address the fixed sanitized seed identifiers instead of global row counts, so `pnpm db:test` remains valid after live ingestion adds records. This supplements local testing; it does not deploy or create a hosted Supabase project.
