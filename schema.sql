\restrict e0w5R3RKr01eXOOmLnrQcipvPcCmtU8gXxHOWVYJQKT40uctLMEnW8lPavXxeQd

-- Dumped from database version 14.19 (Homebrew)
-- Dumped by pg_dump version 14.19 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: chart_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.chart_type AS ENUM (
    'line',
    'bar',
    'pie',
    'number',
    'table',
    'funnel'
);


--
-- Name: member_role; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.member_role AS ENUM (
    'admin',
    'analyst',
    'viewer'
);


--
-- Name: create_events_partition(date); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.create_events_partition(p_month date) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE
    start_ts  timestamptz := date_trunc('month', p_month::timestamp) AT TIME ZONE 'UTC';
    end_ts    timestamptz := (date_trunc('month', p_month::timestamp) + interval '1 month') AT TIME ZONE 'UTC';
    part_name text        := format('events_%s', to_char(p_month, 'YYYY_MM'));
BEGIN
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF events FOR VALUES FROM (%L) TO (%L)',
        part_name, start_ts, end_ts
    );
    RETURN part_name;
END;
$$;


--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alert_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_history (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    rule_id uuid NOT NULL,
    triggered_at timestamp with time zone DEFAULT now() NOT NULL,
    observed_value numeric,
    status text NOT NULL,
    details jsonb,
    CONSTRAINT ck_alert_history_status CHECK ((status = ANY (ARRAY['sent'::text, 'failed'::text])))
);


--
-- Name: alert_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_rules (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    name text NOT NULL,
    trigger_type text NOT NULL,
    event_name text NOT NULL,
    metric text DEFAULT 'count'::text NOT NULL,
    operator text,
    threshold numeric,
    window_minutes integer,
    filters jsonb DEFAULT '[]'::jsonb NOT NULL,
    channels jsonb NOT NULL,
    cooldown_minutes integer DEFAULT 60 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    last_evaluated_at timestamp with time zone,
    last_triggered_at timestamp with time zone,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_alert_rules_cooldown CHECK ((cooldown_minutes >= 0)),
    CONSTRAINT ck_alert_rules_metric CHECK ((metric = ANY (ARRAY['count'::text, 'unique_persons'::text]))),
    CONSTRAINT ck_alert_rules_operator CHECK ((operator = ANY (ARRAY['>'::text, '>='::text, '<'::text, '<='::text]))),
    CONSTRAINT ck_alert_rules_threshold_fields CHECK (((trigger_type = 'on_event'::text) OR ((operator IS NOT NULL) AND (threshold IS NOT NULL) AND (window_minutes IS NOT NULL)))),
    CONSTRAINT ck_alert_rules_trigger_type CHECK ((trigger_type = ANY (ARRAY['on_event'::text, 'threshold'::text]))),
    CONSTRAINT ck_alert_rules_window CHECK ((window_minutes > 0))
);


--
-- Name: api_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.api_keys (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    name text NOT NULL,
    key_prefix character varying(16) NOT NULL,
    key_hash text NOT NULL,
    last_used_at timestamp with time zone,
    revoked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: dashboards; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dashboards (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    is_default boolean DEFAULT false NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: event_daily_stats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.event_daily_stats (
    project_id uuid NOT NULL,
    day date NOT NULL,
    event_name text NOT NULL,
    event_count bigint NOT NULL,
    unique_persons integer NOT NULL
);


--
-- Name: event_definitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.event_definitions (
    project_id uuid NOT NULL,
    event_name text NOT NULL,
    description text,
    first_seen_at timestamp with time zone NOT NULL,
    last_seen_at timestamp with time zone NOT NULL
);


--
-- Name: events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.events (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    event_name text NOT NULL,
    distinct_id text NOT NULL,
    person_id uuid,
    session_id uuid,
    occurred_at timestamp with time zone NOT NULL,
    received_at timestamp with time zone DEFAULT now() NOT NULL,
    source text DEFAULT 'api'::text NOT NULL,
    path text,
    screen_name text,
    platform text,
    os text,
    browser text,
    device_type text,
    app_version text,
    country character(2),
    properties jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT ck_events_source CHECK ((source = ANY (ARRAY['api'::text, 'csv'::text, 'excel'::text])))
)
PARTITION BY RANGE (occurred_at);


--
-- Name: events_2026_10; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.events_2026_10 (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    event_name text NOT NULL,
    distinct_id text NOT NULL,
    person_id uuid,
    session_id uuid,
    occurred_at timestamp with time zone NOT NULL,
    received_at timestamp with time zone DEFAULT now() NOT NULL,
    source text DEFAULT 'api'::text NOT NULL,
    path text,
    screen_name text,
    platform text,
    os text,
    browser text,
    device_type text,
    app_version text,
    country character(2),
    properties jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT ck_events_source CHECK ((source = ANY (ARRAY['api'::text, 'csv'::text, 'excel'::text])))
);


--
-- Name: events_2026_11; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.events_2026_11 (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    event_name text NOT NULL,
    distinct_id text NOT NULL,
    person_id uuid,
    session_id uuid,
    occurred_at timestamp with time zone NOT NULL,
    received_at timestamp with time zone DEFAULT now() NOT NULL,
    source text DEFAULT 'api'::text NOT NULL,
    path text,
    screen_name text,
    platform text,
    os text,
    browser text,
    device_type text,
    app_version text,
    country character(2),
    properties jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT ck_events_source CHECK ((source = ANY (ARRAY['api'::text, 'csv'::text, 'excel'::text])))
);


--
-- Name: events_2026_12; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.events_2026_12 (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    event_name text NOT NULL,
    distinct_id text NOT NULL,
    person_id uuid,
    session_id uuid,
    occurred_at timestamp with time zone NOT NULL,
    received_at timestamp with time zone DEFAULT now() NOT NULL,
    source text DEFAULT 'api'::text NOT NULL,
    path text,
    screen_name text,
    platform text,
    os text,
    browser text,
    device_type text,
    app_version text,
    country character(2),
    properties jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT ck_events_source CHECK ((source = ANY (ARRAY['api'::text, 'csv'::text, 'excel'::text])))
);


--
-- Name: events_default; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.events_default (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    event_name text NOT NULL,
    distinct_id text NOT NULL,
    person_id uuid,
    session_id uuid,
    occurred_at timestamp with time zone NOT NULL,
    received_at timestamp with time zone DEFAULT now() NOT NULL,
    source text DEFAULT 'api'::text NOT NULL,
    path text,
    screen_name text,
    platform text,
    os text,
    browser text,
    device_type text,
    app_version text,
    country character(2),
    properties jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT ck_events_source CHECK ((source = ANY (ARRAY['api'::text, 'csv'::text, 'excel'::text])))
);


--
-- Name: organization_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organization_members (
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role public.member_role DEFAULT 'viewer'::public.member_role NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organizations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    slug text NOT NULL,
    plan text DEFAULT 'free'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean DEFAULT true NOT NULL
);


--
-- Name: persons; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.persons (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    distinct_id text NOT NULL,
    properties jsonb DEFAULT '{}'::jsonb NOT NULL,
    first_seen_at timestamp with time zone NOT NULL,
    last_seen_at timestamp with time zone NOT NULL
);


--
-- Name: project_daily_stats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_daily_stats (
    project_id uuid NOT NULL,
    day date NOT NULL,
    active_users integer NOT NULL,
    new_users integer NOT NULL,
    sessions integer NOT NULL,
    total_events bigint NOT NULL,
    avg_session_seconds integer NOT NULL,
    bounce_rate numeric(5,2)
);


--
-- Name: projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.projects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    name text NOT NULL,
    platform text NOT NULL,
    timezone text DEFAULT 'UTC'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    allowed_origins text[] DEFAULT '{}'::text[] NOT NULL,
    CONSTRAINT ck_projects_platform CHECK ((platform = ANY (ARRAY['web'::text, 'ios'::text, 'android'::text, 'flutter'::text, 'other'::text])))
);


--
-- Name: refresh_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.refresh_tokens (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    token_hash text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    version character varying NOT NULL
);


--
-- Name: sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sessions (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    person_id uuid,
    started_at timestamp with time zone NOT NULL,
    ended_at timestamp with time zone,
    event_count integer DEFAULT 0 NOT NULL,
    entry_path text,
    exit_path text,
    referrer text,
    utm_source text,
    utm_medium text,
    utm_campaign text,
    device_type text,
    os text,
    browser text,
    app_version text,
    country character(2)
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email text NOT NULL,
    password_hash text NOT NULL,
    full_name text,
    is_active boolean DEFAULT true NOT NULL,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    is_superadmin boolean DEFAULT false NOT NULL
);


--
-- Name: widgets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.widgets (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    dashboard_id uuid NOT NULL,
    title text NOT NULL,
    chart_type public.chart_type NOT NULL,
    query jsonb NOT NULL,
    layout jsonb DEFAULT '{"h": 4, "w": 6, "x": 0, "y": 0}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: events_2026_10; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events ATTACH PARTITION public.events_2026_10 FOR VALUES FROM ('2026-10-01 05:30:00+05:30') TO ('2026-11-01 05:30:00+05:30');


--
-- Name: events_2026_11; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events ATTACH PARTITION public.events_2026_11 FOR VALUES FROM ('2026-11-01 05:30:00+05:30') TO ('2026-12-01 05:30:00+05:30');


--
-- Name: events_2026_12; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events ATTACH PARTITION public.events_2026_12 FOR VALUES FROM ('2026-12-01 05:30:00+05:30') TO ('2027-01-01 05:30:00+05:30');


--
-- Name: events_default; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events ATTACH PARTITION public.events_default DEFAULT;


--
-- Name: alert_history alert_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_history
    ADD CONSTRAINT alert_history_pkey PRIMARY KEY (id);


--
-- Name: alert_rules alert_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_rules
    ADD CONSTRAINT alert_rules_pkey PRIMARY KEY (id);


--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);


--
-- Name: dashboards dashboards_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboards
    ADD CONSTRAINT dashboards_pkey PRIMARY KEY (id);


--
-- Name: event_daily_stats event_daily_stats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_daily_stats
    ADD CONSTRAINT event_daily_stats_pkey PRIMARY KEY (project_id, day, event_name);


--
-- Name: event_definitions event_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_definitions
    ADD CONSTRAINT event_definitions_pkey PRIMARY KEY (project_id, event_name);


--
-- Name: events pk_events; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT pk_events PRIMARY KEY (project_id, occurred_at, id);


--
-- Name: events_2026_10 events_2026_10_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events_2026_10
    ADD CONSTRAINT events_2026_10_pkey PRIMARY KEY (project_id, occurred_at, id);


--
-- Name: events_2026_11 events_2026_11_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events_2026_11
    ADD CONSTRAINT events_2026_11_pkey PRIMARY KEY (project_id, occurred_at, id);


--
-- Name: events_2026_12 events_2026_12_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events_2026_12
    ADD CONSTRAINT events_2026_12_pkey PRIMARY KEY (project_id, occurred_at, id);


--
-- Name: events_default events_default_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events_default
    ADD CONSTRAINT events_default_pkey PRIMARY KEY (project_id, occurred_at, id);


--
-- Name: organization_members organization_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_members
    ADD CONSTRAINT organization_members_pkey PRIMARY KEY (organization_id, user_id);


--
-- Name: organizations organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);


--
-- Name: persons persons_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.persons
    ADD CONSTRAINT persons_pkey PRIMARY KEY (id);


--
-- Name: project_daily_stats project_daily_stats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_daily_stats
    ADD CONSTRAINT project_daily_stats_pkey PRIMARY KEY (project_id, day);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: refresh_tokens refresh_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_pkey PRIMARY KEY (id);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: sessions sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);


--
-- Name: api_keys uq_api_keys_key_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT uq_api_keys_key_hash UNIQUE (key_hash);


--
-- Name: organizations uq_organizations_slug; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT uq_organizations_slug UNIQUE (slug);


--
-- Name: persons uq_persons_project_distinct; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.persons
    ADD CONSTRAINT uq_persons_project_distinct UNIQUE (project_id, distinct_id);


--
-- Name: refresh_tokens uq_refresh_tokens_token_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT uq_refresh_tokens_token_hash UNIQUE (token_hash);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: widgets widgets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.widgets
    ADD CONSTRAINT widgets_pkey PRIMARY KEY (id);


--
-- Name: ix_events_project_distinct_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_events_project_distinct_time ON ONLY public.events USING btree (project_id, distinct_id, occurred_at);


--
-- Name: events_2026_10_project_id_distinct_id_occurred_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_2026_10_project_id_distinct_id_occurred_at_idx ON public.events_2026_10 USING btree (project_id, distinct_id, occurred_at);


--
-- Name: ix_events_project_name_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_events_project_name_time ON ONLY public.events USING btree (project_id, event_name, occurred_at);


--
-- Name: events_2026_10_project_id_event_name_occurred_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_2026_10_project_id_event_name_occurred_at_idx ON public.events_2026_10 USING btree (project_id, event_name, occurred_at);


--
-- Name: ix_events_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_events_project_id ON ONLY public.events USING btree (project_id, id);


--
-- Name: events_2026_10_project_id_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_2026_10_project_id_id_idx ON public.events_2026_10 USING btree (project_id, id);


--
-- Name: ix_events_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_events_session_id ON ONLY public.events USING btree (session_id);


--
-- Name: events_2026_10_session_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_2026_10_session_id_idx ON public.events_2026_10 USING btree (session_id);


--
-- Name: events_2026_11_project_id_distinct_id_occurred_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_2026_11_project_id_distinct_id_occurred_at_idx ON public.events_2026_11 USING btree (project_id, distinct_id, occurred_at);


--
-- Name: events_2026_11_project_id_event_name_occurred_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_2026_11_project_id_event_name_occurred_at_idx ON public.events_2026_11 USING btree (project_id, event_name, occurred_at);


--
-- Name: events_2026_11_project_id_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_2026_11_project_id_id_idx ON public.events_2026_11 USING btree (project_id, id);


--
-- Name: events_2026_11_session_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_2026_11_session_id_idx ON public.events_2026_11 USING btree (session_id);


--
-- Name: events_2026_12_project_id_distinct_id_occurred_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_2026_12_project_id_distinct_id_occurred_at_idx ON public.events_2026_12 USING btree (project_id, distinct_id, occurred_at);


--
-- Name: events_2026_12_project_id_event_name_occurred_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_2026_12_project_id_event_name_occurred_at_idx ON public.events_2026_12 USING btree (project_id, event_name, occurred_at);


--
-- Name: events_2026_12_project_id_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_2026_12_project_id_id_idx ON public.events_2026_12 USING btree (project_id, id);


--
-- Name: events_2026_12_session_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_2026_12_session_id_idx ON public.events_2026_12 USING btree (session_id);


--
-- Name: events_default_project_id_distinct_id_occurred_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_default_project_id_distinct_id_occurred_at_idx ON public.events_default USING btree (project_id, distinct_id, occurred_at);


--
-- Name: events_default_project_id_event_name_occurred_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_default_project_id_event_name_occurred_at_idx ON public.events_default USING btree (project_id, event_name, occurred_at);


--
-- Name: events_default_project_id_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_default_project_id_id_idx ON public.events_default USING btree (project_id, id);


--
-- Name: events_default_session_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX events_default_session_id_idx ON public.events_default USING btree (session_id);


--
-- Name: ix_alert_history_rule_triggered; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_history_rule_triggered ON public.alert_history USING btree (rule_id, triggered_at DESC);


--
-- Name: ix_alert_rules_project_event; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_rules_project_event ON public.alert_rules USING btree (project_id, event_name);


--
-- Name: ix_api_keys_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_keys_project_id ON public.api_keys USING btree (project_id);


--
-- Name: ix_dashboards_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dashboards_project_id ON public.dashboards USING btree (project_id);


--
-- Name: ix_organization_members_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_organization_members_user_id ON public.organization_members USING btree (user_id);


--
-- Name: ix_projects_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_projects_organization_id ON public.projects USING btree (organization_id);


--
-- Name: ix_refresh_tokens_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_refresh_tokens_user_id ON public.refresh_tokens USING btree (user_id);


--
-- Name: ix_sessions_person_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sessions_person_id ON public.sessions USING btree (person_id);


--
-- Name: ix_sessions_project_started; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sessions_project_started ON public.sessions USING btree (project_id, started_at DESC);


--
-- Name: ix_widgets_dashboard_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_widgets_dashboard_id ON public.widgets USING btree (dashboard_id);


--
-- Name: uq_users_email_lower; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_users_email_lower ON public.users USING btree (lower(email));


--
-- Name: events_2026_10_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_events ATTACH PARTITION public.events_2026_10_pkey;


--
-- Name: events_2026_10_project_id_distinct_id_occurred_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_project_distinct_time ATTACH PARTITION public.events_2026_10_project_id_distinct_id_occurred_at_idx;


--
-- Name: events_2026_10_project_id_event_name_occurred_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_project_name_time ATTACH PARTITION public.events_2026_10_project_id_event_name_occurred_at_idx;


--
-- Name: events_2026_10_project_id_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_project_id ATTACH PARTITION public.events_2026_10_project_id_id_idx;


--
-- Name: events_2026_10_session_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_session_id ATTACH PARTITION public.events_2026_10_session_id_idx;


--
-- Name: events_2026_11_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_events ATTACH PARTITION public.events_2026_11_pkey;


--
-- Name: events_2026_11_project_id_distinct_id_occurred_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_project_distinct_time ATTACH PARTITION public.events_2026_11_project_id_distinct_id_occurred_at_idx;


--
-- Name: events_2026_11_project_id_event_name_occurred_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_project_name_time ATTACH PARTITION public.events_2026_11_project_id_event_name_occurred_at_idx;


--
-- Name: events_2026_11_project_id_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_project_id ATTACH PARTITION public.events_2026_11_project_id_id_idx;


--
-- Name: events_2026_11_session_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_session_id ATTACH PARTITION public.events_2026_11_session_id_idx;


--
-- Name: events_2026_12_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_events ATTACH PARTITION public.events_2026_12_pkey;


--
-- Name: events_2026_12_project_id_distinct_id_occurred_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_project_distinct_time ATTACH PARTITION public.events_2026_12_project_id_distinct_id_occurred_at_idx;


--
-- Name: events_2026_12_project_id_event_name_occurred_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_project_name_time ATTACH PARTITION public.events_2026_12_project_id_event_name_occurred_at_idx;


--
-- Name: events_2026_12_project_id_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_project_id ATTACH PARTITION public.events_2026_12_project_id_id_idx;


--
-- Name: events_2026_12_session_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_session_id ATTACH PARTITION public.events_2026_12_session_id_idx;


--
-- Name: events_default_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_events ATTACH PARTITION public.events_default_pkey;


--
-- Name: events_default_project_id_distinct_id_occurred_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_project_distinct_time ATTACH PARTITION public.events_default_project_id_distinct_id_occurred_at_idx;


--
-- Name: events_default_project_id_event_name_occurred_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_project_name_time ATTACH PARTITION public.events_default_project_id_event_name_occurred_at_idx;


--
-- Name: events_default_project_id_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_project_id ATTACH PARTITION public.events_default_project_id_id_idx;


--
-- Name: events_default_session_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_events_session_id ATTACH PARTITION public.events_default_session_id_idx;


--
-- Name: dashboards trg_dashboards_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_dashboards_updated_at BEFORE UPDATE ON public.dashboards FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: widgets trg_widgets_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_widgets_updated_at BEFORE UPDATE ON public.widgets FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: alert_history alert_history_rule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_history
    ADD CONSTRAINT alert_history_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES public.alert_rules(id) ON DELETE CASCADE;


--
-- Name: alert_rules alert_rules_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_rules
    ADD CONSTRAINT alert_rules_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: alert_rules alert_rules_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_rules
    ADD CONSTRAINT alert_rules_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: api_keys api_keys_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: dashboards dashboards_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboards
    ADD CONSTRAINT dashboards_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: dashboards dashboards_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboards
    ADD CONSTRAINT dashboards_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: event_definitions event_definitions_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_definitions
    ADD CONSTRAINT event_definitions_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: organization_members organization_members_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_members
    ADD CONSTRAINT organization_members_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: organization_members organization_members_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_members
    ADD CONSTRAINT organization_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: persons persons_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.persons
    ADD CONSTRAINT persons_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: projects projects_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: refresh_tokens refresh_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: sessions sessions_person_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.persons(id) ON DELETE SET NULL;


--
-- Name: sessions sessions_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: widgets widgets_dashboard_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.widgets
    ADD CONSTRAINT widgets_dashboard_id_fkey FOREIGN KEY (dashboard_id) REFERENCES public.dashboards(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict e0w5R3RKr01eXOOmLnrQcipvPcCmtU8gXxHOWVYJQKT40uctLMEnW8lPavXxeQd


--
-- Dbmate schema migrations
--

INSERT INTO public.schema_migrations (version) VALUES
    ('20261017100000'),
    ('20261017100100'),
    ('20261017100200'),
    ('20261017100300'),
    ('20261017100400'),
    ('20261017100500'),
    ('20261017100600'),
    ('20261017100700'),
    ('20261017100800'),
    ('20261017100900'),
    ('20261017101000'),
    ('20261017101100'),
    ('20261017101200'),
    ('20261017101300'),
    ('20261017101400'),
    ('20261017101500'),
    ('20261017101600'),
    ('20261018141153'),
    ('20261020105109'),
    ('20261026183433');
