"use client";

import { useState } from "react";
import { useCart } from "@/lib/cart";
import { Product, formatPrice } from "@/lib/products";

export function AddToCart({
  product,
  full = false,
}: {
  product: Product;
  full?: boolean;
}) {
  const { add, setOpen } = useCart();
  const [added, setAdded] = useState(false);

  function handle() {
    add(product.slug);
    setAdded(true);
    setOpen(true);
    setTimeout(() => setAdded(false), 1500);
  }

  return (
    <button
      onClick={handle}
      className={`btn-accent ${full ? "w-full" : ""}`}
      aria-label={`Add ${product.name} to cart`}
    >
      {added ? "Added ✓" : `Add to cart · ${formatPrice(product.price)}`}
    </button>
  );
}
