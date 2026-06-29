import { NextResponse } from "next/server";
import { products } from "@/lib/products";

// Checkout endpoint.
// - If STRIPE_SECRET_KEY is set, it creates a real Stripe Checkout Session
//   using Stripe's REST API (no SDK dependency) and returns the hosted URL.
// - Otherwise it returns { demo: true } so the storefront can be demoed and
//   deployed before billing is connected.
//
// Set these in your environment to go live:
//   STRIPE_SECRET_KEY=sk_live_...    (or sk_test_...)
//   NEXT_PUBLIC_SITE_URL=https://yourdomain.com

export async function POST(req: Request) {
  const { email, items } = await req.json();

  const lineItems = (items as { slug: string; qty: number }[])
    .map(({ slug, qty }) => {
      const p = products.find((x) => x.slug === slug);
      if (!p) return null;
      return { product: p, qty: Math.max(1, qty | 0) };
    })
    .filter(Boolean) as { product: (typeof products)[number]; qty: number }[];

  if (lineItems.length === 0) {
    return NextResponse.json({ error: "Empty cart" }, { status: 400 });
  }

  const key = process.env.STRIPE_SECRET_KEY;
  const site =
    process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000";

  if (!key) {
    // Demo mode — no billing connected yet.
    return NextResponse.json({ demo: true });
  }

  // Build a Stripe Checkout Session via form-encoded REST call.
  const form = new URLSearchParams();
  form.set("mode", "payment");
  form.set("success_url", `${site}/thank-you?session_id={CHECKOUT_SESSION_ID}`);
  form.set("cancel_url", `${site}/checkout`);
  if (email) form.set("customer_email", email);

  lineItems.forEach(({ product, qty }, i) => {
    form.set(`line_items[${i}][quantity]`, String(qty));
    form.set(
      `line_items[${i}][price_data][currency]`,
      "usd"
    );
    form.set(
      `line_items[${i}][price_data][unit_amount]`,
      String(Math.round(product.price * 100))
    );
    form.set(
      `line_items[${i}][price_data][product_data][name]`,
      product.name
    );
  });

  const resp = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: form.toString(),
  });

  if (!resp.ok) {
    const detail = await resp.text();
    return NextResponse.json(
      { error: "Stripe error", detail },
      { status: 502 }
    );
  }

  const session = await resp.json();
  return NextResponse.json({ url: session.url });
}
