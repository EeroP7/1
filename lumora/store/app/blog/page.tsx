import type { Metadata } from "next";
import Link from "next/link";
import { posts } from "@/lib/posts";

export const metadata: Metadata = {
  title: "The Journal — intentional living, planning & productivity",
  description:
    "Practical, calm advice on planning, habits, productivity and wellness from the Lumora team.",
};

export default function BlogIndex() {
  return (
    <div className="container-x py-14">
      <p className="eyebrow">The Journal</p>
      <h1 className="mt-2 font-serif text-4xl font-semibold sm:text-5xl">
        Ideas for an intentional life
      </h1>
      <p className="mt-4 max-w-xl text-ink/70">
        Short, practical reads on planning, habits and wellness — no fluff, no
        hustle-culture guilt.
      </p>

      <div className="mt-12 grid gap-6 md:grid-cols-3">
        {posts.map((p) => (
          <Link
            key={p.slug}
            href={`/blog/${p.slug}`}
            className="card group flex flex-col p-6 transition hover:-translate-y-1 hover:shadow-lg"
          >
            <span className="text-xs text-ink/50">
              {new Date(p.date).toLocaleDateString("en-US", {
                month: "long",
                day: "numeric",
                year: "numeric",
              })}{" "}
              · {p.readingTime}
            </span>
            <h2 className="mt-3 flex-1 font-serif text-xl font-semibold leading-snug group-hover:text-terracotta">
              {p.title}
            </h2>
            <p className="mt-3 text-sm text-ink/70">{p.excerpt}</p>
            <span className="mt-4 text-sm font-semibold text-terracotta">
              Read →
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
