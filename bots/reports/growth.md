# 🚀 growth — Marketing / Growth
_Updated 2026-08-18 (CEO session)_

## Metrics
- **canonical_domain**: abhihub.edu.eu.org (consolidated; www + bare both 200)
- **referral_credits_per_invite**: 50 (inviter) / 25 (invitee)
- **users**: 85 | active 20 | dormant 65 | new 14 | **referred 2** (loop converting)
- **acceptance test**: PASS ✓ (register_referral verified live, reverts cleanly)

## Campaign history
- **2026-08-18: DORMANT DRIP SENT ✅** — 65 dormant users got the exam-pack + referral
  email from info@abhihub.edu.eu.org (Gmail SMTP via abhihub.02@gmail.com).
  Each email carried the user's personal referral code (50-credit invite).
  Command: `python scripts/exam_pack_drip.py --segment dormant --send`
  Pre-validated with `--test` (single send OK).

## Shipped & verified live (v45)
- [done] Canonical/SEO consolidation → abhihub.edu.eu.org
- [done] www 525 fixed (Cloudflare SSL → Full)
- [done] /u/<id> share card: dedupe OG + "Join Free?ref=CODE" + WA/IG/Copy share row
- [done] Referral backfill (82/82) + 016 migration (referral_credits/referral_count)
- [done] register_referral fixed (PostgREST-safe increment + idempotent guard)
- [done] Exam-pack banner (dashboard) + post-upload invite prompt + referral widget — WA/IG/Copy
- [done] Live referral stats (count + credits) in widget
- [done] Email drip: campaign_export.py + exam_pack_drip.py (info@, --test/--send, .env loader)
- [done] tests/test_referral_flow.py — PASS ✓

## Next highest-ROI actions
1. Measure dormant drip conversion (signups/login from the 65). Add a send-log to track.
2. Post your /u/<id> link in IG bio + college WhatsApp groups.
3. Build branch topper leaderboard (gamified sharing).
4. WhatsApp channel for new-notes drop alerts.
