"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  ReactNode,
} from "react";
import { products, Product } from "./products";

export interface CartLine {
  slug: string;
  qty: number;
}

interface CartContextValue {
  lines: CartLine[];
  add: (slug: string, qty?: number) => void;
  remove: (slug: string) => void;
  setQty: (slug: string, qty: number) => void;
  clear: () => void;
  count: number;
  subtotal: number;
  detailed: { product: Product; qty: number; lineTotal: number }[];
  open: boolean;
  setOpen: (v: boolean) => void;
}

const CartContext = createContext<CartContextValue | null>(null);
const STORAGE_KEY = "lumora-cart-v1";

export function CartProvider({ children }: { children: ReactNode }) {
  const [lines, setLines] = useState<CartLine[]>([]);
  const [open, setOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setLines(JSON.parse(raw));
    } catch {
      /* ignore */
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (hydrated) localStorage.setItem(STORAGE_KEY, JSON.stringify(lines));
  }, [lines, hydrated]);

  const add = (slug: string, qty = 1) =>
    setLines((prev) => {
      const found = prev.find((l) => l.slug === slug);
      if (found)
        return prev.map((l) =>
          l.slug === slug ? { ...l, qty: l.qty + qty } : l
        );
      return [...prev, { slug, qty }];
    });

  const remove = (slug: string) =>
    setLines((prev) => prev.filter((l) => l.slug !== slug));

  const setQty = (slug: string, qty: number) =>
    setLines((prev) =>
      qty <= 0
        ? prev.filter((l) => l.slug !== slug)
        : prev.map((l) => (l.slug === slug ? { ...l, qty } : l))
    );

  const clear = () => setLines([]);

  const detailed = useMemo(
    () =>
      lines
        .map((l) => {
          const product = products.find((p) => p.slug === l.slug);
          if (!product) return null;
          return { product, qty: l.qty, lineTotal: product.price * l.qty };
        })
        .filter(Boolean) as {
        product: Product;
        qty: number;
        lineTotal: number;
      }[],
    [lines]
  );

  const subtotal = detailed.reduce((s, l) => s + l.lineTotal, 0);
  const count = lines.reduce((s, l) => s + l.qty, 0);

  return (
    <CartContext.Provider
      value={{
        lines,
        add,
        remove,
        setQty,
        clear,
        count,
        subtotal,
        detailed,
        open,
        setOpen,
      }}
    >
      {children}
    </CartContext.Provider>
  );
}

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used within CartProvider");
  return ctx;
}
