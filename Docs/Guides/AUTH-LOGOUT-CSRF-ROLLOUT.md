# Auth logout CSRF contract and rollout

`POST /api/auth/logout` clears the browser session and returns `204 No Content`. The route accepts exactly one `Origin` header whose HTTP(S) origin matches an entry in `AUTH_TRUSTED_FRONTEND_ORIGINS`. Missing, `null`, malformed, duplicate, and unlisted origins receive `403` without changing the session. `GET /api/auth/logout` is no longer available and returns `405`; it must not be used for logout.

## Configuration

Set `AUTH_TRUSTED_FRONTEND_ORIGINS` to a comma-separated list of exact serialized frontend origins, such as `https://app.example.test` or, for local development, `http://localhost:3000`. Entries contain only scheme, host, and optional port: do not include a path, query, fragment, credentials, wildcard, or trailing slash. Default HTTP and HTTPS ports are treated as their canonical origin. An unset or malformed allowlist fails closed and rejects logout.

Configure the actual frontend origins in each environment after confirming them with the operator. This list is independent of `ALLOWED_HOSTS`: the latter controls CORS/host configuration and must not be used as the logout trust policy. The frontend origin also needs to be allowed by the server's CORS configuration for the browser to read the response. Production entries should use HTTPS.

## Coordinated release

The DMS API and LandingPage are released separately. Deploy the API and frontend as a coordinated change: the API only accepts POST after this change, so cached/old frontend code that still sends GET cannot log out; a new frontend against an old API receives a failed POST and must retain the signed-in state. There is no GET compatibility bridge because GET must not clear a session. Minimize the mixed-version window, refresh cached frontend assets after the rollout, and verify a real browser logout in staging at every configured origin before production release.

No live origin configuration or cookie settings are changed by this code change. Before deployment, the operator must populate `AUTH_TRUSTED_FRONTEND_ORIGINS`, confirm corresponding CORS origins, and choose a coordinated release window.
