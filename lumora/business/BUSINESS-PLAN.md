# Lumora — Business Plan

**One line:** A premium digital-products brand selling beautifully designed
planners and life systems (Notion + printable + iPad) to people who want a
calmer, more intentional life.

**Target:** $100,000/month revenue run-rate. The financial model
(`financial_model.py`) reaches it in **Month 9** and exits Year 1 at a
**~$1.46M/yr run-rate** on **~$591k** cumulative net profit — driven by ~92%
contribution margins and disciplined reinvestment of profit into paid
acquisition.

> Honesty note: these are a *model and a plan*, not booked revenue. Hitting them
> requires real-world execution (Stripe/LLC setup, ad spend, content, time).
> See `EXECUTION-LOG.md` for exactly what is built vs. what needs a human.

---

## 1. Why this business

From first-principles market research (June 2026):

- **Digital products carry 85–95% gross margins** — no inventory, no shipping,
  no supplier, instant global fulfilment. This is what makes a lean path to
  $100k/month realistic.
- **Wellness / self-improvement is the #1 niche** by margin and lifetime value.
- **Personalised, intentional-living products** reduce price sensitivity and
  convert better, especially as gifts and New-Year purchases.
- **Multi-format (Notion + print + iPad)** widens the market without adding COGS
  — one product, three audiences, one price.

Lumora sits at the intersection of all four.

## 2. The product

A connected family of digital planners. Each pack stands alone and links to the
others; the flagship bundles everything.

| Product | Price | Role |
|---|---|---|
| Habit Builder / Meal Planner | $19 | Entry / impulse |
| Daily / Goals / Wellness | $24 | Core single packs |
| Finance & Budget | $29 | Higher-value pack |
| The Core Bundle (3 packs) | $59 | Mid-tier, "best starter" |
| **The Lumora Life System** | **$97** | Flagship, hero offer (was $189) |

Price ladder + an order bump (a $10 add-on at checkout) + one post-purchase
upsell engineer a **blended AOV of ~$42**.

**Status:** the printable Daily Planner is a *finished, sellable PDF* today
(`../product/printable/`). The Notion edition has a complete build blueprint
(`../product/notion/`). The remaining packs are repetitions of a proven format.

## 3. Customer (ICP)

- **Primary:** women 25–45, organised-aspirational, into wellness, productivity
  and "that girl"/intentional-living content. Shops on Pinterest, TikTok, IG.
- **Secondary:** students & early-career professionals (iPad/GoodNotes users);
  gift-buyers (Q4 + Mother's Day spikes).
- **Jobs to be done:** "help me feel in control of my life," "make me look
  forward to planning," "one place instead of five apps."

## 4. Positioning & moat

- **Positioning:** the *calm* planner. Not hustle-culture, not maximalist —
  a 3-priority method and a warm, premium aesthetic.
- **Why we win:** (1) design quality that photographs well for social,
  (2) three formats for one price, (3) buy-once / lifetime-updates vs. app
  subscriptions, (4) a content + email engine that compounds.
- **Defensibility (built over time):** brand + audience (email list, social
  following), SEO content, and a catalog too broad/polished to cheaply copy.
  Digital products are easy to start and easy to clone — the moat is brand and
  distribution, so we invest there deliberately.

## 5. Unit economics

From `financial_model.py`:

- AOV **$42** · contribution/order **$38.64** (92%)
- Customer LTV (contribution) **~$45** · target CAC **$15** → **LTV:CAC 3.0:1**
- To do $100k/mo: **2,381 orders/mo (~79/day)** ≈ **~91,600 sessions/mo** at a
  2.6% blended conversion rate.

Because margins are ~92%, the constraint is **traffic and CAC**, not COGS. The
whole operating plan is therefore a *distribution* plan.

## 6. Go-to-market (summary; full detail in MARKETING-PLAN.md)

A "rented + owned" engine:

1. **Organic social (Pinterest + TikTok + IG Reels)** — the discovery engine.
   Planner/aesthetic content performs disproportionately well here and is ~free.
2. **Email (owned)** — free lead magnet (a printable weekly page) → welcome flow
   → launches. Owned audience that converts at the highest rate.
3. **Paid (Meta + Pinterest + TikTok)** — scale what organic proves, kept at
   CAC ≤ $15 via creative testing.
4. **SEO content** — the Journal targets high-intent terms ("best digital
   planner", "how to stick to a planner"). Compounds for free over months.
5. **Affiliate / UGC creators** — pay creators a % per sale; their content
   doubles as social proof.

Channel mix at scale ≈ 45% paid, 30% organic/social, 15% email, 10%
affiliate/referral.

## 7. Operations

- **Storefront:** the Next.js site in `../store` (deploy to Vercel).
- **Payments:** Stripe Checkout (already wired in `app/api/checkout/route.ts`).
- **Fulfilment:** automated email with download + Notion duplicate links
  (Resend/ConvertKit), or a delivery platform (Lemon Squeezy/Gumroad/Payhip).
- **Support:** one shared inbox; <24h replies; refunds honoured no-questions.
- **Team:** founder-led for months 1–4; add a part-time designer (more packs)
  and a part-time media buyer around month 5 as ad spend scales (in OPEX).

## 8. Financial plan

See the table printed by `financial_model.py` / `financial-model.csv`.

- **Capital to start:** ~$1–3k (tools + initial ad tests). The business is
  self-funding from ~Month 1 because margins are high and the product is built.
- **Milestones:** $10k/mo (M2) · $30k/mo (M4) · $60k/mo (M6) · **$100k/mo (M9)**.
- **Risk-adjusted view:** if CAC runs hot ($20) or conversion is 2.0%, push the
  $100k month out ~2–3 months and lean harder on organic/email. The model is in
  code so you can re-run any scenario by editing the assumptions block.

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Easy to clone | Compete on brand, design, email list, SEO — not on the files. |
| Rising ad CAC | Over-index on organic + email; affiliate/UGC; raise AOV via bundles. |
| Platform dependence (Meta/TikTok) | Diversify channels; prioritise owned email. |
| Seasonality (Q4/Jan spikes) | Evergreen content + non-dated planners; gift bundles. |
| Refund abuse | Digital, so cap exposure with clear terms; refund rate modeled at ~3%. |
| Trademark/brand name | Verify "Lumora" trademark + domain before committing (see log). |

## 10. Legal & compliance checklist (human required)

- [ ] Register entity (LLC/sole trader) + business bank account.
- [ ] Stripe account + tax settings (Stripe Tax for VAT/sales tax on digital goods).
- [ ] Verify "Lumora" name/trademark/domain availability in target markets.
- [ ] Terms of Service, Privacy Policy, refund policy on-site.
- [ ] Email compliance (CAN-SPAM/GDPR) — consented list + unsubscribe.
- [ ] Replace placeholder testimonials with real, verified reviews before launch.

## 11. 90-day execution plan

**Days 1–14 — Foundation.** Deploy the store; connect Stripe + email delivery;
finish the Core Bundle packs (Daily ✅, Habits, Goals); set up analytics
(GA4 + Meta/Pinterest pixels); register entity + legal pages; open social
accounts.

**Days 15–45 — Audience.** Publish 1 lead-magnet + ship the welcome email flow;
post daily on Pinterest/TikTok/IG (repurpose product visuals + Journal posts);
publish the 3 SEO articles; recruit 5–10 UGC creators; soft-launch to friends
for the first real reviews.

**Days 46–90 — Scale.** Turn on paid once 2–3 organic creatives prove out;
hold CAC ≤ $15; launch the flagship Life System with a discount window; add
order bump + post-purchase upsell; expand catalog (Wellness, Finance, Meals);
start affiliate program. Target exiting day 90 around the **$20–30k/mo** band
and climbing toward $100k by Month 9 per the model.
