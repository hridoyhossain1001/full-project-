# Buykori Vercel Split Plan

## Final domain structure

```txt
buykori.app              -> Marketing website on Vercel
www.buykori.app          -> Marketing website on Vercel
client.buykori.app       -> Future client portal frontend on Vercel
admin.buykori.app        -> Future admin portal frontend on Vercel
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

Move these only after the marketing website and API domain are stable:

```txt
client.buykori.app
admin.buykori.app
```

Both frontends should call:

```txt
https://api.buykori.app
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
ALLOWED_HOSTS=localhost,127.0.0.1,testserver,*.herokuapp.com,buykori.app,www.buykori.app,client.buykori.app,admin.buykori.app,api.buykori.app,track.buykori.app
```

The current CORS policy is intentionally open for tracker requests, while API security is enforced by API keys/signatures and per-client domain checks.
