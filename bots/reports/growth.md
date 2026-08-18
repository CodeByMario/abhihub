# 🚀 growth — Marketing / Growth
_Updated 2026-08-18 (CEO session)_

## Metrics
- **canonical_domain**: abhihub.edu.eu.org (consolidated; www + bare both 200)
- **referral_credits_per_invite**: 50 (inviter) / 25 (invitee)
- **users**: 85 | active 20 | dormant 65 | new 14 | **referred 2** (loop now converting!)
- **acceptance test**: PASS ✓ (register_referral verified live, reverts cleanly)

## Shipped & verified live (v45)
- [done] Canonical/SEO consolidation → abhihub.edu.eu.org
- [done] www 525 fixed (Cloudflare SSL → Full)
- [done] /u/<id> share card: dedupe OG + "Join Free?ref=CODE" + WA/IG/Copy share row
- [done] Referral backfill (82/82) + 016 migration (referral_credits/referral_count)
- [done] register_referral fixed (PostgREST-safe increment + idempotent guard)
- [done] Exam-pack banner (dashboard) + post-upload invite prompt + referral widget — all with WA/IG/Copy
- [done] Live referral stats (count + credits) in widget
- [done] Email drip: campaign_export.py + exam_pack_drip.py (info@abhihub.edu.eu.org)
- [done] tests/test_referral_flow.py — PASS ✓

## HIGHEST-ROI NEXT ACTION: dormant-user email drip
Ready to send. Only blocker: GMAIL_APP_PASSWORD in .env (Gmail SMTP via abhihub.02@gmail.com,
From: info@abhihub.edu.eu.org). Not a secret I can request in chat.

Run after adding the key:
  python scripts/campaign_export.py --all
  python scripts/exam_pack_drip.py --segment dormant --send   # 65 dormant users
  # or start small: --csv exports/users_new.csv --send (14 newest)

Each email: exam pack link + personal referral code (50-credit invite).

## Insights (from earlier)
- Exam-season revision packs email
- IG Reels: '1 note that got a 9-pointer'
- Branch topper leaderboard (gamified)
- WhatsApp channel for new-notes drops

## Recommendations
1. Send dormant drip (highest ROI, zero ad spend) — pushes users into working loop.
2. Post your /u/<id> link in IG bio + college WhatsApp groups.
3. Build branch topper leaderboard to gamify sharing.
