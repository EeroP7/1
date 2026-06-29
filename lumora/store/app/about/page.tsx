import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "About",
  description:
    "Lumora makes beautifully designed digital planners and life systems for people who want a calmer, more intentional life.",
};

export default function About() {
  return (
    <div className="container-x max-w-3xl py-16">
      <p className="eyebrow">Our story</p>
      <h1 className="mt-2 font-serif text-4xl font-semibold sm:text-5xl">
        Tools for a calmer, more intentional life.
      </h1>

      <div className="mt-8 space-y-5 text-lg leading-relaxed text-ink/85">
        <p>
          Lumora started with a frustration most of us share: a drawer full of
          half-used planners and a phone full of productivity apps that somehow
          made life feel busier, not calmer.
        </p>
        <p>
          We believed the problem wasn&apos;t us — it was the tools. So we built
          the system we wished existed: beautiful enough to want to open, simple
          enough to actually keep using, and connected enough that your goals,
          habits, days, wellness and money finally live in one place.
        </p>
        <p>
          Everything we make is digital, so it&apos;s instant, affordable, and
          always improving. You buy once and own it forever — including every
          future update. No subscriptions, no clutter, no guilt.
        </p>
        <h2 className="pt-4 font-serif text-2xl font-semibold">
          What we believe
        </h2>
        <p>
          Productivity isn&apos;t about doing more. It&apos;s about making room
          for what matters. A good system should give you back time and calm —
          not demand more of both.
        </p>
        <p>
          That&apos;s the bar for everything in the Lumora collection. If a page
          doesn&apos;t earn its place by making your life lighter, it
          doesn&apos;t ship.
        </p>
      </div>

      <div className="mt-12 grid gap-6 sm:grid-cols-3">
        {[
          { stat: "3 formats", label: "Notion · Print · iPad, always included" },
          { stat: "Buy once", label: "Free lifetime updates, no subscriptions" },
          { stat: "30 days", label: "Happiness guarantee on every order" },
        ].map((b) => (
          <div key={b.stat} className="card p-6 text-center">
            <p className="font-serif text-2xl font-semibold text-terracotta">
              {b.stat}
            </p>
            <p className="mt-2 text-sm text-ink/70">{b.label}</p>
          </div>
        ))}
      </div>

      <div className="mt-12 text-center">
        <Link href="/shop" className="btn-primary">
          Explore the collection
        </Link>
      </div>
    </div>
  );
}
