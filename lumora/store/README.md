# Lumora Store

The Lumora storefront — a production-ready Next.js 14 (App Router) e-commerce
site for selling digital planners. Tailwind CSS, fully responsive, SEO-ready
(metadata, JSON-LD, sitemap, robots), cart with localStorage persistence, and a
checkout that works in demo mode today and with **real Stripe payments** the
moment you add a key.

## Run locally

```bash
cd lumora/store
npm install
npm run dev          # http://localhost:3000
```

## Build for production

```bash
npm run build
npm run start
```

## Go live (3 steps)

1. **Deploy** — push this folder to Vercel (recommended) or Netlify. Zero config.
2. **Connect Stripe** — create a Stripe account, then set in your host's env:
   ```
   STRIPE_SECRET_KEY=sk_live_...
   NEXT_PUBLIC_SITE_URL=https://yourdomain.com
   ```
   Checkout will automatically switch from demo mode to real, hosted Stripe
   Checkout (see `app/api/checkout/route.ts`). No SDK required.
3. **Deliver the files** — connect an email provider (Klaviyo/ConvertKit/Resend)
   in the checkout success path to email download + Notion duplicate links.
   Or use a digital-delivery platform (Lemon Squeezy / Gumroad / Payhip) as the
   fulfilment layer and point the buttons there.

## What's included

- `app/` — routes: home, shop, product, cart drawer, checkout, thank-you,
  about, faq, blog (3 SEO articles), sitemap & robots.
- `lib/products.ts` — the product catalog (single source of truth).
- `lib/cart.tsx` — cart context + localStorage.
- `lib/posts.ts` — journal/SEO content.
- `components/` — Header, Footer, ProductCard, CartDrawer, etc.

## Editing the catalog

Everything about products (names, prices, copy, formats, badges) lives in
`lib/products.ts`. Change it there and the whole site updates.

## Notes

- The on-site testimonials in `app/page.tsx` are **placeholders** — replace them
  with real, verified customer reviews before launch.
- Brand name/domain (`lumora.co`) is illustrative; verify trademark + domain
  availability before committing to it.
