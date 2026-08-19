-- ArchiAI building engine -- Arqio integration
--
-- Additive only. Nothing here alters an existing table; generated drawings
-- and models land in `assets`, which already has the right shape, and the
-- spec lives on `projects.studio_state`, which is already the state blob.
--
-- Review before running. It has not been applied to any database.

-- 1 ---------------------------------------------------------------------
-- Bucket for generated sheets, meshes and manifests.
insert into storage.buckets (id, name, public)
values ('building-projects', 'building-projects', true)
on conflict (id) do nothing;

-- Public bucket: anyone with the URL can read, nobody can write except the
-- service role. Flip `public` to false and sign URLs if drawings are private.
drop policy if exists "building-projects read" on storage.objects;
create policy "building-projects read" on storage.objects
  for select using (bucket_id = 'building-projects');

-- 2 ---------------------------------------------------------------------
-- Generation ledger. Mirrors the shape of `edits` so the two read alike.
create table if not exists public.building_generations (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid not null references public.projects(id) on delete cascade,
  user_id         uuid not null,
  idempotency_key text not null,
  source          text not null default 'brief',      -- brief | footprint | spec
  input           jsonb not null default '{}'::jsonb,  -- what the user asked for
  spec            jsonb not null default '{}'::jsonb,  -- what the engine understood
  assumptions     jsonb not null default '[]'::jsonb,  -- what it had to assume
  manifest        jsonb not null default '{}'::jsonb,  -- areas, levels, room schedule
  status          text not null default 'pending',     -- pending | complete | failed
  tokens_used     int  not null default 0,
  engine_version  text not null default '',
  duration_ms     int  not null default 0,
  error           text not null default '',
  created_at      timestamptz not null default now()
);

create unique index if not exists building_generations_idem_idx
  on public.building_generations (user_id, idempotency_key);
create index if not exists building_generations_project_idx
  on public.building_generations (project_id, created_at desc);

alter table public.building_generations enable row level security;

drop policy if exists "own generations read" on public.building_generations;
create policy "own generations read" on public.building_generations
  for select using (auth.uid() = user_id);

-- Writes come from the service role only, which bypasses RLS. No insert or
-- update policy is granted to authenticated users on purpose: a client must
-- not be able to write its own ledger row and mark it paid.

-- 3 ---------------------------------------------------------------------
-- Atomic token debit. Raises rather than going negative, so a race between
-- two generations cannot overdraw an account.
create or replace function public.debit_tokens(p_user uuid, p_amount int)
returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  new_balance int;
begin
  if p_amount < 0 then
    raise exception 'amount must not be negative';
  end if;

  update public.user_tokens
     set balance = balance - p_amount,
         updated_at = now()
   where user_id = p_user
     and balance >= p_amount
  returning balance into new_balance;

  if new_balance is null then
    raise exception 'insufficient tokens' using errcode = 'P0001';
  end if;

  return new_balance;
end;
$$;

revoke all on function public.debit_tokens(uuid, int) from public, anon, authenticated;

-- 4 ---------------------------------------------------------------------
-- Refund, for when generation fails after the debit.
create or replace function public.credit_tokens(p_user uuid, p_amount int)
returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  new_balance int;
begin
  update public.user_tokens
     set balance = balance + greatest(p_amount, 0),
         updated_at = now()
   where user_id = p_user
  returning balance into new_balance;
  return coalesce(new_balance, 0);
end;
$$;

revoke all on function public.credit_tokens(uuid, int) from public, anon, authenticated;
