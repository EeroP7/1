// Lumora product catalog.
// All products are DIGITAL (instant download / Notion duplicate link) — ~95% gross margin,
// zero inventory, instant global fulfillment.
//
// To take real payments: create a Stripe Payment Link for each product/price and paste the
// URL into `stripeLink`. Until then the cart routes to /checkout with copy-ready instructions.
// Docs: https://stripe.com/docs/payment-links

export type Format = "Notion" | "Printable PDF" | "iPad / GoodNotes";

export interface Product {
  slug: string;
  name: string;
  tagline: string;
  price: number; // USD
  compareAt?: number; // USD, shown struck-through
  badge?: string;
  formats: Format[];
  hero: boolean;
  bestSeller?: boolean;
  bundle?: boolean;
  // emoji used as lightweight, dependency-free product art
  art: string;
  accent: string; // tailwind bg utility for the art tile
  shortDescription: string;
  includes: string[];
  description: string[];
  // Optional Stripe Payment Link. Leave empty until you create yours.
  stripeLink?: string;
}

export const products: Product[] = [
  {
    slug: "lumora-life-system",
    name: "The Lumora Life System",
    tagline: "Your entire life, beautifully organized — in one system.",
    price: 97,
    compareAt: 189,
    badge: "Complete Bundle",
    formats: ["Notion", "Printable PDF", "iPad / GoodNotes"],
    hero: true,
    bestSeller: true,
    bundle: true,
    art: "✺",
    accent: "bg-terracotta",
    shortDescription:
      "Every Lumora pack in one connected system: planning, goals, habits, wellness, finance and meals. The calm operating system for your year.",
    includes: [
      "All 6 core packs (Daily, Goals, Habits, Wellness, Finance, Meals)",
      "The Lumora Year Dashboard (Notion) — everything linked in one place",
      "300+ printable pages (US Letter + A4)",
      "Hyperlinked iPad / GoodNotes edition",
      "Quick-start guide + 7-day setup plan",
      "Free lifetime updates to every pack",
    ],
    description: [
      "Most planners give you a calendar and call it a day. The Lumora Life System gives you an entire operating model for an intentional life — where your goals, habits, daily plan, wellness, money and meals all talk to each other.",
      "Start your morning in the Daily planner, see how today moves your quarterly goals, check your habit streaks, and keep your budget and meals on track — without app-switching or starting from scratch.",
      "Delivered in three formats so it fits how you actually work: a fully-linked Notion workspace, print-at-home PDFs, and a hyperlinked edition for iPad note apps. Buy once, own forever, including every future update.",
    ],
  },
  {
    slug: "daily-planner-pack",
    name: "The Daily Planner Pack",
    tagline: "Win the day, every day.",
    price: 24,
    compareAt: 39,
    badge: "Most Popular",
    formats: ["Notion", "Printable PDF", "iPad / GoodNotes"],
    hero: false,
    bestSeller: true,
    art: "☀",
    accent: "bg-gold",
    shortDescription:
      "Daily, weekly and monthly layouts built around a calm 3-priority method. Plan less, finish more.",
    includes: [
      "Daily / weekly / monthly planning pages",
      "The 3-Priority daily method (the core of the system)",
      "Time-blocking + shutdown ritual",
      "Notion + printable + iPad formats",
    ],
    description: [
      "The planner that quietly removes the overwhelm. Instead of a 30-item to-do list, the Lumora method asks for three priorities — the things that, if done, make today a win.",
      "Includes daily, weekly and monthly layouts, a time-blocking grid, and an end-of-day shutdown ritual that helps you actually switch off.",
    ],
  },
  {
    slug: "goals-vision-pack",
    name: "The Goals & Vision Pack",
    tagline: "From someday to done.",
    price: 24,
    formats: ["Notion", "Printable PDF", "iPad / GoodNotes"],
    hero: false,
    art: "◎",
    accent: "bg-sage",
    shortDescription:
      "Turn big, vague dreams into quarterly milestones and weekly moves with a vision board, goal-mapping and review system.",
    includes: [
      "Annual vision board + values exercise",
      "12-week goal mapping (the proven cadence)",
      "Quarterly + weekly review templates",
      "Notion + printable + iPad formats",
    ],
    description: [
      "Goals fail when they live in your head. This pack pulls them out, breaks them into 12-week sprints, and gives you a weekly review rhythm so you never drift.",
      "Includes a values clarifier, an annual vision board, quarterly goal maps, and the review templates that keep momentum alive.",
    ],
  },
  {
    slug: "habit-builder-pack",
    name: "The Habit Builder Pack",
    tagline: "Small steps, compounded.",
    price: 19,
    formats: ["Notion", "Printable PDF", "iPad / GoodNotes"],
    hero: false,
    art: "❧",
    accent: "bg-clay",
    shortDescription:
      "Habit trackers, streak grids and a science-based habit-stacking worksheet to make good habits automatic.",
    includes: [
      "Monthly + yearly habit trackers",
      "Habit-stacking + cue/reward worksheet",
      "Streak grids and reflection prompts",
      "Notion + printable + iPad formats",
    ],
    description: [
      "Built on the cue–routine–reward loop, this pack makes habits visual and satisfying. Watch streaks grow, stack new habits onto existing ones, and reflect on what's actually sticking.",
      "Includes monthly and full-year trackers plus a habit-stacking worksheet drawn from behavior-science research.",
    ],
  },
  {
    slug: "wellness-self-care-pack",
    name: "The Wellness & Self-Care Pack",
    tagline: "Take care of the one who does everything.",
    price: 24,
    formats: ["Notion", "Printable PDF", "iPad / GoodNotes"],
    hero: false,
    bestSeller: true,
    art: "❀",
    accent: "bg-sage",
    shortDescription:
      "Mood and sleep trackers, gratitude journaling, self-care planning and a gentle reset routine for hard weeks.",
    includes: [
      "Mood + sleep + energy trackers",
      "Gratitude + reflection journal pages",
      "Self-care menu + weekly reset ritual",
      "Notion + printable + iPad formats",
    ],
    description: [
      "Wellness isn't a luxury — it's maintenance. This pack helps you notice patterns in mood, sleep and energy, and build small rituals that keep you steady.",
      "Includes trackers, gratitude and reflection journaling, a self-care menu, and a gentle weekly reset for when life gets heavy.",
    ],
  },
  {
    slug: "finance-budget-pack",
    name: "The Finance & Budget Pack",
    tagline: "Calm, confident money.",
    price: 29,
    formats: ["Notion", "Printable PDF"],
    hero: false,
    art: "❖",
    accent: "bg-terracotta",
    shortDescription:
      "Zero-based budgeting, debt payoff trackers, savings goals and a net-worth dashboard — money clarity without the spreadsheets-from-scratch.",
    includes: [
      "Monthly zero-based budget (auto-totals in Notion)",
      "Debt snowball / avalanche trackers",
      "Savings goals + sinking funds",
      "Net-worth dashboard",
    ],
    description: [
      "Money stress usually comes from not knowing the numbers. This pack gives you a complete picture: a monthly budget that balances to zero, debt-payoff trackers, savings goals and a net-worth dashboard.",
      "The Notion edition auto-calculates totals so you just plug in numbers. The printable edition is perfect for cash-envelope and pen-and-paper budgeters.",
    ],
  },
  {
    slug: "meal-planner-pack",
    name: "The Meal Planner Pack",
    tagline: "Dinner, decided.",
    price: 19,
    formats: ["Notion", "Printable PDF"],
    hero: false,
    art: "✿",
    accent: "bg-gold",
    shortDescription:
      "Weekly meal planning, auto-building grocery lists, a recipe library and a pantry tracker to cut waste and the daily 'what's for dinner?'",
    includes: [
      "Weekly + monthly meal plans",
      "Grocery list that builds from your plan (Notion)",
      "Recipe library + meal idea bank",
      "Pantry + freezer inventory",
    ],
    description: [
      "End the 5pm panic. Plan your week, and the Notion grocery list builds itself from the meals you choose.",
      "Includes a recipe library, meal idea bank, and a pantry tracker so you waste less and shop smarter.",
    ],
  },
  {
    slug: "core-bundle",
    name: "The Core Bundle",
    tagline: "The three packs everyone starts with.",
    price: 59,
    compareAt: 72,
    badge: "Best Value Starter",
    formats: ["Notion", "Printable PDF", "iPad / GoodNotes"],
    hero: false,
    bundle: true,
    art: "❂",
    accent: "bg-clay",
    shortDescription:
      "Daily Planner + Goals & Vision + Habit Builder. The essential foundation, bundled and discounted.",
    includes: [
      "The Daily Planner Pack",
      "The Goals & Vision Pack",
      "The Habit Builder Pack",
      "All three formats included",
    ],
    description: [
      "Not ready for the full Life System? Start here. The Core Bundle pairs the three packs that work best together — plan your day, aim at your goals, and build the habits that get you there.",
      "Bundled at a lower price than buying the three separately.",
    ],
  },
];

export const getProduct = (slug: string) =>
  products.find((p) => p.slug === slug);

export const heroProduct = products.find((p) => p.hero)!;

export const formatPrice = (n: number) =>
  `$${n.toFixed(n % 1 === 0 ? 0 : 2)}`;
