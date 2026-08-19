# Calling the building engine from Arqio

The engine is a stateless HTTP service. It generates drawings and a mesh,
uploads them to Supabase Storage, and returns a manifest. It does not touch
your database and it does not know about users, tokens or billing — your
backend owns all of that.

## Why a container and not an Edge Function

Supabase Edge Functions run Deno. The engine is Python, so it needs somewhere
to run: Fly, Railway, Cloud Run, Render, or a container on whatever you
already use. An Edge Function can still be the *caller*.

## Shape of a call

```
Browser ──▶ your backend ──▶ debit_tokens()        (Postgres, atomic)
                        ├──▶ POST /v1/generate     (engine container)
                        │         └──▶ Supabase Storage   (service role)
                        └──▶ insert assets + building_generations
```

Generation is synchronous: a five-storey school with eight sheets, a mesh and
a manifest takes about **400 ms**. There is no queue to manage. Renders will
need one when they land; the response is already job-shaped (`status`,
`generation_id`) so adding `202 Accepted` later will not break callers.

## Setup

1. Run `001_building_engine.sql`. It is additive — it creates a storage
   bucket, a `building_generations` ledger, and atomic
   `debit_tokens` / `credit_tokens` functions. It alters nothing you have.
2. Deploy the container:
   ```sh
   docker build -f deploy/Dockerfile -t archiai-engine .
   docker run -p 8080:8080 --env-file deploy/env.example archiai-engine
   ```
3. Set `ARCHIAI_API_KEYS` on the service and `ARCHIAI_ENGINE_KEY` on your
   backend to the same long random string.
4. Drop `archiai-client.ts` into your server code.

## Endpoints

| | |
|---|---|
| `GET /v1/health` | liveness, engine version, storage mode |
| `POST /v1/parse` | read a brief, return the spec and every assumption. Free — call it as the user types |
| `POST /v1/generate` | generate, upload, return the manifest and asset list |
| `GET /docs` | live OpenAPI browser |

`/v1/generate` takes exactly one of `brief`, `footprint` or `spec`.

```jsonc
// text
{ "brief": "a five-storey school around a courtyard, 9000 sqm, entrance west",
  "project_id": "<uuid>", "idempotency_key": "<uuid>" }

// a shape the user drew, in metres
{ "footprint": { "outer": [[0,0],[54,0],[54,20],[30,20],[30,38],[0,38]],
                 "holes": [], "storeys": 3, "use": "gallery" } }

// explicit
{ "spec": { "use": "office", "shape": "courtyard", "storeys": 4,
            "area_m2": 6000, "entrance_azimuth": 270 } }
```

## What `/v1/parse` is for

It returns what the engine understood **and what it had to assume**:

```json
{ "spec": { "use": "office", "shape": "bar", "storeys": 3, "area_m2": null },
  "assumptions": ["Number of storeys not stated; assumed 3.",
                  "Floor area not stated; sized from the storey count.",
                  "Shape not stated; assumed a rectangular bar."],
  "estimated_sheets": 6, "estimated_cost_units": 62 }
```

Show those assumptions before charging. It is the difference between a user
feeling the tool understood them and a user feeling it guessed.

## Notes and limits

- **Idempotency is in-memory in the engine**, so it only holds within one
  instance. The durable check is the unique index on
  `building_generations (user_id, idempotency_key)`, which the client uses
  first — that is the one that matters.
- **Estimate then settle.** Tokens are debited before work starts so
  concurrent requests cannot overdraw, and the difference is settled after.
  Failures refund.
- **Asset index writes are non-fatal.** If the `assets` insert fails, the
  files are already in Storage and the manifest is returned; you can reindex
  from the manifest.
- **The service role key never leaves the server.** Uploads happen inside the
  engine container.
- **Limits** are enforced with `ARCHIAI_MAX_STOREYS` and
  `ARCHIAI_MAX_AREA_M2`, both returning `422` with a readable reason.
