import Link from "next/link";
import { Product, formatPrice } from "@/lib/products";
import { AddToCart } from "./AddToCart";

export function ProductCard({ product }: { product: Product }) {
  return (
    <div className="card group flex flex-col overflow-hidden transition hover:-translate-y-1 hover:shadow-lg">
      <Link href={`/shop/${product.slug}`} className="block">
        <div
          className={`relative flex aspect-[4/3] items-center justify-center text-6xl text-cream ${product.accent}`}
        >
          <span className="opacity-90 transition group-hover:scale-110">
            {product.art}
          </span>
          {product.badge && (
            <span className="absolute left-3 top-3 rounded-full bg-cream/95 px-3 py-1 text-xs font-semibold text-ink">
              {product.badge}
            </span>
          )}
        </div>
      </Link>
      <div className="flex flex-1 flex-col p-5">
        <Link href={`/shop/${product.slug}`}>
          <h3 className="font-serif text-lg font-semibold leading-snug hover:text-terracotta">
            {product.name}
          </h3>
        </Link>
        <p className="mt-2 flex-1 text-sm text-ink/70">
          {product.shortDescription}
        </p>
        <div className="mt-4 flex items-center gap-2">
          <span className="text-lg font-semibold">
            {formatPrice(product.price)}
          </span>
          {product.compareAt && (
            <span className="text-sm text-ink/40 line-through">
              {formatPrice(product.compareAt)}
            </span>
          )}
        </div>
        <div className="mt-4">
          <AddToCart product={product} full />
        </div>
      </div>
    </div>
  );
}
