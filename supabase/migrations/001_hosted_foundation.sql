-- ResearchAssistant hosted foundation.
-- The private FastAPI service is the application writer.  Browser clients use
-- Supabase Auth for identity, while account-owned reads remain protected by RLS.

create extension if not exists pgcrypto;

create table if not exists public.profiles (
    owner_id uuid primary key references auth.users(id) on delete cascade,
    display_name text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.research_runs (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null references auth.users(id) on delete cascade,
    raw_claim text not null check (length(raw_claim) between 1 and 20000),
    request_json jsonb not null,
    status text not null check (status in ('queued', 'running', 'released', 'blocked', 'failed', 'cancelled')),
    stage text not null,
    progress_percent integer not null default 0 check (progress_percent between 0 and 100),
    message text not null,
    latest_checkpoint text,
    completed_checkpoints integer not null default 0 check (completed_checkpoints >= 0),
    total_checkpoints integer not null default 5 check (total_checkpoints >= 1),
    attempt integer not null default 0 check (attempt >= 0),
    max_attempts integer not null default 3 check (max_attempts between 1 and 10),
    lease_owner text,
    lease_expires_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    completed_at timestamptz
);

alter table public.research_runs add column if not exists lease_owner text;

create index if not exists research_runs_queue_idx
    on public.research_runs (status, lease_expires_at, created_at);
create index if not exists research_runs_owner_idx
    on public.research_runs (owner_id, updated_at desc);

create table if not exists public.research_run_events (
    event_id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.research_runs(id) on delete cascade,
    owner_id uuid not null references auth.users(id) on delete cascade,
    event_type text not null check (event_type in ('queued', 'started', 'checkpoint', 'retry', 'completed', 'failed', 'cancelled')),
    stage text not null,
    message text not null,
    checkpoint text,
    created_at timestamptz not null default now()
);

create index if not exists research_run_events_lookup_idx
    on public.research_run_events (run_id, created_at);

create table if not exists public.research_artifacts (
    artifact_id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.research_runs(id) on delete cascade,
    owner_id uuid not null references auth.users(id) on delete cascade,
    artifact_type text not null,
    fingerprint char(64) not null check (fingerprint ~ '^[0-9a-f]{64}$'),
    payload_json jsonb not null,
    created_at timestamptz not null default now(),
    unique (run_id, artifact_type)
);

create table if not exists public.provider_credentials (
    owner_id uuid not null references auth.users(id) on delete cascade,
    name text not null check (name in ('mimo_api_key', 'luna_api_key', 'luna_base_url', 'luna_model', 'exa_api_key', 'openalex_api_key', 'serpsearch_api_key', 'pubmed_api_key', 'firecrawl_api_key')),
    vault_secret_id uuid,
    configured boolean not null default true,
    updated_at timestamptz not null default now(),
    primary key (owner_id, name)
);

create table if not exists public.user_settings (
    owner_id uuid primary key references auth.users(id) on delete cascade,
    display_name text,
    default_max_tokens integer not null default 500000 check (default_max_tokens between 1 and 500000),
    default_max_cost_usd numeric(12, 6) not null default 0.20 check (default_max_cost_usd > 0 and default_max_cost_usd <= 1.00),
    default_max_llm_calls integer not null default 160 check (default_max_llm_calls between 1 and 160),
    updated_at timestamptz not null default now()
);

create table if not exists public.historical_runs (
    history_id uuid primary key default gen_random_uuid(),
    owner_id uuid not null references auth.users(id) on delete cascade,
    source_fingerprint char(64) not null check (source_fingerprint ~ '^[0-9a-f]{64}$'),
    local_run_id uuid not null,
    raw_claim text not null,
    status text not null,
    stage text not null,
    updated_at timestamptz not null,
    completed_at timestamptz,
    run_fingerprint char(64) not null check (run_fingerprint ~ '^[0-9a-f]{64}$'),
    complete boolean not null default false,
    source_schema_version integer not null check (source_schema_version >= 1),
    unique (owner_id, source_fingerprint, local_run_id)
);

create table if not exists public.migration_imports (
    owner_id uuid not null references auth.users(id) on delete cascade,
    source_fingerprint char(64) not null check (source_fingerprint ~ '^[0-9a-f]{64}$'),
    source_schema_version integer not null check (source_schema_version >= 1),
    imported integer not null default 0,
    history_only integer not null default 0,
    created_at timestamptz not null default now(),
    primary key (owner_id, source_fingerprint)
);

create or replace view public.provider_credential_metadata as
select owner_id, name, configured, updated_at
from public.provider_credentials;

-- Immutable evidence and release artifacts are insert-only.
create or replace function public.reject_research_artifact_mutation()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    raise exception 'research artifacts are immutable';
end;
$$;

drop trigger if exists research_artifacts_immutable_update on public.research_artifacts;
create trigger research_artifacts_immutable_update
before update on public.research_artifacts
for each row execute function public.reject_research_artifact_mutation();

drop trigger if exists research_artifacts_immutable_delete on public.research_artifacts;
create trigger research_artifacts_immutable_delete
before delete on public.research_artifacts
for each row execute function public.reject_research_artifact_mutation();

-- Personal account RLS is enabled on every account-owned table.
alter table public.profiles enable row level security;
alter table public.research_runs enable row level security;
alter table public.research_run_events enable row level security;
alter table public.research_artifacts enable row level security;
alter table public.provider_credentials enable row level security;
alter table public.user_settings enable row level security;
alter table public.historical_runs enable row level security;
alter table public.migration_imports enable row level security;

revoke all on public.profiles, public.research_runs, public.research_run_events,
    public.research_artifacts, public.provider_credentials, public.user_settings,
    public.historical_runs, public.migration_imports
    from anon, authenticated;

drop policy if exists profiles_owner on public.profiles;
create policy profiles_owner on public.profiles for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());
drop policy if exists research_runs_owner on public.research_runs;
create policy research_runs_owner on public.research_runs for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());
drop policy if exists research_run_events_owner on public.research_run_events;
create policy research_run_events_owner on public.research_run_events for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());
drop policy if exists research_artifacts_owner on public.research_artifacts;
create policy research_artifacts_owner on public.research_artifacts for select using (owner_id = auth.uid());
drop policy if exists provider_credentials_owner on public.provider_credentials;
create policy provider_credentials_owner on public.provider_credentials for select using (owner_id = auth.uid());
drop policy if exists user_settings_owner on public.user_settings;
create policy user_settings_owner on public.user_settings for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());
drop policy if exists historical_runs_owner on public.historical_runs;
create policy historical_runs_owner on public.historical_runs for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());
drop policy if exists migration_imports_owner on public.migration_imports;
create policy migration_imports_owner on public.migration_imports for select using (owner_id = auth.uid());

revoke all on public.provider_credential_metadata from anon, authenticated;
grant select on public.provider_credential_metadata to service_role;

create or replace function public.create_research_run(p_owner_id uuid, p_request jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    created_run public.research_runs;
begin
    insert into public.research_runs (owner_id, raw_claim, request_json, status, stage, message)
    values (p_owner_id, p_request->>'raw_claim', p_request, 'queued', 'queued', 'Research is queued.')
    returning * into created_run;
    insert into public.research_run_events (run_id, owner_id, event_type, stage, message)
    values (created_run.id, created_run.owner_id, 'queued', created_run.stage, created_run.message);
    return jsonb_build_object(
        'run_id', created_run.id, 'owner_id', created_run.owner_id,
        'raw_claim', created_run.raw_claim, 'request', created_run.request_json,
        'status', created_run.status, 'stage', created_run.stage,
        'progress_percent', created_run.progress_percent, 'message', created_run.message,
        'latest_checkpoint', created_run.latest_checkpoint,
        'completed_checkpoints', created_run.completed_checkpoints,
        'total_checkpoints', created_run.total_checkpoints,
        'attempt', created_run.attempt, 'max_attempts', created_run.max_attempts,
        'lease_expires_at', created_run.lease_expires_at,
        'created_at', created_run.created_at, 'updated_at', created_run.updated_at,
        'completed_at', created_run.completed_at
    );
end;
$$;

create or replace function public.cancel_research_run(p_owner_id uuid, p_run_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    changed public.research_runs;
begin
    update public.research_runs
    set status = case when status in ('released', 'blocked', 'failed', 'cancelled') then status else 'cancelled' end,
        stage = case when status in ('released', 'blocked', 'failed', 'cancelled') then stage else 'cancelled' end,
        message = case when status in ('released', 'blocked', 'failed', 'cancelled') then message else 'Cancellation requested.' end,
        lease_expires_at = null,
        lease_owner = null,
        completed_at = case when status in ('released', 'blocked', 'failed', 'cancelled') then completed_at else now() end,
        updated_at = now()
    where id = p_run_id and owner_id = p_owner_id
    returning * into changed;
    if not found then raise exception 'research run not found'; end if;
    return jsonb_build_object('run_id', changed.id, 'owner_id', changed.owner_id, 'raw_claim', changed.raw_claim,
        'request', changed.request_json, 'status', changed.status, 'stage', changed.stage,
        'progress_percent', changed.progress_percent, 'message', changed.message,
        'latest_checkpoint', changed.latest_checkpoint, 'completed_checkpoints', changed.completed_checkpoints,
        'total_checkpoints', changed.total_checkpoints, 'attempt', changed.attempt, 'max_attempts', changed.max_attempts,
        'lease_expires_at', changed.lease_expires_at, 'created_at', changed.created_at,
        'updated_at', changed.updated_at, 'completed_at', changed.completed_at);
end;
$$;

create or replace function public.claim_research_job(p_worker_id text, p_lease_seconds integer)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    claimed public.research_runs;
    lease_until timestamptz := now() + make_interval(secs => p_lease_seconds);
begin
    select * into claimed
    from public.research_runs
    where (status = 'queued' or (status = 'running' and lease_expires_at <= now()))
    order by created_at
    limit 1
    for update skip locked;
    if not found then return null; end if;
    update public.research_runs
    set status = 'running', stage = case when stage = 'queued' then 'planning' else stage end,
        message = 'Research is running.', attempt = attempt + 1,
        lease_expires_at = lease_until, updated_at = now()
        , lease_owner = p_worker_id
    where id = claimed.id
    returning * into claimed;
    insert into public.research_run_events (run_id, owner_id, event_type, stage, message)
    values (claimed.id, claimed.owner_id, 'started', claimed.stage, claimed.message);
    return jsonb_build_object(
        'run', jsonb_build_object('run_id', claimed.id, 'owner_id', claimed.owner_id,
            'raw_claim', claimed.raw_claim, 'request', claimed.request_json, 'status', claimed.status,
            'stage', claimed.stage, 'progress_percent', claimed.progress_percent, 'message', claimed.message,
            'latest_checkpoint', claimed.latest_checkpoint, 'completed_checkpoints', claimed.completed_checkpoints,
            'total_checkpoints', claimed.total_checkpoints, 'attempt', claimed.attempt,
            'max_attempts', claimed.max_attempts, 'lease_expires_at', claimed.lease_expires_at,
            'created_at', claimed.created_at, 'updated_at', claimed.updated_at, 'completed_at', claimed.completed_at),
        'worker_id', p_worker_id, 'lease_expires_at', lease_until);
end;
$$;

create or replace function public.heartbeat_research_job(
    p_run_id uuid, p_worker_id text, p_checkpoint jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    changed public.research_runs;
begin
    update public.research_runs
    set stage = p_checkpoint->>'stage', progress_percent = (p_checkpoint->>'progress_percent')::integer,
        message = p_checkpoint->>'message', latest_checkpoint = p_checkpoint->>'checkpoint',
        completed_checkpoints = greatest(completed_checkpoints, 1),
        lease_expires_at = now() + interval '5 minutes', updated_at = now()
    where id = p_run_id and status = 'running' and lease_owner = p_worker_id and lease_expires_at > now()
    returning * into changed;
    if not found then raise exception 'worker lease is no longer active'; end if;
    insert into public.research_run_events (run_id, owner_id, event_type, stage, message, checkpoint)
    values (changed.id, changed.owner_id, 'checkpoint', changed.stage, changed.message, changed.latest_checkpoint);
    return jsonb_build_object('run_id', changed.id, 'owner_id', changed.owner_id, 'raw_claim', changed.raw_claim,
        'request', changed.request_json, 'status', changed.status, 'stage', changed.stage,
        'progress_percent', changed.progress_percent, 'message', changed.message,
        'latest_checkpoint', changed.latest_checkpoint, 'completed_checkpoints', changed.completed_checkpoints,
        'total_checkpoints', changed.total_checkpoints, 'attempt', changed.attempt, 'max_attempts', changed.max_attempts,
        'lease_expires_at', changed.lease_expires_at, 'created_at', changed.created_at,
        'updated_at', changed.updated_at, 'completed_at', changed.completed_at);
end;
$$;

create or replace function public.complete_research_job(
    p_run_id uuid, p_worker_id text, p_result jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    changed public.research_runs;
    artifact jsonb := p_result->'final_artifact';
begin
    update public.research_runs
    set status = p_result->>'status', stage = p_result->>'stage', progress_percent = 100,
        message = p_result->>'message', lease_owner = null, lease_expires_at = null,
        completed_at = now(), updated_at = now()
    where id = p_run_id and status = 'running' and lease_owner = p_worker_id and lease_expires_at > now()
    returning * into changed;
    if not found then raise exception 'worker lease is no longer active'; end if;
    if artifact is not null and artifact <> 'null'::jsonb then
        insert into public.research_artifacts (artifact_id, run_id, owner_id, artifact_type, fingerprint, payload_json)
        values ((artifact->>'artifact_id')::uuid, changed.id, changed.owner_id, artifact->>'artifact_type',
            artifact->>'fingerprint', (artifact->>'payload_json')::jsonb);
    end if;
    insert into public.research_run_events (run_id, owner_id, event_type, stage, message)
    values (changed.id, changed.owner_id,
        case when changed.status in ('released', 'blocked') then 'completed' else 'failed' end,
        changed.stage, changed.message);
    return jsonb_build_object('run_id', changed.id, 'owner_id', changed.owner_id, 'raw_claim', changed.raw_claim,
        'request', changed.request_json, 'status', changed.status, 'stage', changed.stage,
        'progress_percent', changed.progress_percent, 'message', changed.message,
        'latest_checkpoint', changed.latest_checkpoint, 'completed_checkpoints', changed.completed_checkpoints,
        'total_checkpoints', changed.total_checkpoints, 'attempt', changed.attempt, 'max_attempts', changed.max_attempts,
        'lease_expires_at', changed.lease_expires_at, 'created_at', changed.created_at,
        'updated_at', changed.updated_at, 'completed_at', changed.completed_at);
end;
$$;

create or replace function public.fail_research_job(
    p_run_id uuid, p_worker_id text, p_message text, p_retryable boolean
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    changed public.research_runs;
    retry boolean;
begin
    select (p_retryable and attempt < max_attempts) into retry
    from public.research_runs
    where id = p_run_id and status = 'running' and lease_owner = p_worker_id and lease_expires_at > now();
    if not found then raise exception 'worker lease is no longer active'; end if;
    update public.research_runs
    set status = case when retry then 'queued' else 'failed' end,
        stage = case when retry then 'retrying' else 'failed' end,
        message = p_message, lease_owner = null, lease_expires_at = null,
        completed_at = case when retry then null else now() end, updated_at = now()
    where id = p_run_id returning * into changed;
    insert into public.research_run_events (run_id, owner_id, event_type, stage, message)
    values (changed.id, changed.owner_id, case when retry then 'retry' else 'failed' end, changed.stage, changed.message);
    return jsonb_build_object('run_id', changed.id, 'owner_id', changed.owner_id, 'raw_claim', changed.raw_claim,
        'request', changed.request_json, 'status', changed.status, 'stage', changed.stage,
        'progress_percent', changed.progress_percent, 'message', changed.message,
        'latest_checkpoint', changed.latest_checkpoint, 'completed_checkpoints', changed.completed_checkpoints,
        'total_checkpoints', changed.total_checkpoints, 'attempt', changed.attempt, 'max_attempts', changed.max_attempts,
        'lease_expires_at', changed.lease_expires_at, 'created_at', changed.created_at,
        'updated_at', changed.updated_at, 'completed_at', changed.completed_at);
end;
$$;

create or replace function public.import_local_history(p_owner_id uuid, p_bundle jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    existing public.migration_imports;
    run_item jsonb;
    existing_run_fingerprint char(64);
    collision_ids jsonb := '[]'::jsonb;
    imported_count integer := 0;
    history_count integer := 0;
begin
    select * into existing from public.migration_imports
    where owner_id = p_owner_id and source_fingerprint = p_bundle->>'source_fingerprint';
    if found then
        return jsonb_build_object('source_fingerprint', existing.source_fingerprint,
            'imported', existing.imported, 'already_imported', existing.imported,
            'collisions', '[]'::jsonb, 'history_only', existing.history_only);
    end if;
    for run_item in select * from jsonb_array_elements(coalesce(p_bundle->'runs', '[]'::jsonb)) loop
        select run_fingerprint into existing_run_fingerprint from public.historical_runs
        where owner_id = p_owner_id and local_run_id = (run_item->>'local_run_id')::uuid
        order by updated_at desc limit 1;
        if found then
            if existing_run_fingerprint <> run_item->>'fingerprint' then
                collision_ids := collision_ids || jsonb_build_array((run_item->>'local_run_id')::uuid);
            end if;
        else
            insert into public.historical_runs (owner_id, source_fingerprint, local_run_id, raw_claim, status, stage,
                updated_at, completed_at, run_fingerprint, complete, source_schema_version)
            values (p_owner_id, p_bundle->>'source_fingerprint', (run_item->>'local_run_id')::uuid,
                run_item->>'raw_claim', run_item->>'status', run_item->>'stage', (run_item->>'updated_at')::timestamptz,
                nullif(run_item->>'completed_at', '')::timestamptz, run_item->>'fingerprint',
                coalesce((run_item->>'complete')::boolean, false), (run_item->>'source_schema_version')::integer);
            imported_count := imported_count + 1;
            if coalesce((run_item->>'complete')::boolean, false) = false then history_count := history_count + 1; end if;
        end if;
    end loop;
    insert into public.migration_imports (owner_id, source_fingerprint, source_schema_version, imported, history_only)
    values (p_owner_id, p_bundle->>'source_fingerprint', (p_bundle->>'source_schema_version')::integer, imported_count, history_count);
    return jsonb_build_object('source_fingerprint', p_bundle->>'source_fingerprint', 'imported', imported_count,
        'already_imported', 0, 'collisions', collision_ids, 'history_only', history_count);
end;
$$;

-- Vault is the only place where provider credential values are stored.
create or replace function public.save_provider_credentials(p_owner_id uuid, p_credentials jsonb)
returns table(name text, configured boolean, updated_at timestamptz)
language plpgsql
security definer
set search_path = public, vault
as $$
declare
    item record;
    secret_id uuid;
    changed_at timestamptz := now();
begin
    for item in select key, value from jsonb_each_text(coalesce(p_credentials, '{}'::jsonb)) loop
        if item.value is null or length(item.value) = 0 then continue; end if;
        secret_id := vault.create_secret(item.value, p_owner_id::text || ':' || item.key,
            'ResearchAssistant provider credential');
        insert into public.provider_credentials (owner_id, name, vault_secret_id, configured, updated_at)
        values (p_owner_id, item.key, secret_id, true, changed_at)
        on conflict (owner_id, name) do update set vault_secret_id = excluded.vault_secret_id,
            configured = true, updated_at = excluded.updated_at;
    end loop;
    return query select c.name, c.configured, c.updated_at
    from public.provider_credentials c where c.owner_id = p_owner_id order by c.name;
end;
$$;

create or replace function public.read_provider_secret(p_owner_id uuid, p_name text)
returns text
language sql
security definer
set search_path = public, vault
as $$
    select ds.decrypted_secret
    from public.provider_credentials c
    join vault.decrypted_secrets ds on ds.id = c.vault_secret_id
    where c.owner_id = p_owner_id and c.name = p_name and c.configured;
$$;

create or replace function public.clear_provider_credential(p_owner_id uuid, p_name text)
returns table(name text, configured boolean, updated_at timestamptz)
language plpgsql
security definer
set search_path = public, vault
as $$
declare
    old_secret uuid;
begin
    select vault_secret_id into old_secret from public.provider_credentials
    where owner_id = p_owner_id and name = p_name;
    delete from public.provider_credentials where owner_id = p_owner_id and name = p_name;
    if old_secret is not null then
        delete from vault.secrets where id = old_secret;
    end if;
    return query select c.name, c.configured, c.updated_at
    from public.provider_credentials c where c.owner_id = p_owner_id order by c.name;
end;
$$;

create or replace function public.save_user_settings(p_owner_id uuid, p_settings jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    changed public.user_settings;
begin
    insert into public.user_settings (owner_id, display_name, default_max_tokens,
        default_max_cost_usd, default_max_llm_calls, updated_at)
    values (p_owner_id, p_settings->>'display_name',
        coalesce((p_settings->>'default_max_tokens')::integer, 500000),
        coalesce((p_settings->>'default_max_cost_usd')::numeric, 0.20),
        coalesce((p_settings->>'default_max_llm_calls')::integer, 160), now())
    on conflict (owner_id) do update set display_name = excluded.display_name,
        default_max_tokens = excluded.default_max_tokens,
        default_max_cost_usd = excluded.default_max_cost_usd,
        default_max_llm_calls = excluded.default_max_llm_calls,
        updated_at = excluded.updated_at
    returning * into changed;
    return jsonb_build_object('display_name', changed.display_name,
        'default_max_tokens', changed.default_max_tokens,
        'default_max_cost_usd', changed.default_max_cost_usd,
        'default_max_llm_calls', changed.default_max_llm_calls);
end;
$$;

revoke all on function public.read_provider_secret(uuid, text) from public, anon, authenticated;
grant execute on function public.read_provider_secret(uuid, text) to service_role;
grant execute on function public.create_research_run(uuid, jsonb) to service_role;
grant execute on function public.cancel_research_run(uuid, uuid) to service_role;
grant execute on function public.claim_research_job(text, integer) to service_role;
grant execute on function public.heartbeat_research_job(uuid, text, jsonb) to service_role;
grant execute on function public.complete_research_job(uuid, text, jsonb) to service_role;
grant execute on function public.fail_research_job(uuid, text, text, boolean) to service_role;
grant execute on function public.import_local_history(uuid, jsonb) to service_role;
grant execute on function public.save_provider_credentials(uuid, jsonb) to service_role;
grant execute on function public.read_provider_secret(uuid, text) to service_role;
grant execute on function public.clear_provider_credential(uuid, text) to service_role;
grant execute on function public.save_user_settings(uuid, jsonb) to service_role;
