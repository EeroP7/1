import type { Metadata } from "next";
import { products } from "@/lib/products";
import { ProductCard } from "@/components/ProductCard";

export const metadata: Metadata = {
  title: "Shop all digital planners & packs",
  description:
    "Browse every Lumora digital planner and pack — daily planning, goals, habits, wellness, finance and meals. For Notion, iPad and print.",
};

export default function ShopPage() {
  const bundles = products.filter((p) => p.bundle);
  const single = products.filter((p) => !p.bundle);

  return (
    <div className="container-x py-14">
      <p className="eyebrow">The full collection</p>
      <h1 className="mt-2 font-serif text-4xl font-semibold sm:text-5xl">
        Everything Lumora makes
      </h1>
      <p className="mt-4 max-w-xl text-ink/70">
        Each pack works on its own and links seamlessly with the rest. Every
        product includes Notion, printable PDF and (where noted) iPad editions —
        with free lifetime updates.
      </p>

      <h2 className="mt-14 font-serif text-2xl font-semibold">Bundles</h2>
      <div className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {bundles.map((p) => (
          <ProductCard key={p.slug} product={p} />
        ))}
      </div>

      <h2 className="mt-16 font-serif text-2xl font-semibold">Single packs</h2>
      <div className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {single.map((p) => (
          <ProductCard key={p.slug} product={p} />
        ))}
      </div>
    </div>
  );
}
