# Recall web client

A Vite + React + TypeScript web app that talks to the existing Recall FastAPI
over HTTP + SSE. Slice 1: login + chat list + chat stream (markdown text only).

This is a **separate web app**, not react-native-web of `apps/mobile`. It
shares the same API contract and event types as the mobile client.

## Setup

```bash
cd apps/web
cp .env.example .env        # set VITE_API_URL + VITE_GOOGLE_CLIENT_ID
pnpm install
pnpm dev                    # http://localhost:5173
```

The API must be running (`./scripts/dev.sh api` on port 8000).

### Environment

- `VITE_API_URL` — API base URL (default `http://localhost:8000` for `pnpm dev`).
  Production builds (`pnpm build`) require a public `https://` URL.
- `VITE_GOOGLE_CLIENT_ID` — Google Identity Services web client ID. **Same**
  as the API `GOOGLE_CLIENT_ID` / mobile `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`.

### Google OAuth (owner ops, one-time)

Add the web origin to the OAuth client's **Authorized JavaScript origins** in
the Google Cloud Console:

- local: `http://localhost:5173`
- prod: your real web origin

Without this, the GIS token client will throw `Origin not allowed`.

### CORS

Add the web origin to `CORS_ORIGINS` in `apps/api/.env` (required for cookie
sessions — an empty value falls back to `*`, which cannot send credentials):

```
CORS_ORIGINS=https://app.recall.app,http://localhost:5173
```

The web origin and API must be same-site (e.g. sibling subdomains) so the
`SameSite=Lax` refresh cookie is sent on `fetch`. Mobile does not need to be
listed; it uses Bearer tokens, not cookies.

### Dev login

When the API has `DEV_AUTH_ENABLED=true`, the "Continue (dev)" button signs in
without Google — useful for local dev without a configured OAuth client.

## What's in slice 1

- Google Sign-In (GIS) + dev login
- Chat list (create / open)
- Chat view with SSE streaming (`start` / `token` / `status` / `stream_end` /
  `done` / `error`), stop (abort), regenerate
- Plain markdown rendering with GFM tables and images; JSON rich fences
  (sources, places, graph, chart, …) become a short human label, not a code dump
- Named source links under the reply (`search_sources` on `done`, or the
  trailing ` ```sources ` fence on history reload)
- Access token in memory; httpOnly refresh cookie + CSRF (`X-CSRF-Token`);
  reload bootstraps via `POST /auth/refresh`. Mobile stays Bearer + secure-store.

## Later slices (not yet)

- Rich fences (math, charts, Mermaid, sandboxed HTML preview)
- Memory, settings, attachments, image gen
- Lists and the language-learning product are not coming back (see chat-ux-bans)
- `packages/api-types` extracted from `lib/api/types.ts`
- Apple Sign-In on web (separate Services ID)
- Prod deploy (Cloudflare Pages or Fly)

## UX rules

Follows the mobile [chat-ux-bans](.cursor/rules/chat-ux-bans.mdc): no
"Recalled N memories" chip, no assistant Show more / Show less, no
model-fallback chips on assistant bubbles.
