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
| `POST /v1/trace` | trace an uploaded sketch and return the outline, without building anything |
| `POST /v1/generate` | generate, upload, return the manifest and asset list |
| `POST /v1/revise` | the same building with one thing changed, as the next revision |
| `POST /v1/view` | renders of a building, on their own |
| `GET /docs` | live OpenAPI browser |

`/v1/generate` and `/v1/view` take exactly one of `brief`, `footprint`,
`spec` or `image`.

```jsonc
// text
{ "brief": "a five-storey school around a courtyard, 9000 sqm, entrance west",
  "project_id": "<uuid>", "idempotency_key": "<uuid>" }

// a shape the user drew, in metres
{ "footprint": { "outer": [[0,0],[54,0],[54,20],[30,20],[30,38],[0,38]],
                 "holes": [], "storeys": 3, "use": "gallery" } }

// a photograph or scan of a shape the user sketched
{ "image": { "data": "data:image/png;base64,...", "area_m2": 2400,
             "storeys": 3, "use": "office" } }

// explicit
{ "spec": { "use": "office", "shape": "courtyard", "storeys": 4,
            "area_m2": 6000, "entrance_azimuth": 270 } }
```

## Uploads: trace first, then generate

Call `/v1/trace` with the image, show the outline back to the user, and only
then generate. The response is the ring in metres plus anything worth saying
about it:

```json
{ "outer": [[-33.2,-21.6],[33.2,-21.6],[33.2,21.6],[-33.2,21.6]],
  "holes": [[[-10.1,-7.2],[10.1,-7.2],[10.1,7.2],[-10.1,7.2]]],
  "area_m2": 2400.0, "perimeter_m": 212.7, "width_m": 66.4, "depth_m": 43.2,
  "vertices": 4, "notes": ["1 opening(s) read as courtyards."] }
```

Posting that `outer`/`holes` back as a `footprint` builds exactly the building
the trace describes, so a user can nudge a corner before committing. PNG works
with no extra server dependency; other formats need Pillow installed.

`simplify` (default `0.010`) controls how hard a shaky line is smoothed, and
`straighten` (default `22`, degrees) how far an edge can be off square and
still be snapped onto it. Send `straighten: 0` to keep an outline exactly as
drawn.

## What comes back

Alongside the individual sheets, every generation returns two things you can
hand to someone as they are:

- **`<number>-drawings.pdf`** — the whole set as one PDF at true paper size,
  vector, with the text still text. A1 sheets stay A1; renders get a page they
  fit on. Turn it off with `"include_pdf": false`.
- **`<number>-project.html`** — one self-contained page with the sheets, the
  views, a turntable of the model and the key numbers. Nothing is loaded from
  anywhere else, so it works from a link, an attachment or a memory stick. A
  link can point at one drawing: `…#drawings/A-102`. Turn it off with
  `"include_page": false`, or drop the turntable with `"turntable": 0`.

Both appear in `manifest.documents` and as assets of kind `document`.

## Changing your mind

Every generation's manifest carries a `source` block — the input that made it,
normalised. Keep it next to the generation. To revise, send it back with what
you want different:

```jsonc
{ "source": { /* manifest.source from the generation you are revising */ },
  "changes": { "storeys": "+2", "courtyard": "bigger" },
  "parent_generation_id": "<the generation you are revising>",
  "project_id": "<uuid>", "idempotency_key": "<uuid>" }
```

You get a full set back, numbered `P02`, and a note of what moved:

```json
{ "revision": {
    "of": "P01", "now": "P02", "parent": "<generation id>",
    "changed": ["Storeys 6 to 8.",
                "Floor plate held, so total floor area 11 000 to 14 667 m²."],
    "measured": { "before": { "gia_m2": 10956.1, "rooms": 144 },
                  "after":  { "gia_m2": 14608.1, "rooms": 192 },
                  "delta":  { "gia_m2": 3652.0, "gia_m2_pct": 33.3, "rooms": 48 } } } }
```

Show `changed` to the user — it is written to be read aloud. `measured` is the
difference the engine actually produced, not what the change promised.

**What can change:** `storeys` `area_m2` `floor_to_floor_m` `use` `shape`
`entrance` `name` `courtyard` `footprint_scale`.

**How to say it:** an absolute value (`8`), a step (`"+2"`, `"-1"`), a
proportion (`"+20%"`, `"-10%"`), a compass point for `entrance`
(`"north"`), or a plain word for sizes (`"bigger"`, `"much smaller"`,
`"none"` to remove a courtyard).

Two behaviours worth knowing:

- **Adding storeys makes the building taller, not thinner.** The floor plate
  is held and the total area follows. Send `area_m2` in the same call to hold
  the total instead.
- **Editing geometry promotes the source.** A shape family cannot express
  "courtyard 30% bigger", so the first such change converts the source from a
  specification to the outline it produced, and says so. From then on the
  building is an outline and `shape` no longer applies.

A change that cannot be made comes back as `422` with a sentence saying why —
a courtyard that would leave less than 7 m of building around it, a value
already set, an unknown field.

## Views

`/v1/view` rebuilds the building from the same input and renders it. Nothing
is stored between calls: the engine is deterministic, so the same input is
the same building tomorrow.

```jsonc
{ "brief": "a six-storey office of 11000 sqm with a courtyard",
  "views": [
    { "name": "aerial-ne", "label": "Site aerial",
      "addons": ["ground","sky","shadow","context","trees","cars","people"] },
    { "name": "entrance", "hour": 9.5, "addons": ["ground","sky","shadow","people"] },
    { "name": "aerial-sw", "label": "Cutaway", "addons": ["ground","sky","shadow","cutaway"] }
  ] }
```

- **Names**: `aerial-ne` `aerial-nw` `aerial-se` `aerial-sw` `eye-north`
  `eye-south` `eye-east` `eye-west` `entrance` `courtyard` `roof` `axo`
  `worm`. Framing, distance and eye height are worked out from the model, so
  a name alone is enough; `azimuth`, `elevation`, `distance`, `eye_height`
  and `fov` override it.
- **Styles**: `material` `clay` `white` `line`.
- **Add-ons**: `ground` `sky` `shadow` `context` `trees` `cars` `people`
  `cutaway`. Omit for `ground`, `sky`, `shadow`.
- **Light**: `latitude`, `day_of_year` and `hour` give a real solar position,
  so shadows fall where they would fall. `sky` is `day` `clear` `overcast`
  `evening` or `none`.

Views come back as SVG, sized by `width` and `height`. `/v1/generate` accepts
the same `views` array, so a set arrives with its pictures.

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
  `ARCHIAI_MAX_AREA_M2`, both returning `422` with a readable reason. Uploads
  are capped at 12 MB and 40 megapixels; a request may ask for at most 12
  views, each at most 4000 x 4000.
- **Renders are the deterministic pass.** They are drawn from the model, not
  generated, which is what makes them repeatable and what makes them a usable
  base for a photoreal pass later.
