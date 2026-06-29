"use client";

import { useState } from "react";
import Link from "next/link";
import { useCart } from "@/lib/cart";
import { formatPrice } from "@/lib/products";

export default function CheckoutPage() {
  const { detailed, subtotal, clear, count } = useCart();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function pay(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!email.includes("@")) {
      setError("Please enter a valid email for your downloads.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          items: detailed.map((d) => ({ slug: d.product.slug, qty: d.qty })),
        }),
      });
      const data = await res.json();
      if (data.url) {
        // Real Stripe Checkout session — redirect to hosted payment page.
        window.location.href = data.url;
        return;
      }
      // Demo mode (no Stripe key configured yet): simulate successful purchase.
      setDone(true);
      clear();
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <div className="container-x flex min-h-[60vh] flex-col items-center justify-center py-20 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-sage text-3xl text-cream">
          ✓
        </div>
        <h1 className="mt-6 font-serif text-3xl font-semibold">
          Thank you — your order is on its way.
        </h1>
        <p className="mt-3 max-w-md text-ink/70">
          We&apos;ve sent your download links and Notion duplicate link to{" "}
          <span className="font-semibold">{email}</span>. (Demo mode: connect
          Stripe to take live payments — see the README.)
        </p>
        <Link href="/shop" className="btn-accent mt-8">
          Back to shop
        </Link>
      </div>
    );
  }

  if (count === 0) {
    return (
      <div className="container-x flex min-h-[50vh] flex-col items-center justify-center py-20 text-center">
        <h1 className="font-serif text-3xl font-semibold">
          Your cart is empty
        </h1>
        <Link href="/shop" className="btn-accent mt-6">
          Find your planner
        </Link>
      </div>
    );
  }

  return (
    <div className="container-x grid gap-12 py-14 lg:grid-cols-2">
      <div>
        <h1 className="font-serif text-3xl font-semibold">Checkout</h1>
        <p className="mt-2 text-sm text-ink/60">
          Digital products — delivered instantly by email. No shipping.
        </p>

        <form onSubmit={pay} className="mt-8 space-y-5">
          <div>
            <label className="text-sm font-medium">
              Email (for your downloads)
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@email.com"
              className="mt-2 w-full rounded-xl border border-ink/20 bg-white px-4 py-3 outline-none focus:border-terracotta"
            />
          </div>

          {error && <p className="text-sm text-terracotta">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="btn-primary w-full"
          >
            {loading ? "Processing…" : `Pay ${formatPrice(subtotal)}`}
          </button>

          <p className="text-center text-xs text-ink/50">
            Secure checkout. By purchasing you agree to our terms. 30-day
            happiness guarantee.
          </p>
        </form>
      </div>

      {/* Order summary */}
      <div className="card h-fit bg-white/70 p-6">
        <h2 className="font-serif text-xl font-semibold">Order summary</h2>
        <ul className="mt-5 space-y-4">
          {detailed.map(({ product, qty, lineTotal }) => (
            <li key={product.slug} className="flex items-center gap-3">
              <div
                className={`flex h-12 w-12 items-center justify-center rounded-lg text-xl text-cream ${product.accent}`}
              >
                {product.art}
              </div>
              <div className="flex-1">
                <p className="text-sm font-medium">{product.name}</p>
                <p className="text-xs text-ink/50">Qty {qty}</p>
              </div>
              <span className="text-sm font-semibold">
                {formatPrice(lineTotal)}
              </span>
            </li>
          ))}
        </ul>
        <div className="mt-6 space-y-2 border-t border-ink/10 pt-4 text-sm">
          <div className="flex justify-between">
            <span className="text-ink/60">Subtotal</span>
            <span>{formatPrice(subtotal)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-ink/60">Delivery</span>
            <span className="text-sage">Instant · free</span>
          </div>
          <div className="flex justify-between border-t border-ink/10 pt-2 text-base font-semibold">
            <span>Total</span>
            <span>{formatPrice(subtotal)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
