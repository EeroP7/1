import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { products, getProduct, formatPrice } from "@/lib/products";
import { AddToCart } from "@/components/AddToCart";
import { ProductCard } from "@/components/ProductCard";

export function generateStaticParams() {
  return products.map((p) => ({ slug: p.slug }));
}

export function generateMetadata({
  params,
}: {
  params: { slug: string };
}): Metadata {
  const product = getProduct(params.slug);
  if (!product) return {};
  return {
    title: product.name,
    description: product.shortDescription,
    openGraph: {
      title: `${product.name} · Lumora`,
      description: product.shortDescription,
    },
  };
}

export default function ProductPage({ params }: { params: { slug: string } }) {
  const product = getProduct(params.slug);
  if (!product) notFound();

  const related = products
    .filter((p) => p.slug !== product.slug && !p.hero)
    .slice(0, 3);

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.name,
    description: product.shortDescription,
    brand: { "@type": "Brand", name: "Lumora" },
    offers: {
      "@type": "Offer",
      price: product.price,
      priceCurrency: "USD",
      availability: "https://schema.org/InStock",
    },
  };

  return (
    <div className="container-x py-12">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <nav className="text-sm text-ink/50">
        <Link href="/shop" className="hover:text-terracotta">
          Shop
        </Link>{" "}
        / <span className="text-ink/70">{product.name}</span>
      </nav>

      <div className="mt-6 grid gap-10 lg:grid-cols-2">
        {/* Visual */}
        <div className="lg:sticky lg:top-24 lg:self-start">
          <div
            className={`card flex aspect-square items-center justify-center text-[12rem] text-cream ${product.accent}`}
          >
            {product.art}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {product.formats.map((f) => (
              <span
                key={f}
                className="rounded-full border border-ink/15 bg-white px-3 py-1 text-xs font-medium text-ink/70"
              >
                {f}
              </span>
            ))}
          </div>
        </div>

        {/* Details */}
        <div>
          {product.badge && (
            <span className="inline-block rounded-full bg-terracotta/10 px-3 py-1 text-xs font-semibold text-terracotta">
              {product.badge}
            </span>
          )}
          <h1 className="mt-3 font-serif text-3xl font-semibold sm:text-4xl">
            {product.name}
          </h1>
          <p className="mt-2 text-lg text-ink/70">{product.tagline}</p>

          <div className="mt-5 flex items-center gap-3">
            <span className="text-3xl font-semibold">
              {formatPrice(product.price)}
            </span>
            {product.compareAt && (
              <>
                <span className="text-lg text-ink/40 line-through">
                  {formatPrice(product.compareAt)}
                </span>
                <span className="rounded-full bg-sage/15 px-2 py-1 text-xs font-semibold text-sage">
                  Save {formatPrice(product.compareAt - product.price)}
                </span>
              </>
            )}
          </div>

          <div className="mt-6 max-w-md">
            <AddToCart product={product} full />
            <p className="mt-3 text-center text-xs text-ink/50">
              Instant digital delivery · 30-day guarantee · Free lifetime updates
            </p>
          </div>

          <div className="mt-8 space-y-4 text-ink/80">
            {product.description.map((para, i) => (
              <p key={i}>{para}</p>
            ))}
          </div>

          <div className="mt-8 card p-6">
            <h3 className="font-serif text-lg font-semibold">What&apos;s inside</h3>
            <ul className="mt-4 space-y-2">
              {product.includes.map((item) => (
                <li key={item} className="flex gap-3 text-sm text-ink/80">
                  <span className="text-terracotta">✓</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* Related */}
      <section className="mt-20">
        <h2 className="font-serif text-2xl font-semibold">You might also like</h2>
        <div className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {related.map((p) => (
            <ProductCard key={p.slug} product={p} />
          ))}
        </div>
      </section>
    </div>
  );
}
