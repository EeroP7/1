import type { MetadataRoute } from "next";
import { products } from "@/lib/products";
import { posts } from "@/lib/posts";

const SITE = process.env.NEXT_PUBLIC_SITE_URL || "https://lumora.co";

export default function sitemap(): MetadataRoute.Sitemap {
  const staticRoutes = ["", "/shop", "/about", "/faq", "/blog"].map((r) => ({
    url: `${SITE}${r}`,
    lastModified: new Date(),
  }));

  const productRoutes = products.map((p) => ({
    url: `${SITE}/shop/${p.slug}`,
    lastModified: new Date(),
  }));

  const postRoutes = posts.map((p) => ({
    url: `${SITE}/blog/${p.slug}`,
    lastModified: new Date(p.date),
  }));

  return [...staticRoutes, ...productRoutes, ...postRoutes];
}
