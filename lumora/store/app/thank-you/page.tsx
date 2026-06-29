import Link from "next/link";

export const metadata = { title: "Thank you" };

export default function ThankYou() {
  return (
    <div className="container-x flex min-h-[60vh] flex-col items-center justify-center py-20 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-sage text-3xl text-cream">
        ✓
      </div>
      <h1 className="mt-6 font-serif text-3xl font-semibold">
        Welcome to Lumora.
      </h1>
      <p className="mt-3 max-w-md text-ink/70">
        Your payment was successful. Your download links and Notion duplicate
        link are in your inbox — check spam if you don&apos;t see them in a
        minute. Follow the included 7-day setup plan and make it yours.
      </p>
      <Link href="/shop" className="btn-accent mt-8">
        Explore more packs
      </Link>
    </div>
  );
}
