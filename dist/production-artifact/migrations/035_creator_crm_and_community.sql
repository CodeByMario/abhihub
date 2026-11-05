-- =====================================================================
-- AbhiHub Migration 035: Creator CRM, Top Customers & Community Broadcasts
-- Replaces Store Room with a Creator Customer & Community Hub
-- =====================================================================

SET search_path TO abhihub, public, extensions;

-- 1. Creator Customer Relations Table
CREATE TABLE IF NOT EXISTS abhihub.creator_customer_relations (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id           uuid NOT NULL REFERENCES abhihub.profiles(id) ON DELETE CASCADE,
    customer_id          uuid NOT NULL REFERENCES abhihub.profiles(id) ON DELETE CASCADE,
    total_spent          numeric(10,2) NOT NULL DEFAULT 0.00,
    total_notes_unlocked int NOT NULL DEFAULT 1,
    vip_tier             text NOT NULL DEFAULT 'regular' CHECK (vip_tier IN ('new', 'regular', 'vip', 'superfan')),
    customer_name        text,
    customer_email       text,
    notes                text,
    last_interacted_at   timestamptz NOT NULL DEFAULT now(),
    created_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_creator_customer UNIQUE (creator_id, customer_id)
);

CREATE INDEX IF NOT EXISTS idx_ccr_creator_id ON abhihub.creator_customer_relations(creator_id);
CREATE INDEX IF NOT EXISTS idx_ccr_customer_id ON abhihub.creator_customer_relations(customer_id);
CREATE INDEX IF NOT EXISTS idx_ccr_total_spent ON abhihub.creator_customer_relations(creator_id, total_spent DESC);

-- 2. Creator Community Broadcasts Table
CREATE TABLE IF NOT EXISTS abhihub.creator_broadcasts (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id   uuid NOT NULL REFERENCES abhihub.profiles(id) ON DELETE CASCADE,
    title        text NOT NULL,
    message      text NOT NULL,
    channel_url  text,
    target_tier  text NOT NULL DEFAULT 'all' CHECK (target_tier IN ('all', 'vip', 'superfan')),
    view_count   int NOT NULL DEFAULT 0,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cb_creator_id ON abhihub.creator_broadcasts(creator_id, created_at DESC);

-- 3. Top Customers Query Function
CREATE OR REPLACE FUNCTION abhihub.get_creator_top_customers(
    p_creator_id uuid,
    p_limit      int DEFAULT 20
)
RETURNS TABLE (
    customer_id          uuid,
    customer_name        text,
    customer_email       text,
    total_spent          numeric(10,2),
    total_notes_unlocked int,
    vip_tier             text,
    last_interacted_at   timestamptz
)
LANGUAGE sql
STABLE
SET search_path = abhihub, public, extensions
AS $$
    SELECT 
        c.customer_id,
        coalesce(p.full_name, c.customer_name, 'Supporter') AS customer_name,
        coalesce(p.email, c.customer_email, '') AS customer_email,
        c.total_spent,
        c.total_notes_unlocked,
        c.vip_tier,
        c.last_interacted_at
    FROM abhihub.creator_customer_relations c
    LEFT JOIN abhihub.profiles p ON p.id = c.customer_id
    WHERE c.creator_id = p_creator_id
    ORDER BY c.total_spent DESC, c.total_notes_unlocked DESC, c.last_interacted_at DESC
    LIMIT p_limit;
$$;

-- 4. RLS Policies
ALTER TABLE abhihub.creator_customer_relations ENABLE ROW LEVEL SECURITY;
ALTER TABLE abhihub.creator_broadcasts ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'creator_manage_own_customers') THEN
        CREATE POLICY creator_manage_own_customers ON abhihub.creator_customer_relations
            FOR ALL USING (auth.uid() = creator_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'creator_manage_own_broadcasts') THEN
        CREATE POLICY creator_manage_own_broadcasts ON abhihub.creator_broadcasts
            FOR ALL USING (auth.uid() = creator_id);
    END IF;
END $$;

GRANT ALL PRIVILEGES ON TABLE abhihub.creator_customer_relations TO anon, authenticated, service_role;
GRANT ALL PRIVILEGES ON TABLE abhihub.creator_broadcasts TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION abhihub.get_creator_top_customers(uuid, int) TO anon, authenticated, service_role;
