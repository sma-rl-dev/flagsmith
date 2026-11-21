# Flagsmith - Deployment, Smoke, and Seed Notes

## Quick Start

```bash
./tester-env deploy    # Build image from source, start Postgres + app, bootstrap SPA flags
./tester-env seed      # Reseed deterministic e2e data via the app's own teardown endpoint
./tester-env verify    # Assert login, org, projects, SPA and SDK flag bootstrap
./tester-env reset     # Clean slate (containers + Postgres volume, keeps image)
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `deploy` | `docker build` `Dockerfile.tester-env`, start Postgres + app, wait for HTTP, bootstrap the SPA's own flags environment |
| `seed` | `POST /api/v1/e2etests/teardown/` with `X-E2E-Test-Auth-Token`, then `tester-env-seed.py` for the `My Test Project` product baseline |
| `verify` | Login as the e2e admin, assert org/projects, features/tags/segments/identities, SPA overrides and the SDK flags endpoint |
| `reset` | `docker compose down -v` (containers + `pgdata` volume; image kept for reuse) |
| `stop` | `docker compose stop` (Postgres data preserved) |
| `logs` | `docker compose logs -f app` |
| `status` | Compose status plus an HTTP liveness probe |

Options:
- `--run-id <id>` scopes the compose project (and therefore containers, network and the `pgdata` volume) for parallel runs.
- `--port <port>` host port for the app (default `18097`, container port `8000`).

`IMAGE_TAG` (exported by `scripts/rl-env`) overrides the image name so identical
baseline/patch sets share a content-addressed image; `RUN_ID` never reaches the
image name.

## Build

`Dockerfile.tester-env` mirrors upstream's `oss-unified` target (Django/DRF API
plus the rspack-bundled SPA served on `:8000`) and only differs by pinning base
images to digests:

- `node:24-bookworm@sha256:9d266751…` (frontend build)
- `cgr.dev/chainguard/wolfi-base@sha256:be019c1c…` (Python runtime/builder)
- `ghcr.io/astral-sh/uv@sha256:d3b601f0…` (Python deps)
- `postgres:15.5-alpine@sha256:934be6ae…` (compose service)

Measured on this host (28 vCPU):

| Build | Time |
|-------|------|
| Cold (empty layer cache and uv cache) | 95 s |
| After an `api/` edit (deps cached, collectstatic rerun) | 19 s |
| After a `frontend/` edit (deps cached, full rspack `bundledjango`) | 21 s |
| No source change | 1 s |

Dependency installs live in their own stages (`api/pyproject.toml` + `uv.lock`
for `uv sync`, `frontend/package*.json` for `npm ci`), so API source mutations
never pay for a frontend bundle and vice versa.

## Services and Environment

`docker-compose.tester-env.yml` runs two services (upstream's separate
`migrate-db` and `flagsmith-task-processor` services are dropped):

- `app`: the built image, `ENTRYPOINT flagsmith`, `CMD migrate-and-serve`
  (migrations then gunicorn on `:8000`), published on `${PORT}`.
- `postgres`: `postgres:15.5-alpine`, database `flagsmith`, user `postgres`,
  password `password`, named volume `pgdata`.

Environment set by the compose overlay:

| Variable | Value / why |
|----------|-------------|
| `DATABASE_URL` | `postgresql://postgres:password@postgres:5432/flagsmith` |
| `ENVIRONMENT` | `production` |
| `DJANGO_ALLOWED_HOSTS` | `*` so both `localhost` and `host.docker.internal` work |
| `USE_POSTGRES_FOR_ANALYTICS` | `true` — analytics stay in Postgres, no warehouse |
| `TASK_RUN_METHOD` | `SEPARATE_THREAD` — no task-processor service needed |
| `ENABLE_FE_E2E` | `true` — enables the teardown/seed endpoint |
| `E2E_TEST_AUTH_TOKEN` | fixed `tester-env-e2e-token` |
| `ENABLE_AXES` | `false` — no account lockout on repeated bad logins |
| `COOKIE_AUTH_ENABLED` / `USE_SECURE_COOKIES` | `false` — token auth over plain HTTP |
| `FLAGSMITH_ON_FLAGSMITH_API_URL` | `/api/v1/` — the SPA reads its own flags from this instance, following any page origin |
| `FLAGSMITH_ON_FLAGSMITH_API_KEY` | fixed key of the `Tester Env Platform` environment created at deploy |

The app container runs as `nobody` over a root-owned `/app`; core CRUD works,
but import/export media writes were not exercised.

## SPA flags bootstrap

The SPA initialises the Flagsmith JS client at startup
(`frontend/common/stores/config-store.js`). If that request fails, `App.js`
renders the Maintenance page, so `deploy` creates a small internal environment
(`tester-env-bootstrap.py`: organisation `Tester Env Platform`, project
`Platform Configuration`, environment `Default`, api key
`testerenvplatformflags0000000001`). The managed project is invisible to the
e2e users. No feature flags are created in it, so optional surfaces gated on
Flagsmith-on-Flagsmith flags (`feature_health`, `feature_versioning`,
`segment_change_requests`, `usage_dashboard`, release pipelines, payments) stay
off — add them here if a scenario needs them.

## Credentials and Seed Data

```bash
./tester-env seed
```

`POST /api/v1/e2etests/teardown/` runs `api/e2etests/e2e_seed_data.py`:
organisation `Bullet Train Ltd`, 7 projects (`My Test Project` … `My Test
Project 7 Role`, each with Development/Production environments as upstream
defines), permission group `TestGroup`, identity `test-identity`, an ENTERPRISE
plan with 8 seats, and 8 users that all share the password below.

`seed` then copies `tester-env-seed.py` into the app container and runs it in
`manage.py shell`, adding the product baseline to `My Test Project`. Because the
upstream teardown deletes the e2e users' organisations first, every run starts
from the same state: leftovers such as the smoke-test feature
`browser_smoke_check` are removed, and re-running `seed` on a live stack is
safe.

- Admin login: `e2e_user@flagsmithe2etestdomain.io` / `Str0ngp4ssw0rd!`
- Other seeded users: `e2e_signup_user@`, `e2e_change_email@`,
  `e2e_non_admin_user_with_{org,project,env}_permissions@`,
  `e2e_non_admin_user_with_a_role@`, `e2e_separate_test_user@`,
  `e2e_billing_user@` `flagsmithe2etestdomain.io`
- Seed is idempotent (teardown first). Login does not require a cookie; the API
  returns a DRF token at `POST /api/v1/auth/login/` under the key `key`.

### Product baseline (`My Test Project`)

8 features, 4 tags, 2 segments and 3 identities. All dates are pinned; match
entities by name, not id (ids are database-generated).

| Feature | Development | Production | Tags |
|---------|-------------|------------|------|
| `checkout_v2` | enabled, `true` | disabled, `true` | checkout, experiment |
| `seat_map_enabled` | enabled, `true` | enabled, `true` | checkout, mobile |
| `max_seats_per_booking` | enabled, `6` | enabled, `4` | pricing |
| `loyalty_points_multiplier` | enabled, `2` | disabled, `1` | pricing, experiment |
| `checkout_copy_variant` | enabled, `one-tap` | disabled, `control` | checkout, experiment |
| `journey_planner_config` | enabled, `{"max_connections": 2, "prefer_rail": true}` | disabled, `{"max_connections": 1, "prefer_rail": false}` | mobile |
| `delay_notification_threshold_minutes` | enabled, `10` | enabled, `15` | mobile |
| `duty_free_catalogue` | disabled, `{"enabled_categories": []}` | disabled, `{"enabled_categories": []}` | (none) |

Tags: `checkout` `#1F7A8C`, `experiment` `#00B894`, `mobile` `#6C5CE7`,
`pricing` `#E17055` (feature counts 3/3/3/2; one untagged feature).

Created dates (UTC, used by the Created Date sort and date column):
checkout_v2 2026-09-14 09:30, seat_map_enabled 2026-09-21 14:05,
max_seats_per_booking 2026-10-02 11:15, loyalty_points_multiplier
2026-10-09 08:45, checkout_copy_variant 2026-10-16 16:20,
journey_planner_config 2026-10-23 10:10, delay_notification_threshold_minutes
2026-11-03 13:40, duty_free_catalogue 2026-11-10 09:05.

Segments (project level, root ALL rule → one nested ALL rule group → conditions,
matching the payload the SPA's own segment create sends; conditions on the root
rule are not rendered by the segment editor):

- `Loyalty Members` — ALL: `plan` EQUAL `gold`.
- `UK Frequent Travellers` — ALL: `country` EQUAL `GB`, `bookings`
  GREATER_THAN_INCLUSIVE `5`.

Identities (Development):

- `identity-1042` — plan `gold`, country `GB`, bookings `12` (integer),
  newsletter `true`. Member of both segments.
- `identity-2087` — plan `silver`, country `US`, bookings `2`, newsletter
  `false`.
- `identity-3311` — plan `gold`, country `IE`, bookings `6`. Member of Loyalty
  Members only.

`./tester-env verify` asserts the feature names, per-environment enabled state
and value, tag assignments, segment rules, identity traits and the absence of
`browser_smoke_check`. Seed requirements are recorded in `tester-env-seed.json`
(this fork; the corpus also keeps a copy at `scenarios/flagsmith/seed.manifest.json`).

`reset` → `deploy` → `seed` → `verify` and a second `seed` → `verify` on the
same stack produced byte-identical API snapshots of projects, features, tags,
segments and identities (compared 2026-11-21).

### Browser verification paths

1. Login lands on the project list: organisation `Bullet Train Ltd`, 7 projects,
   no Maintenance page.
2. `My Test Project` → `Development` → Features: 8 rows; `checkout_v2` Enabled,
   `duty_free_catalogue` Disabled, values `6`, `one-tap`,
   `{"max_connections": 2, "prefer_rail": true}` visible.
3. Search `checkout` → 2 rows (`checkout_v2`, `checkout_copy_variant`).
4. Tag filter `pricing` → 2 rows; empty/untagged filter → `duty_free_catalogue`.
5. Sort by Created Date descending → `duty_free_catalogue` first,
   `checkout_v2` last.
6. Switch to `Production`: 3 enabled rows, `checkout_v2` Disabled,
   `max_seats_per_booking` value `4`.
7. Segments: 2 rows; open `UK Frequent Travellers` (route
   `/project/<id>/segments/<id>`) — it shows one And rule group with the
   `country` EQUAL `GB` and `bookings` Greater than or equal to `5` conditions
   and no "Add at least one AND/NOT rule" message; `Loyalty Members` shows
   `plan` EQUAL `gold`.
8. Identities: 3 rows; `identity-1042` detail shows 4 traits (plan, country,
   bookings, newsletter).

## Reset

`./tester-env reset` removes both containers, the compose network and the
`pgdata` volume; the image is kept because content-addressed tags may be shared
by other runs. `reset` → `deploy` → `verify` was verified to reproduce the same
state without `seed` (empty instance), and `reset` → `deploy` → `seed` →
`verify` reproduces the seeded state.

## Caveats

- First boot runs ~600 migrations and takes ~60 s before gunicorn listens; the
  image healthcheck's 20 s start period marks the container unhealthy in the
  meantime, so the CLI does not use `docker compose up --wait` and polls HTTP
  instead.
- Time-relative UI (audit log "x ago", feature last-updated, metrics) must not
  be asserted on exact values.
- `wolfi-base` is a rolling image: the digest is pinned, but its `apk`
  repositories move, so a future rebuild may not find `python-3.13` packages.
- Metrics/experimentation pages need SDK event traffic in Postgres; keep them
  out of the first scenarios.
