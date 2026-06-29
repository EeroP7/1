"use client";

import Link from "next/link";
import { useCart } from "@/lib/cart";
import { formatPrice } from "@/lib/products";

export function CartDrawer() {
  const { open, setOpen, detailed, subtotal, setQty, remove, count } =
    useCart();

  return (
    <div
      className={`fixed inset-0 z-50 ${open ? "" : "pointer-events-none"}`}
      aria-hidden={!open}
    >
      <div
        className={`absolute inset-0 bg-ink/40 transition-opacity ${
          open ? "opacity-100" : "opacity-0"
        }`}
        onClick={() => setOpen(false)}
      />
      <aside
        className={`absolute right-0 top-0 flex h-full w-full max-w-md flex-col bg-cream shadow-2xl transition-transform ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between border-b border-ink/10 px-6 py-5">
          <h2 className="font-serif text-xl">Your cart ({count})</h2>
          <button
            onClick={() => setOpen(false)}
            aria-label="Close cart"
            className="text-2xl leading-none text-ink/60 hover:text-ink"
          >
            ×
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {detailed.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <p className="text-ink/60">Your cart is empty.</p>
              <Link
                href="/shop"
                onClick={() => setOpen(false)}
                className="btn-accent mt-6"
              >
                Browse the shop
              </Link>
            </div>
          ) : (
            <ul className="space-y-5">
              {detailed.map(({ product, qty, lineTotal }) => (
                <li key={product.slug} className="flex gap-4">
                  <div
                    className={`flex h-16 w-16 shrink-0 items-center justify-center rounded-xl text-2xl text-cream ${product.accent}`}
                  >
                    {product.art}
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-semibold">{product.name}</p>
                    <p className="text-xs text-ink/60">
                      {formatPrice(product.price)} · digital download
                    </p>
                    <div className="mt-2 flex items-center gap-3">
                      <div className="flex items-center rounded-full border border-ink/20">
                        <button
                          className="px-2 text-ink/70"
                          onClick={() => setQty(product.slug, qty - 1)}
                          aria-label="Decrease quantity"
                        >
                          –
                        </button>
                        <span className="w-6 text-center text-sm">{qty}</span>
                        <button
                          className="px-2 text-ink/70"
                          onClick={() => setQty(product.slug, qty + 1)}
                          aria-label="Increase quantity"
                        >
                          +
                        </button>
                      </div>
                      <button
                        className="text-xs text-ink/50 underline hover:text-terracotta"
                        onClick={() => remove(product.slug)}
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                  <div className="text-sm font-semibold">
                    {formatPrice(lineTotal)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {detailed.length > 0 && (
          <div className="border-t border-ink/10 px-6 py-5">
            <div className="flex items-center justify-between text-sm">
              <span className="text-ink/70">Subtotal</span>
              <span className="font-semibold">{formatPrice(subtotal)}</span>
            </div>
            <p className="mt-1 text-xs text-ink/50">
              Taxes calculated at checkout. Instant digital delivery.
            </p>
            <Link
              href="/checkout"
              onClick={() => setOpen(false)}
              className="btn-primary mt-4 w-full"
            >
              Checkout · {formatPrice(subtotal)}
            </Link>
            <Link
              href="/shop"
              onClick={() => setOpen(false)}
              className="mt-3 block text-center text-xs text-ink/60 underline"
            >
              Continue shopping
            </Link>
          </div>
        )}
      </aside>
    </div>
  );
}
