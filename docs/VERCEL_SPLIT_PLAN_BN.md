# Buykori Vercel Split Plan

## Final domain structure

```txt
buykori.app              -> Marketing website on Vercel
www.buykori.app          -> Marketing website on Vercel
client.buykori.app       -> Client portal frontend on Vercel
admin.buykori.app        -> Admin portal frontend on Vercel
api.buykori.app          -> Current FastAPI backend/server
track.buykori.app        -> Optional tracking endpoint alias
```

## Phase 1: Marketing website

The marketing website is now prepared in:

```txt
marketing-site/
```

Deploy this folder to Vercel and connect:

```txt
buykori.app
www.buykori.app
```

This improves landing page load speed because Vercel serves static assets from CDN.

## Phase 2: Backend API domain

Keep FastAPI on the current backend host for event ingestion, workers, database, retries and platform forwarding.

Connect:

```txt
api.buykori.app
```

The plugin event endpoint should be:

```txt
https://api.buykori.app/api/v1/events
```

Optional future tracking alias:

```txt
https://track.buykori.app/api/v1/events
```

## Phase 3: Client and admin portals

Initial split frontends are now prepared in:

```txt
client-portal/
admin-portal/
```

Create two separate Vercel projects:

```txt
client-portal root -> client.buykori.app
admin-portal root  -> admin.buykori.app
```

Both frontends call:

```txt
https://api.buykori.app
```

Current client auth model:

```txt
client-portal -> public email/password signup and login
client-portal -> secure HttpOnly client session cookie
admin-portal  -> sends X-Admin-API-Key to admin JSON APIs for now
```

Email verification is intentionally deferred. New users can sign up and inspect the dashboard immediately; the workspace starts with a small free quota and platform delivery disabled until setup is completed.

The old FastAPI-rendered HTML routes remain available during migration:

```txt
/api/v1/client
/api/v1/client/dashboard
/api/v1/admin
```

## DNS checklist

Use exact DNS targets from Vercel and your backend provider.

Common setup:

```txt
buykori.app          -> Vercel apex target
www.buykori.app      -> Vercel CNAME target
client.buykori.app   -> Vercel CNAME target, later
admin.buykori.app    -> Vercel CNAME target, later
api.buykori.app      -> backend provider DNS target
track.buykori.app    -> backend provider DNS target, optional
```

## Backend configuration

Set production backend environment variables like:

```txt
PRIMARY_DOMAIN=api.buykori.app
ALLOWED_HOSTS=localhost,127.0.0.1,testserver,buykori.app,www.buykori.app,client.buykori.app,admin.buykori.app,api.buykori.app,track.buykori.app
```

The current CORS policy is intentionally open for tracker requests, while API security is enforced by API keys/signatures and per-client domain checks.
