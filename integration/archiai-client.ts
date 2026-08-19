/**
 * ArchiAI building engine — Arqio server-side client.
 *
 * Runs on your backend (Next.js route handler, worker, or Node service).
 * It must NOT run in the browser: it holds both the engine API key and the
 * Supabase service role key.
 *
 * Supabase Edge Functions are Deno and cannot host the Python engine, but they
 * can call it — this module works unchanged there if you swap the imports.
 */

import { createClient, SupabaseClient } from "@supabase/supabase-js";

const ENGINE_URL = process.env.ARCHIAI_ENGINE_URL!;      // https://engine.internal
const ENGINE_KEY = process.env.ARCHIAI_ENGINE_KEY!;      // matches ARCHIAI_API_KEYS

export type GenerateInput =
  | { brief: string }
  | { footprint: { outer: [number, number][]; holes?: [number, number][][];
                   storeys?: number; floor_to_floor?: number; use?: string;
                   entrance_azimuth?: number; name?: string } }
  | { spec: { use?: string; shape?: string; storeys?: number; area_m2?: number;
              entrance_azimuth?: number; floor_to_floor?: number; name?: string } };

export interface EngineAsset {
  kind: "drawing" | "model" | "manifest";
  number?: string;
  title?: string;
  key: string;
  url: string;
  bytes: number;
  content_type: string;
  width: number;
  height: number;
  meta: Record<string, unknown>;
}

export interface EngineResult {
  status: string;
  generation_id: string;
  project_id?: string;
  duration_ms: number;
  cost_units: number;
  manifest: any;
  assets: EngineAsset[];
}

/** Read a brief without generating. Free — safe to call as the user types. */
export async function parseBrief(brief: string) {
  const r = await fetch(`${ENGINE_URL}/v1/parse`, {
    method: "POST",
    headers: { "content-type": "application/json",
               authorization: `Bearer ${ENGINE_KEY}` },
    body: JSON.stringify({ brief }),
  });
  if (!r.ok) throw new Error(`parse failed: ${r.status} ${await r.text()}`);
  return r.json() as Promise<{
    spec: Record<string, unknown>;
    assumptions: string[];
    estimated_cost_units: number;
    estimated_sheets: number;
  }>;
}

/**
 * Generate a building and persist it.
 *
 * Order matters: tokens are debited before the work starts, so two concurrent
 * requests cannot overdraw, and refunded if anything downstream fails.
 */
export async function generateBuilding(opts: {
  supabase: SupabaseClient;
  userId: string;
  projectId: string;
  input: GenerateInput;
  idempotencyKey: string;
  number?: string;
}): Promise<EngineResult> {
  const { supabase, userId, projectId, input, idempotencyKey } = opts;

  // 0. Replay an earlier identical request rather than charging twice.
  const { data: prior } = await supabase
    .from("building_generations")
    .select("manifest, tokens_used, status")
    .eq("user_id", userId)
    .eq("idempotency_key", idempotencyKey)
    .maybeSingle();
  if (prior?.status === "complete") {
    return { status: "complete", generation_id: idempotencyKey,
             project_id: projectId, duration_ms: 0,
             cost_units: prior.tokens_used, manifest: prior.manifest,
             assets: [] };
  }

  // 1. Price it, then take payment before doing the work.
  const estimate = "brief" in input
    ? (await parseBrief(input.brief)).estimated_cost_units
    : 80;
  const { error: debitError } = await supabase.rpc("debit_tokens", {
    p_user: userId, p_amount: estimate,
  });
  if (debitError) throw new Error(`insufficient tokens: ${debitError.message}`);

  let result: EngineResult;
  try {
    const r = await fetch(`${ENGINE_URL}/v1/generate`, {
      method: "POST",
      headers: { "content-type": "application/json",
                 authorization: `Bearer ${ENGINE_KEY}` },
      body: JSON.stringify({
        ...input,
        project_id: projectId,
        number: opts.number,
        idempotency_key: idempotencyKey,
      }),
    });
    if (!r.ok) throw new Error(`engine ${r.status}: ${await r.text()}`);
    result = (await r.json()) as EngineResult;
  } catch (err) {
    await supabase.rpc("credit_tokens", { p_user: userId, p_amount: estimate });
    await supabase.from("building_generations").insert({
      project_id: projectId, user_id: userId, idempotency_key: idempotencyKey,
      source: Object.keys(input)[0], input, status: "failed",
      error: String(err).slice(0, 2000),
    });
    throw err;
  }

  // 2. Record every artefact as an asset. The engine has already uploaded the
  //    bytes; these rows are the index your UI reads.
  const rows = result.assets.map((a) => ({
    project_id: projectId,
    kind: a.kind === "drawing" ? "drawing" : a.kind,
    storage_path: a.key,
    width: a.width,
    height: a.height,
    meta: { ...a.meta, sheet_number: a.number ?? null, title: a.title ?? null,
            url: a.url, bytes: a.bytes, content_type: a.content_type,
            generation_id: result.generation_id },
    is_starred: false,
  }));
  if (rows.length) {
    const { error } = await supabase.from("assets").insert(rows);
    if (error) console.error("asset index write failed", error);  // files are safe
  }

  // 3. Ledger, and the spec back onto the project so it can be regenerated.
  await supabase.from("building_generations").insert({
    project_id: projectId, user_id: userId, idempotency_key: idempotencyKey,
    source: Object.keys(input)[0], input,
    spec: result.manifest.spec ?? {},
    assumptions: result.manifest.assumptions ?? [],
    manifest: result.manifest,
    status: "complete",
    tokens_used: result.cost_units,
    engine_version: result.manifest.engine?.version ?? "",
    duration_ms: result.duration_ms,
  });

  await supabase.from("projects")
    .update({ studio_state: { kind: "building", manifest: result.manifest } })
    .eq("id", projectId);

  // 4. Settle the difference between estimate and actual.
  const delta = result.cost_units - estimate;
  if (delta > 0) await supabase.rpc("debit_tokens", { p_user: userId, p_amount: delta });
  if (delta < 0) await supabase.rpc("credit_tokens", { p_user: userId, p_amount: -delta });

  return result;
}
