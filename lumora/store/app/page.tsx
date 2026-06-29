import Link from "next/link";
import { products, heroProduct, formatPrice } from "@/lib/products";
import { ProductCard } from "@/components/ProductCard";
import { AddToCart } from "@/components/AddToCart";
import { EmailCapture } from "@/components/EmailCapture";

const valueProps = [
  {
    icon: "✶",
    title: "Calm, not cluttered",
    body: "A 3-priority method that replaces endless to-do lists with the few things that matter.",
  },
  {
    icon: "↻",
    title: "Buy once, own forever",
    body: "No subscriptions. Free lifetime updates to every pack you own.",
  },
  {
    icon: "⌁",
    title: "Works how you do",
    body: "Notion, printable PDF, and hyperlinked iPad editions — all included.",
  },
  {
    icon: "✓",
    title: "30-day happiness guarantee",
    body: "Use it for a month. If it isn't for you, we'll refund you — keep the files.",
  },
];

const steps = [
  {
    n: "01",
    title: "Choose your pack",
    body: "Start with a single pack or the complete Lumora Life System.",
  },
  {
    n: "02",
    title: "Get it instantly",
    body: "Download links and your Notion duplicate arrive by email in seconds.",
  },
  {
    n: "03",
    title: "Set up in minutes",
    body: "Follow the 7-day setup plan and make it yours. We guide every step.",
  },
];

// NOTE: Replace with real, verified customer reviews before launch.
// These are illustrative placeholders for the template.
const testimonials = [
  {
    quote:
      "I've bought four planners that I abandoned by February. This is the first one I've actually kept using. The 3-priority thing changed my mornings.",
    name: "Maya R.",
    role: "Product designer",
  },
  {
    quote:
      "The Notion version is gorgeous and everything links together. It replaced about five separate apps for me.",
    name: "Daniel K.",
    role: "Freelancer",
  },
  {
    quote:
      "Bought the Life System for the new year. Worth every cent — the finance pack alone paid for itself.",
    name: "Priya S.",
    role: "Nurse & mum of two",
  },
];

export default function Home() {
  const featured = products.filter((p) => !p.hero).slice(0, 6);

  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 -z-10 bg-gradient-to-b from-sand/80 to-cream" />
        <div className="container-x grid items-center gap-12 py-16 lg:grid-cols-2 lg:py-24">
          <div className="animate-fade-up">
            <p className="eyebrow">Digital planners · Notion · iPad · Print</p>
            <h1 className="mt-4 font-serif text-4xl font-semibold leading-[1.05] sm:text-5xl lg:text-6xl">
              Design a calmer,
              <br />
              more intentional life.
            </h1>
            <p className="mt-6 max-w-md text-lg text-ink/75">
              Lumora turns the chaos of modern life into one beautiful, connected
              system — your days, goals, habits, wellness and money, finally in
              one place.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link href="/shop/lumora-life-system" className="btn-primary">
                Shop the Life System
              </Link>
              <Link href="/shop" className="btn-ghost">
                Browse all packs
              </Link>
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-ink/60">
              <span>★★★★★ 4.9/5 from early users</span>
              <span>·</span>
              <span>Instant delivery</span>
              <span>·</span>
              <span>30-day guarantee</span>
            </div>
          </div>

          <div className="animate-fade-up">
            <div className="relative mx-auto max-w-md">
              <div className="card flex aspect-square items-center justify-center bg-terracotta text-[10rem] text-cream shadow-2xl">
                <span>{heroProduct.art}</span>
              </div>
              <div className="card absolute -bottom-6 -left-6 w-56 bg-cream p-4 shadow-xl">
                <p className="text-xs font-semibold text-terracotta">
                  {heroProduct.badge}
                </p>
                <p className="mt-1 font-serif text-lg leading-snug">
                  {heroProduct.name}
                </p>
                <div className="mt-2 flex items-center gap-2">
                  <span className="font-semibold">
                    {formatPrice(heroProduct.price)}
                  </span>
                  <span className="text-sm text-ink/40 line-through">
                    {formatPrice(heroProduct.compareAt!)}
                  </span>
                </div>
                <div className="mt-3">
                  <AddToCart product={heroProduct} full />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Value props */}
      <section className="container-x py-16">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {valueProps.map((v) => (
            <div key={v.title} className="card p-6">
              <div className="text-2xl text-terracotta">{v.icon}</div>
              <h3 className="mt-4 font-serif text-lg font-semibold">
                {v.title}
              </h3>
              <p className="mt-2 text-sm text-ink/70">{v.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Featured products */}
      <section className="container-x py-12">
        <div className="flex items-end justify-between">
          <div>
            <p className="eyebrow">The collection</p>
            <h2 className="mt-2 font-serif text-3xl font-semibold sm:text-4xl">
              Find your starting point
            </h2>
          </div>
          <Link
            href="/shop"
            className="hidden text-sm font-semibold text-terracotta hover:underline sm:block"
          >
            View all →
          </Link>
        </div>
        <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {featured.map((p) => (
            <ProductCard key={p.slug} product={p} />
          ))}
        </div>
      </section>

      {/* Flagship banner */}
      <section className="container-x py-12">
        <div className="card grid items-center gap-8 overflow-hidden bg-ink p-8 text-cream lg:grid-cols-2 lg:p-12">
          <div>
            <p className="eyebrow text-clay">Best value</p>
            <h2 className="mt-3 font-serif text-3xl font-semibold sm:text-4xl">
              Everything, connected.
              <br /> The Lumora Life System.
            </h2>
            <p className="mt-4 max-w-md text-cream/80">
              All six packs in one linked system, three formats, 300+ printable
              pages, and free lifetime updates. Save{" "}
              {formatPrice(heroProduct.compareAt! - heroProduct.price)} versus
              buying separately.
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Link
                href="/shop/lumora-life-system"
                className="btn bg-cream text-ink hover:bg-clay"
              >
                See what&apos;s inside
              </Link>
              <span className="text-2xl font-semibold">
                {formatPrice(heroProduct.price)}{" "}
                <span className="text-base text-cream/50 line-through">
                  {formatPrice(heroProduct.compareAt!)}
                </span>
              </span>
            </div>
          </div>
          <div className="flex items-center justify-center">
            <div className="flex aspect-square w-56 items-center justify-center rounded-2xl bg-terracotta text-8xl">
              {heroProduct.art}
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="container-x py-16">
        <div className="text-center">
          <p className="eyebrow">How it works</p>
          <h2 className="mt-2 font-serif text-3xl font-semibold sm:text-4xl">
            Calm in three steps
          </h2>
        </div>
        <div className="mt-10 grid gap-6 md:grid-cols-3">
          {steps.map((s) => (
            <div key={s.n} className="card p-8">
              <span className="font-serif text-4xl text-clay">{s.n}</span>
              <h3 className="mt-4 font-serif text-xl font-semibold">
                {s.title}
              </h3>
              <p className="mt-2 text-sm text-ink/70">{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Testimonials */}
      <section className="bg-sand/60 py-16">
        <div className="container-x">
          <div className="text-center">
            <p className="eyebrow">Loved by intentional humans</p>
            <h2 className="mt-2 font-serif text-3xl font-semibold sm:text-4xl">
              What early users say
            </h2>
          </div>
          <div className="mt-10 grid gap-6 md:grid-cols-3">
            {testimonials.map((t) => (
              <figure key={t.name} className="card bg-cream p-6">
                <div className="text-gold">★★★★★</div>
                <blockquote className="mt-3 text-sm leading-relaxed text-ink/80">
                  “{t.quote}”
                </blockquote>
                <figcaption className="mt-4 text-sm font-semibold">
                  {t.name}
                  <span className="block font-normal text-ink/60">{t.role}</span>
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      </section>

      {/* Lead magnet */}
      <section className="container-x py-16">
        <div className="card grid items-center gap-8 bg-gradient-to-br from-clay/30 to-sand p-8 lg:grid-cols-2 lg:p-12">
          <div>
            <p className="eyebrow">Free gift</p>
            <h2 className="mt-2 font-serif text-3xl font-semibold sm:text-4xl">
              Try Lumora free.
            </h2>
            <p className="mt-3 max-w-md text-ink/75">
              Get our printable weekly planner page — completely free — plus 10%
              off your first order. No spam, unsubscribe anytime.
            </p>
          </div>
          <EmailCapture />
        </div>
      </section>
    </>
  );
}
