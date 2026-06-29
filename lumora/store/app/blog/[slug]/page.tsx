import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { posts, getPost } from "@/lib/posts";

export function generateStaticParams() {
  return posts.map((p) => ({ slug: p.slug }));
}

export function generateMetadata({
  params,
}: {
  params: { slug: string };
}): Metadata {
  const post = getPost(params.slug);
  if (!post) return {};
  return { title: post.title, description: post.excerpt };
}

export default function PostPage({ params }: { params: { slug: string } }) {
  const post = getPost(params.slug);
  if (!post) notFound();

  return (
    <article className="container-x max-w-3xl py-14">
      <Link href="/blog" className="text-sm text-terracotta hover:underline">
        ← The Journal
      </Link>
      <p className="mt-6 text-xs text-ink/50">
        {new Date(post.date).toLocaleDateString("en-US", {
          month: "long",
          day: "numeric",
          year: "numeric",
        })}{" "}
        · {post.readingTime}
      </p>
      <h1 className="mt-3 font-serif text-3xl font-semibold leading-tight sm:text-4xl">
        {post.title}
      </h1>

      <div className="mt-8 space-y-5 text-lg leading-relaxed text-ink/85">
        {post.body.map((block, i) =>
          block.startsWith("## ") ? (
            <h2 key={i} className="pt-4 font-serif text-2xl font-semibold">
              {block.replace("## ", "")}
            </h2>
          ) : (
            <p key={i}>{block}</p>
          )
        )}
      </div>

      <div className="mt-12 card bg-sand/60 p-6 text-center">
        <p className="font-serif text-xl font-semibold">
          Ready to build your own calm system?
        </p>
        <Link href="/shop" className="btn-accent mt-4">
          Explore the planners
        </Link>
      </div>
    </article>
  );
}
