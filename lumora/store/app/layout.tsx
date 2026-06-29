import type { Metadata } from "next";
import "./globals.css";
import { CartProvider } from "@/lib/cart";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";

const SITE = "https://lumora.co";

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: {
    default: "Lumora — Digital Planners & Life Systems for an Intentional Life",
    template: "%s · Lumora",
  },
  description:
    "Beautifully designed digital planners and life systems for Notion, iPad and print. Plan your days, build habits, reach goals and feel calmer — buy once, own forever.",
  keywords: [
    "digital planner",
    "notion planner",
    "notion template",
    "goodnotes planner",
    "printable planner",
    "habit tracker",
    "goal planner",
    "budget template",
  ],
  openGraph: {
    title: "Lumora — Digital Planners & Life Systems",
    description:
      "The calm operating system for your year. Digital planners for Notion, iPad and print.",
    url: SITE,
    siteName: "Lumora",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Lumora — Digital Planners & Life Systems",
    description:
      "The calm operating system for your year. Digital planners for Notion, iPad and print.",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <CartProvider>
          <Header />
          <main>{children}</main>
          <Footer />
        </CartProvider>
      </body>
    </html>
  );
}
