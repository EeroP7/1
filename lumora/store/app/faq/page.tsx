import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "FAQ",
  description:
    "Answers to common questions about Lumora digital planners — formats, delivery, refunds and Notion setup.",
};

const faqs = [
  {
    q: "How do I receive my planner?",
    a: "Instantly. The moment your payment goes through, you'll get an email with your download links and a Notion duplicate link. No shipping, no waiting.",
  },
  {
    q: "Do I need to pay for Notion?",
    a: "No. Notion's free plan is more than enough to use any Lumora template. Just click the duplicate link and it's copied into your own workspace.",
  },
  {
    q: "What formats are included?",
    a: "Every pack includes a Notion template and printable PDFs (US Letter + A4). Most also include a hyperlinked edition for iPad apps like GoodNotes and Notability — it's listed on each product page.",
  },
  {
    q: "Can I print the planners at home?",
    a: "Yes. The PDFs are designed for clean home or office printing on standard paper sizes, and they also work beautifully sent to a print shop.",
  },
  {
    q: "Is this a subscription?",
    a: "Never. You pay once and own it forever — including all future updates to the packs you bought.",
  },
  {
    q: "What's your refund policy?",
    a: "We offer a 30-day happiness guarantee. If a planner isn't right for you, email us within 30 days for a full refund — and you can keep the files.",
  },
  {
    q: "Can I use these for my own clients or resell them?",
    a: "Lumora products are licensed for personal use. You can't resell or redistribute the files, but you're welcome to use them in your own life as much as you like.",
  },
];

export default function FAQ() {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((f) => ({
      "@type": "Question",
      name: f.q,
      acceptedAnswer: { "@type": "Answer", text: f.a },
    })),
  };

  return (
    <div className="container-x max-w-3xl py-16">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <p className="eyebrow">Questions</p>
      <h1 className="mt-2 font-serif text-4xl font-semibold sm:text-5xl">
        Frequently asked
      </h1>

      <div className="mt-10 divide-y divide-ink/10">
        {faqs.map((f) => (
          <details key={f.q} className="group py-5">
            <summary className="flex cursor-pointer list-none items-center justify-between font-serif text-lg font-semibold">
              {f.q}
              <span className="text-terracotta transition group-open:rotate-45">
                +
              </span>
            </summary>
            <p className="mt-3 text-ink/75">{f.a}</p>
          </details>
        ))}
      </div>
    </div>
  );
}
