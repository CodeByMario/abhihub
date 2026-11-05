-- ==============================================================================
-- PHASE 2: Documents Pricing & Metadata Columnization (Schema: abhihub)
-- Adds typed relational columns to `abhihub.documents` and safely backfills from `description`.
-- Safe & Backward-Compatible: Leaves original `description` intact.
-- ==============================================================================

SET search_path = abhihub, public;

BEGIN;

-- ------------------------------------------------------------------------------
-- 1. Add structured monetization columns to `abhihub.documents`
-- ------------------------------------------------------------------------------
ALTER TABLE abhihub.documents
    ADD COLUMN IF NOT EXISTS is_paid BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS price NUMERIC(10, 2) DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS seller_id UUID REFERENCES abhihub.profiles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS coupon_code TEXT,
    ADD COLUMN IF NOT EXISTS coupon_discount INT4 DEFAULT 0;

-- Create index for fast catalog filtering on paid/free documents
CREATE INDEX IF NOT EXISTS idx_documents_is_paid_price ON abhihub.documents (is_paid, price);
CREATE INDEX IF NOT EXISTS idx_documents_seller_id ON abhihub.documents (seller_id) WHERE seller_id IS NOT NULL;

-- ------------------------------------------------------------------------------
-- 2. Safe Backfill Procedure from JSON strings in `description`
-- ------------------------------------------------------------------------------
DO $$
DECLARE
    r RECORD;
    raw_desc TEXT;
    parsed_json JSONB;
    pricing_obj JSONB;
    p_is_paid BOOLEAN;
    p_price NUMERIC(10, 2);
    p_seller_id UUID;
    p_seller_str TEXT;
    p_coupon_code TEXT;
    p_coupon_discount INT4;
BEGIN
    FOR r IN SELECT id, description, uploader_id FROM abhihub.documents WHERE description IS NOT NULL AND description LIKE '{%' LOOP
        BEGIN
            raw_desc := TRIM(r.description);
            parsed_json := raw_desc::jsonb;
            pricing_obj := parsed_json->'pricing';

            IF pricing_obj IS NOT NULL AND jsonb_typeof(pricing_obj) = 'object' THEN
                p_is_paid := COALESCE((pricing_obj->>'is_paid')::boolean, false);
                p_price := COALESCE((pricing_obj->>'price')::numeric, 0.00);
                p_seller_str := pricing_obj->>'seller_id';
                p_coupon_code := pricing_obj->>'coupon_code';
                p_coupon_discount := COALESCE((pricing_obj->>'coupon_discount')::int, 0);

                -- Verify if seller_str is a valid UUID
                IF p_seller_str ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
                    p_seller_id := p_seller_str::uuid;
                ELSE
                    p_seller_id := r.uploader_id;
                END IF;

                -- Update the document row with structured values
                UPDATE abhihub.documents
                SET
                    is_paid = p_is_paid,
                    price = p_price,
                    seller_id = p_seller_id,
                    coupon_code = p_coupon_code,
                    coupon_discount = p_coupon_discount
                WHERE id = r.id;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            -- Skip malformed JSON rows without failing transaction
            NULL;
        END;
    END LOOP;
END $$;

COMMIT;
