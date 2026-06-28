-- OperaOps initial schema: incidents, results, audit, eval, flywheel

create extension if not exists "pgcrypto";

create table if not exists public.schema_migrations (
  version text primary key,
  applied_at timestamptz not null default now()
);

create table if not exists public.incidents (
  id text primary key,
  source_id text,
  title text not null,
  service text not null,
  severity text not null,
  category text,
  status text not null default 'diagnosing',
  error_message text,
  stack_trace text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.incident_results (
  incident_id text primary key references public.incidents(id) on delete cascade,
  diagnosis jsonb not null default '{}'::jsonb,
  routing jsonb not null default '{}'::jsonb,
  moe jsonb not null default '{}'::jsonb,
  difficulty jsonb not null default '{}'::jsonb,
  pipeline_log jsonb not null default '[]'::jsonb,
  total_time_ms integer,
  cost_usd numeric(10, 6),
  faithfulness numeric(5, 4),
  fms_score numeric(5, 4),
  raw_result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.cascade_audit (
  id uuid primary key default gen_random_uuid(),
  incident_id text references public.incidents(id) on delete set null,
  model_used text,
  routing_reason text,
  cost_usd numeric(10, 6),
  latency_ms integer,
  escalated boolean default false,
  call_number integer,
  expert_id text,
  routing_mode text,
  difficulty text,
  provider text,
  tokens_saved integer,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_cascade_audit_incident on public.cascade_audit(incident_id);
create index if not exists idx_incidents_created on public.incidents(created_at desc);

create table if not exists public.eval_runs (
  id uuid primary key default gen_random_uuid(),
  runs integer not null default 1,
  metrics jsonb not null default '{}'::jsonb,
  raw_result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.flywheel_trajectories (
  id uuid primary key default gen_random_uuid(),
  incident_id text,
  entry jsonb not null default '{}'::jsonb,
  logged_at timestamptz not null default now()
);

create index if not exists idx_flywheel_logged on public.flywheel_trajectories(logged_at desc);

alter table public.incidents enable row level security;
alter table public.incident_results enable row level security;
alter table public.cascade_audit enable row level security;
alter table public.eval_runs enable row level security;
alter table public.flywheel_trajectories enable row level security;

drop policy if exists "anon_all_incidents" on public.incidents;
create policy "anon_all_incidents" on public.incidents for all using (true) with check (true);

drop policy if exists "anon_all_incident_results" on public.incident_results;
create policy "anon_all_incident_results" on public.incident_results for all using (true) with check (true);

drop policy if exists "anon_all_cascade_audit" on public.cascade_audit;
create policy "anon_all_cascade_audit" on public.cascade_audit for all using (true) with check (true);

drop policy if exists "anon_all_eval_runs" on public.eval_runs;
create policy "anon_all_eval_runs" on public.eval_runs for all using (true) with check (true);

drop policy if exists "anon_all_flywheel" on public.flywheel_trajectories;
create policy "anon_all_flywheel" on public.flywheel_trajectories for all using (true) with check (true);

insert into public.schema_migrations (version)
values ('20260628100000')
on conflict (version) do nothing;
