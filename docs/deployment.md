# Deployment Configuration

This slice is deployment-ready but does not provision cloud resources.

## Local managed server

`node scripts/local-web-server.mjs start` launches the local fixture dashboard as a detached, project-scoped process on `127.0.0.1:3000`. `status` verifies the stored PID, the exact Next.js command, and the `/api/health` response. Logs and runtime metadata stay under ignored `apps/web/.data/` files. The stop command refuses to signal a reused or unrelated PID.

The production build uses `.next-production`, while development uses `.next`, so running verification builds cannot overwrite a live development cache. The managed server is for local fixture use only; hosted deployment must use authenticated mode and real Supabase configuration.

## Supabase

1. Create a project and link the repository with the Supabase CLI.
2. Apply migrations and update `app_settings.owner_email` to the same lowercase value as `OWNER_EMAIL`.
3. Keep the `raw-artifacts` bucket private.
4. Add the production callback URL to Auth redirect URLs.

## Vercel

Use `apps/web` through the root `vercel.json`. Configure `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and `OWNER_EMAIL`. Never configure `TM_FIXTURE_MODE=true` in production. The service-role key is not a frontend variable.

## GitHub Actions

Scheduled ingestion requires encrypted `DATABASE_URL`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY` secrets. The workflow runs four times per day and never logs into or bids on the source site.
