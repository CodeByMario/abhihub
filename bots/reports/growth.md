# 🚀 growth — Marketing / Growth
_Updated 2026-08-18 (CEO session)_

## Metrics
- **canonical_domain**: abhihub.edu.eu.org (consolidated; www + bare both 200, canonical → brand)
- **referral_credits_per_invite**: 50 (inviter) / 25 (invitee)
- **users**: 85 (all have referral_code after backfill)
- **referred_by**: 0 — loop not yet converting (needs real shares)

## Shipped & verified live
- [done] Canonical/SEO consolidation → abhihub.edu.eu.org (single canonical + og:url everywhere)
- [done] www.abhihub.edu.eu.org 525 fixed (Cloudflare SSL → Full)
- [done] /u/<id> share card: dedupe OG, conversion CTA "Join Free?ref=CODE" (verified single canonical)
- [done] Referral-code backfill: 82/82 null → populated
- [done] Exam-pack + referral banner (dashboard) with WhatsApp + Instagram share CTAs
- [done] Post-upload invite prompt (highest-intent moment, once/session)
- [done] Live referral stats in widget (count + credits)
- [done] Email drip scripts (campaign_export.py + exam_pack_drip.py) → send as info@abhihub.edu.eu.org
- [done] tests/test_referral_flow.py — end-to-end acceptance test (reverts mutations)

## BLOCKER (action required)
**Migration 016 not yet applied in Supabase.** Live DB is missing
`profiles.referral_credits` and `profiles.referral_count`, so register_referral()
and /api/referral/my-code error at runtime. The acceptance test reports BLOCKED.

### Fix — run in Supabase SQL editor (abhihub schema):
```sql
ALTER TABLE abhihub.profiles
  ADD COLUMN IF NOT EXISTS referral_credits INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS referral_count  INTEGER NOT NULL DEFAULT 0;
```
File: `migrations/016_referral_credit_columns.sql`. Then:
`python tests/test_referral_flow.py` → expect PASS ✓.

## Insights (from earlier)
- Exam-season 'last 7 days' revision packs email
- Instagram Reels: '1 note that got a 9-pointer'
- Referral: 50 credits per invited active peer
- Branch-wise topper leaderboard (gamified)
- WhatsApp channel for new-notes drop alerts

## Recommendations
- Apply 016, run acceptance test, then push the dormant-user email drip.
- Post your /u/<id> link in IG bio + college WhatsApp groups to start moving referred_by.
- Add share CTAs to /u/<id> card + post-upload prompt (both already done on dashboard/banner).
