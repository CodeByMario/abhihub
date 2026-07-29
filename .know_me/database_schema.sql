-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE abhihub.colleges (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  abbreviation text,
  city text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT colleges_pkey PRIMARY KEY (id)
);
CREATE TABLE abhihub.departments (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  abbreviation text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT departments_pkey PRIMARY KEY (id)
);
CREATE TABLE abhihub.subjects (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  department_id uuid NOT NULL,
  name text NOT NULL,
  subject_code text NOT NULL,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT subjects_pkey PRIMARY KEY (id),
  CONSTRAINT subjects_department_id_fkey FOREIGN KEY (department_id) REFERENCES abhihub.departments(id)
);
CREATE TABLE abhihub.profiles (
  id uuid NOT NULL,
  role USER-DEFINED NOT NULL DEFAULT 'student'::abhihub.user_role,
  email text NOT NULL UNIQUE,
  full_name text NOT NULL,
  phone_number text,
  college_id uuid,
  department_id uuid,
  subscription_tier USER-DEFINED DEFAULT 'free'::abhihub.subscription_tier,
  subscription_expires_at timestamp with time zone,
  reputation_score numeric DEFAULT 0,
  rank_title text DEFAULT 'Beginner'::text,
  is_verified boolean DEFAULT false,
  verified_by uuid,
  verified_at timestamp with time zone,
  referral_code text UNIQUE,
  referred_by uuid,
  total_active_minutes integer DEFAULT 0,
  last_active_at timestamp with time zone DEFAULT now(),
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  paper_quota_remaining integer DEFAULT 19,
  last_quota_reset text DEFAULT '2026-05'::text,
  CONSTRAINT profiles_pkey PRIMARY KEY (id),
  CONSTRAINT profiles_id_fkey FOREIGN KEY (id) REFERENCES auth.users(id),
  CONSTRAINT profiles_college_id_fkey FOREIGN KEY (college_id) REFERENCES abhihub.colleges(id),
  CONSTRAINT profiles_department_id_fkey FOREIGN KEY (department_id) REFERENCES abhihub.departments(id),
  CONSTRAINT profiles_verified_by_fkey FOREIGN KEY (verified_by) REFERENCES auth.users(id),
  CONSTRAINT profiles_referred_by_fkey FOREIGN KEY (referred_by) REFERENCES auth.users(id)
);
CREATE TABLE abhihub.students (
  profile_id uuid NOT NULL,
  registration_number text,
  pursuing_year integer,
  year_of_joining integer,
  profile_completed boolean DEFAULT false,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT students_pkey PRIMARY KEY (profile_id),
  CONSTRAINT students_profile_id_fkey FOREIGN KEY (profile_id) REFERENCES abhihub.profiles(id)
);
CREATE TABLE abhihub.teachers (
  profile_id uuid NOT NULL,
  employee_id text,
  designation text,
  profile_completed boolean DEFAULT false,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT teachers_pkey PRIMARY KEY (profile_id),
  CONSTRAINT teachers_profile_id_fkey FOREIGN KEY (profile_id) REFERENCES abhihub.profiles(id)
);
CREATE TABLE abhihub.user_sessions (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  login_time timestamp with time zone DEFAULT now(),
  logout_time timestamp with time zone,
  duration_minutes integer,
  ip_address text,
  user_agent text,
  device_type text,
  CONSTRAINT user_sessions_pkey PRIMARY KEY (id),
  CONSTRAINT user_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES abhihub.profiles(id)
);
CREATE TABLE abhihub.documents (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  uploader_id uuid,
  college_id uuid,
  department_id uuid,
  subject_id uuid,
  title text NOT NULL,
  document_category text NOT NULL,
  description text,
  file_url text NOT NULL UNIQUE,
  storage_provider USER-DEFINED NOT NULL,
  provider_public_id text,
  file_type text,
  file_size_bytes bigint,
  status USER-DEFINED DEFAULT 'pending'::abhihub.verification_state,
  verified_by uuid,
  verification_notes text,
  verified_at timestamp with time zone,
  view_count integer DEFAULT 0,
  like_count integer DEFAULT 0,
  bookmark_count integer DEFAULT 0,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT documents_pkey PRIMARY KEY (id),
  CONSTRAINT documents_uploader_id_fkey FOREIGN KEY (uploader_id) REFERENCES abhihub.profiles(id),
  CONSTRAINT documents_college_id_fkey FOREIGN KEY (college_id) REFERENCES abhihub.colleges(id),
  CONSTRAINT documents_department_id_fkey FOREIGN KEY (department_id) REFERENCES abhihub.departments(id),
  CONSTRAINT documents_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES abhihub.subjects(id),
  CONSTRAINT documents_verified_by_fkey FOREIGN KEY (verified_by) REFERENCES abhihub.profiles(id)
);
CREATE TABLE abhihub.bookmarks (
  user_id uuid NOT NULL,
  document_id uuid NOT NULL,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT bookmarks_pkey PRIMARY KEY (user_id, document_id),
  CONSTRAINT bookmarks_document_id_fkey FOREIGN KEY (document_id) REFERENCES abhihub.documents(id),
  CONSTRAINT bookmarks_user_id_fkey FOREIGN KEY (user_id) REFERENCES abhihub.profiles(id)
);
CREATE TABLE abhihub.document_comments (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL,
  user_id uuid NOT NULL,
  content text NOT NULL,
  is_deleted boolean DEFAULT false,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT document_comments_pkey PRIMARY KEY (id),
  CONSTRAINT document_comments_document_id_fkey FOREIGN KEY (document_id) REFERENCES abhihub.documents(id),
  CONSTRAINT document_comments_user_id_fkey FOREIGN KEY (user_id) REFERENCES abhihub.profiles(id)
);
CREATE TABLE abhihub.tags (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT tags_pkey PRIMARY KEY (id)
);
CREATE TABLE abhihub.document_tags (
  document_id uuid NOT NULL,
  tag_id uuid NOT NULL,
  CONSTRAINT document_tags_pkey PRIMARY KEY (document_id, tag_id),
  CONSTRAINT document_tags_document_id_fkey FOREIGN KEY (document_id) REFERENCES abhihub.documents(id),
  CONSTRAINT document_tags_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES abhihub.tags(id)
);
CREATE TABLE abhihub.document_views (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL,
  user_id uuid,
  ip_address text,
  device_type text,
  accessed_at timestamp with time zone DEFAULT now(),
  CONSTRAINT document_views_pkey PRIMARY KEY (id),
  CONSTRAINT document_views_document_id_fkey FOREIGN KEY (document_id) REFERENCES abhihub.documents(id),
  CONSTRAINT document_views_user_id_fkey FOREIGN KEY (user_id) REFERENCES abhihub.profiles(id)
);
CREATE TABLE abhihub.document_votes (
  document_id uuid NOT NULL,
  user_id uuid NOT NULL,
  vote USER-DEFINED NOT NULL,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT document_votes_pkey PRIMARY KEY (document_id, user_id),
  CONSTRAINT document_votes_document_id_fkey FOREIGN KEY (document_id) REFERENCES abhihub.documents(id),
  CONSTRAINT document_votes_user_id_fkey FOREIGN KEY (user_id) REFERENCES abhihub.profiles(id)
);
CREATE TABLE abhihub.security_audit_logs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid,
  document_id uuid,
  event USER-DEFINED NOT NULL,
  ip_address text,
  user_agent text,
  metadata jsonb,
  detected_at timestamp with time zone DEFAULT now(),
  CONSTRAINT security_audit_logs_pkey PRIMARY KEY (id),
  CONSTRAINT security_audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES abhihub.profiles(id),
  CONSTRAINT security_audit_logs_document_id_fkey FOREIGN KEY (document_id) REFERENCES abhihub.documents(id)
);
CREATE TABLE abhihub.push_subscriptions (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  endpoint text NOT NULL UNIQUE,
  p256dh text NOT NULL,
  auth text NOT NULL,
  device_type text,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT push_subscriptions_pkey PRIMARY KEY (id),
  CONSTRAINT push_subscriptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES abhihub.profiles(id)
);
CREATE TABLE abhihub.notifications (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  type USER-DEFINED NOT NULL,
  title text NOT NULL,
  message text NOT NULL,
  action_url text,
  is_read boolean DEFAULT false,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT notifications_pkey PRIMARY KEY (id),
  CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES abhihub.profiles(id)
);
CREATE TABLE abhihub.memory_wall (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id text NOT NULL,
  slug text NOT NULL UNIQUE,
  title text,
  photo_url text,
  college text,
  branch text,
  graduation_year integer,
  status text DEFAULT 'active'::text CHECK (status = ANY (ARRAY['active'::text, 'closed'::text])),
  response_count integer DEFAULT 0,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  view_count integer DEFAULT 0,
  CONSTRAINT memory_wall_pkey PRIMARY KEY (id)
);
CREATE TABLE abhihub.memory_response (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  wall_id uuid NOT NULL,
  friend_name text NOT NULL,
  word_1 text NOT NULL,
  word_2 text NOT NULL,
  word_3 text NOT NULL,
  memory_message text,
  emoji text,
  anonymous boolean DEFAULT false,
  ip_hash text,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT memory_response_pkey PRIMARY KEY (id),
  CONSTRAINT memory_response_wall_id_fkey FOREIGN KEY (wall_id) REFERENCES abhihub.memory_wall(id)
);
CREATE TABLE abhihub.signature (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  response_id uuid NOT NULL,
  signature_url text,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT signature_pkey PRIMARY KEY (id),
  CONSTRAINT signature_response_id_fkey FOREIGN KEY (response_id) REFERENCES abhihub.memory_response(id)
);

-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE auth.audit_log_entries (
  instance_id uuid,
  id uuid NOT NULL,
  payload json,
  created_at timestamp with time zone,
  ip_address character varying NOT NULL DEFAULT ''::character varying,
  CONSTRAINT audit_log_entries_pkey PRIMARY KEY (id)
);
CREATE TABLE auth.flow_state (
  id uuid NOT NULL,
  user_id uuid,
  auth_code text,
  code_challenge_method USER-DEFINED,
  code_challenge text,
  provider_type text NOT NULL,
  provider_access_token text,
  provider_refresh_token text,
  created_at timestamp with time zone,
  updated_at timestamp with time zone,
  authentication_method text NOT NULL,
  auth_code_issued_at timestamp with time zone,
  invite_token text,
  referrer text,
  oauth_client_state_id uuid,
  linking_target_id uuid,
  email_optional boolean NOT NULL DEFAULT false,
  CONSTRAINT flow_state_pkey PRIMARY KEY (id)
);
CREATE TABLE auth.identities (
  provider_id text NOT NULL,
  user_id uuid NOT NULL,
  identity_data jsonb NOT NULL,
  provider text NOT NULL,
  last_sign_in_at timestamp with time zone,
  created_at timestamp with time zone,
  updated_at timestamp with time zone,
  email text DEFAULT lower((identity_data ->> 'email'::text)),
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  CONSTRAINT identities_pkey PRIMARY KEY (id),
  CONSTRAINT identities_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id)
);
CREATE TABLE auth.instances (
  id uuid NOT NULL,
  uuid uuid,
  raw_base_config text,
  created_at timestamp with time zone,
  updated_at timestamp with time zone,
  CONSTRAINT instances_pkey PRIMARY KEY (id)
);
CREATE TABLE auth.mfa_amr_claims (
  session_id uuid NOT NULL,
  created_at timestamp with time zone NOT NULL,
  updated_at timestamp with time zone NOT NULL,
  authentication_method text NOT NULL,
  id uuid NOT NULL,
  CONSTRAINT mfa_amr_claims_pkey PRIMARY KEY (id),
  CONSTRAINT mfa_amr_claims_session_id_fkey FOREIGN KEY (session_id) REFERENCES auth.sessions(id)
);
CREATE TABLE auth.mfa_challenges (
  id uuid NOT NULL,
  factor_id uuid NOT NULL,
  created_at timestamp with time zone NOT NULL,
  verified_at timestamp with time zone,
  ip_address inet NOT NULL,
  otp_code text,
  web_authn_session_data jsonb,
  CONSTRAINT mfa_challenges_pkey PRIMARY KEY (id),
  CONSTRAINT mfa_challenges_auth_factor_id_fkey FOREIGN KEY (factor_id) REFERENCES auth.mfa_factors(id)
);
CREATE TABLE auth.mfa_factors (
  id uuid NOT NULL,
  user_id uuid NOT NULL,
  friendly_name text,
  factor_type USER-DEFINED NOT NULL,
  status USER-DEFINED NOT NULL,
  created_at timestamp with time zone NOT NULL,
  updated_at timestamp with time zone NOT NULL,
  secret text,
  phone text,
  last_challenged_at timestamp with time zone UNIQUE,
  web_authn_credential jsonb,
  web_authn_aaguid uuid,
  last_webauthn_challenge_data jsonb,
  CONSTRAINT mfa_factors_pkey PRIMARY KEY (id),
  CONSTRAINT mfa_factors_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id)
);
CREATE TABLE auth.one_time_tokens (
  id uuid NOT NULL,
  user_id uuid NOT NULL,
  token_type USER-DEFINED NOT NULL,
  token_hash text NOT NULL CHECK (char_length(token_hash) > 0),
  relates_to text NOT NULL,
  created_at timestamp without time zone NOT NULL DEFAULT now(),
  updated_at timestamp without time zone NOT NULL DEFAULT now(),
  CONSTRAINT one_time_tokens_pkey PRIMARY KEY (id),
  CONSTRAINT one_time_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id)
);
CREATE TABLE auth.refresh_tokens (
  instance_id uuid,
  id bigint NOT NULL DEFAULT nextval('auth.refresh_tokens_id_seq'::regclass),
  token character varying UNIQUE,
  user_id character varying,
  revoked boolean,
  created_at timestamp with time zone,
  updated_at timestamp with time zone,
  parent character varying,
  session_id uuid,
  CONSTRAINT refresh_tokens_pkey PRIMARY KEY (id),
  CONSTRAINT refresh_tokens_session_id_fkey FOREIGN KEY (session_id) REFERENCES auth.sessions(id)
);
CREATE TABLE auth.saml_providers (
  id uuid NOT NULL,
  sso_provider_id uuid NOT NULL,
  entity_id text NOT NULL UNIQUE CHECK (char_length(entity_id) > 0),
  metadata_xml text NOT NULL CHECK (char_length(metadata_xml) > 0),
  metadata_url text CHECK (metadata_url = NULL::text OR char_length(metadata_url) > 0),
  attribute_mapping jsonb,
  created_at timestamp with time zone,
  updated_at timestamp with time zone,
  name_id_format text,
  CONSTRAINT saml_providers_pkey PRIMARY KEY (id),
  CONSTRAINT saml_providers_sso_provider_id_fkey FOREIGN KEY (sso_provider_id) REFERENCES auth.sso_providers(id)
);
CREATE TABLE auth.saml_relay_states (
  id uuid NOT NULL,
  sso_provider_id uuid NOT NULL,
  request_id text NOT NULL CHECK (char_length(request_id) > 0),
  for_email text,
  redirect_to text,
  created_at timestamp with time zone,
  updated_at timestamp with time zone,
  flow_state_id uuid,
  CONSTRAINT saml_relay_states_pkey PRIMARY KEY (id),
  CONSTRAINT saml_relay_states_flow_state_id_fkey FOREIGN KEY (flow_state_id) REFERENCES auth.flow_state(id),
  CONSTRAINT saml_relay_states_sso_provider_id_fkey FOREIGN KEY (sso_provider_id) REFERENCES auth.sso_providers(id)
);
CREATE TABLE auth.schema_migrations (
  version character varying NOT NULL,
  CONSTRAINT schema_migrations_pkey PRIMARY KEY (version)
);
CREATE TABLE auth.sessions (
  id uuid NOT NULL,
  user_id uuid NOT NULL,
  created_at timestamp with time zone,
  updated_at timestamp with time zone,
  factor_id uuid,
  aal USER-DEFINED,
  not_after timestamp with time zone,
  refreshed_at timestamp without time zone,
  user_agent text,
  ip inet,
  tag text,
  oauth_client_id uuid,
  refresh_token_hmac_key text,
  refresh_token_counter bigint,
  scopes text CHECK (char_length(scopes) <= 4096),
  CONSTRAINT sessions_pkey PRIMARY KEY (id),
  CONSTRAINT sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id),
  CONSTRAINT sessions_oauth_client_id_fkey FOREIGN KEY (oauth_client_id) REFERENCES auth.oauth_clients(id)
);
CREATE TABLE auth.sso_domains (
  id uuid NOT NULL,
  sso_provider_id uuid NOT NULL,
  domain text NOT NULL CHECK (char_length(domain) > 0),
  created_at timestamp with time zone,
  updated_at timestamp with time zone,
  CONSTRAINT sso_domains_pkey PRIMARY KEY (id),
  CONSTRAINT sso_domains_sso_provider_id_fkey FOREIGN KEY (sso_provider_id) REFERENCES auth.sso_providers(id)
);
CREATE TABLE auth.sso_providers (
  id uuid NOT NULL,
  resource_id text CHECK (resource_id = NULL::text OR char_length(resource_id) > 0),
  created_at timestamp with time zone,
  updated_at timestamp with time zone,
  disabled boolean,
  CONSTRAINT sso_providers_pkey PRIMARY KEY (id)
);
CREATE TABLE auth.users (
  instance_id uuid,
  id uuid NOT NULL,
  aud character varying,
  role character varying,
  email character varying,
  encrypted_password character varying,
  email_confirmed_at timestamp with time zone,
  invited_at timestamp with time zone,
  confirmation_token character varying,
  confirmation_sent_at timestamp with time zone,
  recovery_token character varying,
  recovery_sent_at timestamp with time zone,
  email_change_token_new character varying,
  email_change character varying,
  email_change_sent_at timestamp with time zone,
  last_sign_in_at timestamp with time zone,
  raw_app_meta_data jsonb,
  raw_user_meta_data jsonb,
  is_super_admin boolean,
  created_at timestamp with time zone,
  updated_at timestamp with time zone,
  phone text DEFAULT NULL::character varying UNIQUE,
  phone_confirmed_at timestamp with time zone,
  phone_change text DEFAULT ''::character varying,
  phone_change_token character varying DEFAULT ''::character varying,
  phone_change_sent_at timestamp with time zone,
  confirmed_at timestamp with time zone DEFAULT LEAST(email_confirmed_at, phone_confirmed_at),
  email_change_token_current character varying DEFAULT ''::character varying,
  email_change_confirm_status smallint DEFAULT 0 CHECK (email_change_confirm_status >= 0 AND email_change_confirm_status <= 2),
  banned_until timestamp with time zone,
  reauthentication_token character varying DEFAULT ''::character varying,
  reauthentication_sent_at timestamp with time zone,
  is_sso_user boolean NOT NULL DEFAULT false,
  deleted_at timestamp with time zone,
  is_anonymous boolean NOT NULL DEFAULT false,
  CONSTRAINT users_pkey PRIMARY KEY (id)
);
CREATE TABLE auth.oauth_clients (
  id uuid NOT NULL,
  client_secret_hash text,
  registration_type USER-DEFINED NOT NULL,
  redirect_uris text NOT NULL,
  grant_types text NOT NULL,
  client_name text CHECK (char_length(client_name) <= 1024),
  client_uri text CHECK (char_length(client_uri) <= 2048),
  logo_uri text CHECK (char_length(logo_uri) <= 2048),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  deleted_at timestamp with time zone,
  client_type USER-DEFINED NOT NULL DEFAULT 'confidential'::auth.oauth_client_type,
  token_endpoint_auth_method text NOT NULL CHECK (token_endpoint_auth_method = ANY (ARRAY['client_secret_basic'::text, 'client_secret_post'::text, 'none'::text])),
  CONSTRAINT oauth_clients_pkey PRIMARY KEY (id)
);
CREATE TABLE auth.oauth_authorizations (
  id uuid NOT NULL,
  authorization_id text NOT NULL UNIQUE,
  client_id uuid NOT NULL,
  user_id uuid,
  redirect_uri text NOT NULL CHECK (char_length(redirect_uri) <= 2048),
  scope text NOT NULL CHECK (char_length(scope) <= 4096),
  state text CHECK (char_length(state) <= 4096),
  resource text CHECK (char_length(resource) <= 2048),
  code_challenge text CHECK (char_length(code_challenge) <= 128),
  code_challenge_method USER-DEFINED,
  response_type USER-DEFINED NOT NULL DEFAULT 'code'::auth.oauth_response_type,
  status USER-DEFINED NOT NULL DEFAULT 'pending'::auth.oauth_authorization_status,
  authorization_code text UNIQUE CHECK (char_length(authorization_code) <= 255),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  expires_at timestamp with time zone NOT NULL DEFAULT (now() + '00:03:00'::interval),
  approved_at timestamp with time zone,
  nonce text CHECK (char_length(nonce) <= 255),
  CONSTRAINT oauth_authorizations_pkey PRIMARY KEY (id),
  CONSTRAINT oauth_authorizations_client_id_fkey FOREIGN KEY (client_id) REFERENCES auth.oauth_clients(id),
  CONSTRAINT oauth_authorizations_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id)
);
CREATE TABLE auth.oauth_consents (
  id uuid NOT NULL,
  user_id uuid NOT NULL,
  client_id uuid NOT NULL,
  scopes text NOT NULL CHECK (char_length(scopes) <= 2048),
  granted_at timestamp with time zone NOT NULL DEFAULT now(),
  revoked_at timestamp with time zone,
  CONSTRAINT oauth_consents_pkey PRIMARY KEY (id),
  CONSTRAINT oauth_consents_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id),
  CONSTRAINT oauth_consents_client_id_fkey FOREIGN KEY (client_id) REFERENCES auth.oauth_clients(id)
);
CREATE TABLE auth.oauth_client_states (
  id uuid NOT NULL,
  provider_type text NOT NULL,
  code_verifier text,
  created_at timestamp with time zone NOT NULL,
  CONSTRAINT oauth_client_states_pkey PRIMARY KEY (id)
);
CREATE TABLE auth.custom_oauth_providers (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  provider_type text NOT NULL CHECK (provider_type = ANY (ARRAY['oauth2'::text, 'oidc'::text])),
  identifier text NOT NULL UNIQUE CHECK (identifier ~ '^[a-z0-9][a-z0-9:-]{0,48}[a-z0-9]$'::text),
  name text NOT NULL CHECK (char_length(name) >= 1 AND char_length(name) <= 100),
  client_id text NOT NULL CHECK (char_length(client_id) >= 1 AND char_length(client_id) <= 512),
  client_secret text NOT NULL,
  acceptable_client_ids ARRAY NOT NULL DEFAULT '{}'::text[],
  scopes ARRAY NOT NULL DEFAULT '{}'::text[],
  pkce_enabled boolean NOT NULL DEFAULT true,
  attribute_mapping jsonb NOT NULL DEFAULT '{}'::jsonb,
  authorization_params jsonb NOT NULL DEFAULT '{}'::jsonb,
  enabled boolean NOT NULL DEFAULT true,
  email_optional boolean NOT NULL DEFAULT false,
  issuer text CHECK (issuer IS NULL OR char_length(issuer) >= 1 AND char_length(issuer) <= 2048),
  discovery_url text CHECK (discovery_url IS NULL OR char_length(discovery_url) <= 2048),
  skip_nonce_check boolean NOT NULL DEFAULT false,
  cached_discovery jsonb,
  discovery_cached_at timestamp with time zone,
  authorization_url text CHECK (authorization_url IS NULL OR authorization_url ~~ 'https://%'::text),
  token_url text CHECK (token_url IS NULL OR token_url ~~ 'https://%'::text),
  userinfo_url text CHECK (userinfo_url IS NULL OR userinfo_url ~~ 'https://%'::text),
  jwks_uri text CHECK (jwks_uri IS NULL OR jwks_uri ~~ 'https://%'::text),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT custom_oauth_providers_pkey PRIMARY KEY (id)
);
CREATE TABLE auth.webauthn_credentials (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  credential_id bytea NOT NULL,
  public_key bytea NOT NULL,
  attestation_type text NOT NULL DEFAULT ''::text,
  aaguid uuid,
  sign_count bigint NOT NULL DEFAULT 0,
  transports jsonb NOT NULL DEFAULT '[]'::jsonb,
  backup_eligible boolean NOT NULL DEFAULT false,
  backed_up boolean NOT NULL DEFAULT false,
  friendly_name text NOT NULL DEFAULT ''::text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  last_used_at timestamp with time zone,
  CONSTRAINT webauthn_credentials_pkey PRIMARY KEY (id),
  CONSTRAINT webauthn_credentials_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id)
);
CREATE TABLE auth.webauthn_challenges (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid,
  challenge_type text NOT NULL CHECK (challenge_type = ANY (ARRAY['signup'::text, 'registration'::text, 'authentication'::text])),
  session_data jsonb NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  expires_at timestamp with time zone NOT NULL,
  CONSTRAINT webauthn_challenges_pkey PRIMARY KEY (id),
  CONSTRAINT webauthn_challenges_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id)
);

-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.college (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  college_name text NOT NULL UNIQUE,
  college_abbreviation text,
  city text,
  name text NOT NULL UNIQUE,
  short_name text,
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT college_pkey PRIMARY KEY (id)
);
CREATE TABLE public.students (
  student_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  student_name text NOT NULL,
  college_id bigint,
  student_email text,
  student_moblie_number bigint,
  pursuing_year integer,
  branch_id bigint,
  registration_number character varying,
  user_id uuid DEFAULT auth.uid(),
  user_role text CHECK (user_role = ANY (ARRAY['student'::text, 'teacher'::text])),
  year_of_joining integer CHECK (year_of_joining >= 1900 AND year_of_joining <= 2100),
  profile_completed boolean DEFAULT false,
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT students_pkey PRIMARY KEY (student_id),
  CONSTRAINT students_college_id_fkey FOREIGN KEY (college_id) REFERENCES public.college(id),
  CONSTRAINT students_branch_id_fkey FOREIGN KEY (branch_id) REFERENCES public.branch(branch_id),
  CONSTRAINT students_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id)
);
CREATE TABLE public.branch (
  branch_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL UNIQUE,
  branch_name text NOT NULL UNIQUE,
  branch_abbreviation text UNIQUE,
  id uuid DEFAULT uuid_generate_v4(),
  name text NOT NULL UNIQUE,
  short_name text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT branch_pkey PRIMARY KEY (branch_id)
);
CREATE TABLE public.cae1 (
  cae1_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  student_id bigint,
  college_id bigint,
  cae1_path text,
  verification_status boolean,
  subject_id uuid,
  CONSTRAINT cae1_pkey PRIMARY KEY (cae1_id),
  CONSTRAINT cae1_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.students(student_id),
  CONSTRAINT cae1_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(subject_id),
  CONSTRAINT cae1_college_id_fkey FOREIGN KEY (college_id) REFERENCES public.college(id)
);
CREATE TABLE public.subject (
  subject_id uuid NOT NULL DEFAULT gen_random_uuid(),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  subject_name text,
  subject_abbreviation text,
  subject_code text UNIQUE,
  college_id bigint,
  CONSTRAINT subject_pkey PRIMARY KEY (subject_id),
  CONSTRAINT subject_college_id_fkey FOREIGN KEY (college_id) REFERENCES public.college(id)
);
CREATE TABLE public.exam (
  id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  exam text,
  Date date,
  subject_id uuid,
  CONSTRAINT exam_pkey PRIMARY KEY (id),
  CONSTRAINT exam_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(subject_id)
);
CREATE TABLE public.cae2 (
  cae2_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  student_id bigint,
  college_id bigint,
  cae2_path text,
  verification_status boolean,
  subject_id uuid,
  CONSTRAINT cae2_pkey PRIMARY KEY (cae2_id),
  CONSTRAINT cae1_duplicate_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.students(student_id),
  CONSTRAINT cae1_duplicate_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(subject_id),
  CONSTRAINT cae2_college_id_fkey FOREIGN KEY (college_id) REFERENCES public.college(id)
);
CREATE TABLE public.cae3 (
  cae3_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  student_id bigint,
  college_id bigint,
  cae3_path text,
  verification_status boolean,
  subject_id uuid,
  CONSTRAINT cae3_pkey PRIMARY KEY (cae3_id),
  CONSTRAINT cae3_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.students(student_id),
  CONSTRAINT cae3_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(subject_id),
  CONSTRAINT cae3_college_id_fkey FOREIGN KEY (college_id) REFERENCES public.college(id)
);
CREATE TABLE public.ese (
  ese_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  student_id bigint,
  college_id bigint,
  ese_path text,
  verification_status boolean,
  subject_id uuid,
  CONSTRAINT ese_pkey PRIMARY KEY (ese_id),
  CONSTRAINT ese_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.students(student_id),
  CONSTRAINT ese_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(subject_id),
  CONSTRAINT ese_college_id_fkey FOREIGN KEY (college_id) REFERENCES public.college(id)
);
CREATE TABLE public.file_access_history (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  user_email text NOT NULL,
  file_name text NOT NULL,
  file_type text,
  file_path text,
  file_url text,
  accessed_at timestamp with time zone DEFAULT now(),
  CONSTRAINT file_access_history_pkey PRIMARY KEY (id)
);
CREATE TABLE public.file_records (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  user_id text NOT NULL,
  user_email text NOT NULL,
  file_name text NOT NULL,
  file_url text NOT NULL,
  file_type text NOT NULL,
  file_size bigint NOT NULL,
  cloudinary_public_id text NOT NULL UNIQUE,
  subject_name text NOT NULL,
  document_type text NOT NULL,
  year text,
  college_id bigint,
  branch_id bigint,
  uploaded_at timestamp with time zone DEFAULT now(),
  last_accessed_at timestamp with time zone,
  access_count integer DEFAULT 0,
  CONSTRAINT file_records_pkey PRIMARY KEY (id),
  CONSTRAINT file_records_college_id_fkey FOREIGN KEY (college_id) REFERENCES public.college(id),
  CONSTRAINT file_records_branch_id_fkey FOREIGN KEY (branch_id) REFERENCES public.branch(branch_id)
);