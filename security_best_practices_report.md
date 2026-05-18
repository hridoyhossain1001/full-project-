# Security and Codebase Check Report

Date: 2026-05-18

## Fix Status

Fixes applied after the initial audit:

- Runtime config: local `.env` now has generated `ADMIN_API_KEY` and `ENCRYPTION_KEY` values; `.env.example` documents required variables.
- Host header hardening: `TrustedHostMiddleware` added with `ALLOWED_HOSTS` support.
- Webhook SSRF hardening: outbound webhook hostnames now resolve to global IPs only, credentials in URLs are rejected, and redirects are not followed.
- Signed server-side origin proof: WordPress `/events` requests now include `X-CAPI-Timestamp` and `X-CAPI-Signature`; FastAPI only accepts `X-CAPI-Origin` as domain proof when the signature is valid.
- Token fallback hardening: decrypt fallback is disabled by default and only available through `ALLOW_LEGACY_PLAINTEXT_TOKENS=true`.
- Client portal XSS hardening: dynamic dashboard text inserted through `innerHTML` is escaped.
- Repo hygiene: `.gitignore` was repaired, `.env.example` added, and the null-byte scratch Python file was removed.
- Plugin ZIP artifacts were rebuilt after PHP changes.

Remaining operational note: if you use a custom production gateway domain, add it to `ALLOWED_HOSTS` in deployment config.

## Executive Summary

The core FastAPI app, tests, and WordPress plugin syntax checks are mostly healthy: `pytest` passed, `app/` and `tests/` compile cleanly, PHP lint found no syntax errors, `pip check` found no broken requirements, and Alembic has one current head.

The initially identified high/medium items have been fixed in code/config, except deployment-specific hostnames must still be set in `ALLOWED_HOSTS` where needed.

## Checks Run

- `python -m pytest -q` -> 5 passed
- `python -m compileall -q app tests` -> passed
- `python -m compileall -q .` -> failed on `scratch_old_portal.py` null bytes
- `php -l` over `wordpress-plugin/capi-gateway/**/*.php` -> passed
- `python -m pip check` -> no broken requirements
- `python -m alembic heads` -> `g4h5i6j7k8l9 (head)`
- Secret-pattern scan for common API key/private key formats -> no matches in non-zip files
- `bandit` was not available in the current Python environment

## High Severity

### H-1 Runtime app import fails unless required environment variables are set

Rule ID: FASTAPI-CONFIG-001  
Severity: High  
Location: `app/security.py` lines 14-17, `app/main.py` lines 21-23, `.env` line 6  
Evidence: `app/security.py` raises when `ENCRYPTION_KEY` is empty; `app/main.py` raises when `ADMIN_API_KEY` is absent. The current `.env` contains `ENCRYPTION_KEY` but it is empty, and `.env` does not contain `ADMIN_API_KEY`.  
Impact: Local `uvicorn app.main:app` / plain app import fails before startup. Production will also fail if either variable is missing.  
Fix: Generate and set a real Fernet `ENCRYPTION_KEY`; add `ADMIN_API_KEY` in deployment config. Consider adding `.env.example` with required keys and a startup config validation message that lists missing key names only.  
False positive notes: If production config vars are already set in Heroku, production may be fine; local `.env` is currently not runnable.

### H-2 Host header is trusted without TrustedHostMiddleware

Rule ID: FASTAPI-HOST-001  
Severity: High  
Location: `app/main.py` lines 88-113, `app/routers/tracker.py` lines 95-100, `app/routers/client_portal.py` lines 670-677  
Evidence: No `TrustedHostMiddleware` is configured. The tracker and portal build URLs from `Host` / `X-Forwarded-Proto`.  
Impact: Depending on proxy/cache behavior, this can enable host-header poisoning, bad generated integration URLs, or cache poisoning of `/t.js?key=...` responses.  
Fix: Add `TrustedHostMiddleware` with allowed production hostnames from env, and only trust forwarded headers from known proxies.  
Mitigation: Ensure Heroku/CDN/reverse proxy rejects unexpected hosts before the app.

## Medium Severity

### M-1 Webhook SSRF guard does not resolve DNS before outbound requests

Rule ID: FASTAPI-SSRF-001  
Severity: Medium  
Location: `app/services/webhook_service.py` lines 16-27 and 45-52  
Evidence: URL validation blocks localhost literals and private IP literals, but arbitrary hostnames return `True` without resolving and checking final IPs.  
Impact: A client-controlled webhook domain could resolve to internal/private infrastructure, or change later via DNS rebinding, causing server-side requests to unintended targets.  
Fix: Resolve hostnames before sending and reject private, loopback, link-local, multicast, and reserved addresses. Disable or revalidate redirects if enabled in the shared HTTP client.  
False positive notes: The current shared `httpx.AsyncClient` does not explicitly enable redirects, which reduces redirect-based SSRF risk.

### M-2 Domain whitelist accepts spoofable `X-CAPI-Origin`

Rule ID: FASTAPI-AUTHZ-ORIGIN-001  
Severity: Medium  
Location: `app/routers/events.py` lines 180-209 and `wordpress-plugin/capi-gateway/capi-gateway.php` lines 163-167  
Evidence: `/events` accepts `Origin`, `Referer`, or caller-supplied `X-CAPI-Origin` as domain proof. The WordPress plugin sets `X-CAPI-Origin`, but any holder of the server API key can also set it.  
Impact: If a server API key leaks, domain locking can be bypassed by sending the expected `X-CAPI-Origin` header.  
Fix: Treat `X-CAPI-Origin` as informational for server-side integrations, not as security proof. For browser endpoints use `Origin`/`Referer`; for server integrations rely on rotated server keys, separate per-channel keys, or HMAC-signed requests.

### M-3 Token decrypt fallback returns plaintext on any decrypt failure

Rule ID: PYTHON-CRYPTO-001  
Severity: Medium  
Location: `app/security.py` lines 30-40  
Evidence: `decrypt_token()` catches every exception and returns the input value unchanged.  
Impact: This preserves backwards compatibility with old plaintext tokens, but it also silently accepts invalid encrypted values and can mask key-rotation mistakes.  
Fix: Restrict fallback to an explicit migration mode or a detected legacy plaintext format. For cookies/session tokens, fail closed instead of returning the raw value.

### M-4 Client portal JavaScript writes API data into `innerHTML`

Rule ID: JS-XSS-001  
Severity: Medium  
Location: `app/routers/client_portal.py` lines 1557-1569, 1651-1683, 1700-1711  
Evidence: Event names, event IDs, validation messages, and error details are concatenated into HTML strings and assigned through `innerHTML`.  
Impact: If any of these fields can contain attacker-controlled HTML, a client dashboard user could hit stored/reflected XSS.  
Fix: Use `textContent` / DOM node creation for dynamic text, or HTML-escape all dynamic values before insertion.

## Low Severity / Hygiene

### L-1 Full repository compile fails because a tracked scratch file contains null bytes

Rule ID: REPO-HYGIENE-001  
Severity: Low  
Location: `scratch_old_portal.py`; tracked artifact list includes `scratch_*.py`, `site.html`, `logs.txt`, and plugin ZIPs  
Evidence: `python -m compileall -q .` fails with `SyntaxError: source code string cannot contain null bytes` for `scratch_old_portal.py`.  
Impact: Full-repo tooling, packaging, or CI checks can fail even though production app code is fine. Tracked logs/scratch/zips also increase accidental data exposure risk over time.  
Fix: Remove generated/scratch artifacts from git or move them under an ignored archive directory. Fix `.gitignore` encoding and add patterns for scratch files, logs, and ZIP build outputs.

### L-2 Client IP is taken from forwarded headers without trusted-proxy enforcement

Rule ID: FASTAPI-HEADER-001  
Severity: Low  
Location: `app/routers/events.py` lines 211-214, `app/routers/tracker.py` lines 188-190, `app/routers/admin.py` lines 440-443, `wordpress-plugin/capi-gateway/includes/frontend-tracking.php` lines 521-542  
Evidence: `X-Forwarded-For` and similar headers are used directly for client IP detection.  
Impact: Attackers can spoof analytics/audit IP fields if requests can reach the app directly or if the edge proxy does not sanitize these headers.  
Fix: Only trust forwarded headers from known proxy IP ranges, or rely on platform-provided proxy handling.

## Positive Findings

- OpenAPI docs are disabled by default unless `ENABLE_DOCS` is set.
- CORS wildcard is configured with `allow_credentials=False`.
- Admin Basic auth uses constant-time comparison and requires `ADMIN_PASSWORD`.
- Admin state-changing forms have CSRF tokens.
- WordPress admin AJAX endpoints reviewed use nonce checks and capability checks.
- WordPress frontend AJAX validates origin/referer and whitelists event names.
- Token storage uses Fernet encryption for new values.
- SQL access is through SQLAlchemy expressions; I did not find raw SQL string interpolation.

## Recommended Fix Order

1. Set required runtime config and add `.env.example`.
2. Add TrustedHostMiddleware / host allowlist.
3. Harden outbound webhook URL validation against DNS-based SSRF.
4. Remove or gate the plaintext decrypt fallback.
5. Replace dashboard `innerHTML` dynamic rendering with safe DOM/text APIs.
6. Clean tracked scratch/log/ZIP artifacts and repair `.gitignore`.
