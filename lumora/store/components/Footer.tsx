import Link from "next/link";
import { Logo } from "./Logo";
import { EmailCapture } from "./EmailCapture";

export function Footer() {
  return (
    <footer className="mt-24 border-t border-ink/10 bg-sand/60">
      <div className="container-x grid gap-12 py-16 md:grid-cols-2 lg:grid-cols-4">
        <div className="lg:col-span-1">
          <Logo />
          <p className="mt-4 max-w-xs text-sm text-ink/70">
            Beautifully designed digital planners and life systems for people who
            want a calmer, more intentional life.
          </p>
        </div>

        <div>
          <h4 className="text-sm font-semibold text-ink">Shop</h4>
          <ul className="mt-4 space-y-2 text-sm text-ink/70">
            <li>
              <Link href="/shop" className="hover:text-terracotta">
                All products
              </Link>
            </li>
            <li>
              <Link
                href="/shop/lumora-life-system"
                className="hover:text-terracotta"
              >
                The Lumora Life System
              </Link>
            </li>
            <li>
              <Link href="/shop/core-bundle" className="hover:text-terracotta">
                The Core Bundle
              </Link>
            </li>
          </ul>
        </div>

        <div>
          <h4 className="text-sm font-semibold text-ink">Company</h4>
          <ul className="mt-4 space-y-2 text-sm text-ink/70">
            <li>
              <Link href="/about" className="hover:text-terracotta">
                About
              </Link>
            </li>
            <li>
              <Link href="/blog" className="hover:text-terracotta">
                Journal
              </Link>
            </li>
            <li>
              <Link href="/faq" className="hover:text-terracotta">
                FAQ
              </Link>
            </li>
          </ul>
        </div>

        <div>
          <h4 className="text-sm font-semibold text-ink">
            Get a free starter page
          </h4>
          <p className="mt-3 text-sm text-ink/70">
            Join the list for a free printable weekly planner and 10% off your
            first order.
          </p>
          <div className="mt-4">
            <EmailCapture compact />
          </div>
        </div>
      </div>

      <div className="border-t border-ink/10">
        <div className="container-x flex flex-col items-center justify-between gap-2 py-6 text-xs text-ink/60 sm:flex-row">
          <p>© {new Date().getFullYear()} Lumora. All rights reserved.</p>
          <p>
            Digital products. Instant delivery. Made with care for intentional
            humans.
          </p>
        </div>
      </div>
    </footer>
  );
}
