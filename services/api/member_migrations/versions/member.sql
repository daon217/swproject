CREATE TABLE app.members (
 user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 login_id text NOT NULL CHECK(login_id ~ '^[A-Za-z0-9]{4,16}$'),
 password_hash text NOT NULL, gender text CHECK(gender IN ('male','female','prefer_not_to_say')),
 birth_date date, include_used boolean NOT NULL DEFAULT false,
 profile_version integer NOT NULL DEFAULT 1 CHECK(profile_version>0),
 consent_version text NOT NULL, consent_at timestamptz NOT NULL DEFAULT now(),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX members_login ON app.members(lower(login_id));
CREATE TABLE app.member_preferences (
 user_id uuid NOT NULL REFERENCES app.members ON DELETE CASCADE,
 kind text NOT NULL CHECK(kind IN ('allergy','avoid','prefer')),
 value text NOT NULL CHECK(length(value) BETWEEN 1 AND 100), PRIMARY KEY(user_id,kind,value)
);
CREATE TABLE app.sessions (
 token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES app.members ON DELETE CASCADE,
 created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL
);
CREATE INDEX sessions_by_user ON app.sessions(user_id);
CREATE INDEX sessions_expiry ON app.sessions(expires_at);
CREATE TABLE app.auth_attempts (
 bucket text PRIMARY KEY, attempts integer NOT NULL, window_start timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE app.subscription_plans (
 plan_id text PRIMARY KEY, name text NOT NULL, price numeric(20,4) CHECK(price>=0),
 currency varchar(3) NOT NULL, interval text NOT NULL CHECK(interval IN ('month','year')),
 benefits jsonb NOT NULL, enabled boolean NOT NULL DEFAULT true
);
INSERT INTO app.subscription_plans VALUES ('premium-monthly','꿀픽 프리미엄',NULL,'KRW','month',
 '["AI 추천 상품 3개 전체 보기","기피·선호 재료로 식품 필터","내 취향에 맞는 후보 비교"]',true);
CREATE TABLE app.subscriptions (
 subscription_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id uuid NOT NULL UNIQUE REFERENCES app.members,
 plan_id text NOT NULL REFERENCES app.subscription_plans,
 entitlement_end timestamptz,
 cancel_at_period_end boolean NOT NULL DEFAULT false,
 billing_mode text NOT NULL CHECK(billing_mode IN ('mock','live')),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE app.invoices (
 invoice_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 subscription_id uuid NOT NULL REFERENCES app.subscriptions,
 user_id uuid NOT NULL REFERENCES app.members,
 idempotency_key text NOT NULL CHECK(length(idempotency_key) BETWEEN 8 AND 128),
 request_hash text NOT NULL, amount numeric(20,4) NOT NULL CHECK(amount>=0), currency varchar(3) NOT NULL,
 period_start timestamptz NOT NULL, period_end timestamptz NOT NULL CHECK(period_end>period_start),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(user_id,idempotency_key)
);
CREATE TABLE app.payments (
 payment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), invoice_id uuid NOT NULL UNIQUE REFERENCES app.invoices,
 method text NOT NULL CHECK(method IN ('card','bank_transfer','naverpay','kakaopay','tosspay')),
 provider text NOT NULL CHECK(provider IN ('mock')),
 status text NOT NULL CHECK(status IN ('pending','succeeded','failed','refunded')),
 error_code text, created_at timestamptz NOT NULL DEFAULT now(), paid_at timestamptz, refunded_at timestamptz
);
CREATE INDEX invoices_by_member ON app.invoices(user_id,created_at DESC,invoice_id);
CREATE INDEX payments_pending ON app.payments(created_at) WHERE status='pending';
REVOKE INSERT,UPDATE,DELETE ON app.subscription_plans FROM kkulpick_member_app;
