"use client";

import Link from "next/link";
import { useState } from "react";
import { Logo } from "./Logo";
import { useCart } from "@/lib/cart";
import { CartDrawer } from "./CartDrawer";

const nav = [
  { href: "/shop", label: "Shop" },
  { href: "/shop/lumora-life-system", label: "Life System" },
  { href: "/blog", label: "Journal" },
  { href: "/about", label: "About" },
];

export function Header() {
  const { count, setOpen } = useCart();
  const [mobile, setMobile] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-ink/10 bg-cream/80 backdrop-blur">
      <div className="container-x flex h-16 items-center justify-between">
        <Link href="/" aria-label="Lumora home">
          <Logo />
        </Link>

        <nav className="hidden items-center gap-8 md:flex">
          {nav.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className="text-sm font-medium text-ink/80 transition hover:text-terracotta"
            >
              {n.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setOpen(true)}
            className="relative rounded-full border border-ink/20 px-4 py-2 text-sm font-medium transition hover:border-ink"
            aria-label="Open cart"
          >
            Cart
            {count > 0 && (
              <span className="ml-2 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-terracotta px-1 text-xs font-semibold text-cream">
                {count}
              </span>
            )}
          </button>
          <button
            className="md:hidden"
            onClick={() => setMobile((v) => !v)}
            aria-label="Toggle menu"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path
                d="M4 7h16M4 12h16M4 17h16"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>
      </div>

      {mobile && (
        <nav className="border-t border-ink/10 bg-cream md:hidden">
          <div className="container-x flex flex-col py-2">
            {nav.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                onClick={() => setMobile(false)}
                className="py-3 text-sm font-medium text-ink/80"
              >
                {n.label}
              </Link>
            ))}
          </div>
        </nav>
      )}

      <CartDrawer />
    </header>
  );
}
