# Go-Live Checklist

Everything between "built" and "taking real orders." Roughly a weekend of work.

## 1. Business setup (½ day)
- [ ] Confirm brand name/domain/trademark availability (or pick an alternative).
- [ ] Register entity + business bank account.
- [ ] Buy the domain.

## 2. Payments + fulfilment (½ day)
- [ ] Create Stripe account; complete identity verification; enable Stripe Tax.
- [ ] Add `STRIPE_SECRET_KEY` + `NEXT_PUBLIC_SITE_URL` to host env.
- [ ] Choose delivery: email provider (Resend/ConvertKit) **or** Gumroad/Lemon
      Squeezy as the fulfilment layer. Wire it into checkout success.
- [ ] Test a real $1 purchase end-to-end (use a test SKU), confirm delivery email.

## 3. Deploy the store (1–2 hrs)
- [ ] Push `store/` to GitHub → import to Vercel → set env vars → deploy.
- [ ] Point domain at Vercel; confirm HTTPS.
- [ ] Submit `sitemap.xml` to Google Search Console.

## 4. Product (1–2 days)
- [ ] Ship the Daily Planner pack (PDF is ready) as SKU #1.
- [ ] Build Habits + Goals packs (same format) → release the Core Bundle.
- [ ] Build the Notion editions from the blueprint; test duplicate links incognito.

## 5. Legal/trust (2–3 hrs)
- [ ] Add Terms, Privacy, Refund policy pages.
- [ ] Replace placeholder testimonials once you have real reviews.
- [ ] Add support email + auto-reply.

## 6. Analytics + pixels (1 hr)
- [ ] GA4; Meta Pixel; Pinterest Tag; TikTok Pixel.
- [ ] Verify purchase event fires on the thank-you page.

## 7. Audience + launch (ongoing)
- [ ] Connect the lead-magnet form to your ESP; load the welcome sequence.
- [ ] Open Pinterest/TikTok/IG; post the prepared hooks daily.
- [ ] Publish the 3 SEO articles (already written) on the live blog.
- [ ] Recruit 5–10 UGC creators with the brief.
- [ ] Soft launch to friends/family for first real reviews.
- [ ] Turn on paid only after 2–3 organic creatives prove out; hold CAC ≤ $15.

## 8. Operating rhythm (weekly)
- [ ] Review KPIs (sessions, CVR, AOV, CAC, ROAS, refund rate).
- [ ] Ship 1–2 Journal posts + 1–2 emails.
- [ ] Test 5+ new ad creatives; scale winners, cut losers.
- [ ] Re-run `financial_model.py` with real numbers to track vs. plan.
