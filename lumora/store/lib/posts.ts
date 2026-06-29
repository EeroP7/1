// Journal posts — these double as SEO content targeting high-intent search terms
// (e.g. "how to use a notion planner", "best digital planner for ipad").
// Written in lightweight markdown-ish paragraphs rendered by the blog template.

export interface Post {
  slug: string;
  title: string;
  excerpt: string;
  date: string;
  readingTime: string;
  keyword: string;
  body: string[];
}

export const posts: Post[] = [
  {
    slug: "how-to-actually-stick-to-a-planner",
    title: "How to Actually Stick to a Planner (When You Never Have Before)",
    excerpt:
      "Most planners are abandoned by February. Here's the simple, research-backed system that makes planning a habit you keep.",
    date: "2026-01-08",
    readingTime: "6 min read",
    keyword: "how to stick to a planner",
    body: [
      "If you've bought a planner before and stopped using it within weeks, you're not lazy or disorganised. You were set up to fail by a tool that demanded too much, too fast.",
      "## Why most planners fail",
      "The typical planner asks you to fill a blank page every single day. That's a high-friction ritual, and high-friction rituals don't survive busy weeks. The first day you skip becomes two, then the guilt of a half-empty planner makes you avoid it entirely.",
      "The fix isn't more discipline. It's lower friction and a clearer payoff.",
      "## The 3-priority method",
      "Instead of a 30-item to-do list, write down three priorities for the day — the things that, if completed, would make today a win. Three is small enough to finish, which means you get the dopamine hit of crossing everything off. That feeling is what brings you back tomorrow.",
      "Everything else goes in a single 'later' list. You're not ignoring it; you're protecting your attention.",
      "## Stack it onto something you already do",
      "Habits stick when they're attached to an existing cue. Plan your three priorities while the kettle boils, or review them when you sit down at your desk. The cue does the remembering for you.",
      "## Make it beautiful enough to want to open",
      "This sounds shallow, but it matters: a calm, well-designed page is something you look forward to. That's a big part of why our planners are designed the way they are — the aesthetics aren't decoration, they're retention.",
      "## A 7-day on-ramp",
      "Don't try to use every feature on day one. Start with just the daily 3-priority page for a week. Add weekly planning in week two. Layer in habits and goals once the daily ritual is automatic. Slow is smooth, and smooth is permanent.",
      "If you'd like a system built around exactly this method, the Lumora Daily Planner Pack is where most people start.",
    ],
  },
  {
    slug: "notion-vs-printable-vs-ipad-planner",
    title: "Notion vs. Printable vs. iPad: Which Digital Planner Is Right for You?",
    excerpt:
      "Three formats, three very different humans. A quick, honest guide to choosing the planner format you'll actually use.",
    date: "2026-01-15",
    readingTime: "5 min read",
    keyword: "best digital planner format",
    body: [
      "Digital planners come in three main flavours: Notion templates, printable PDFs, and hyperlinked PDFs for iPad note apps like GoodNotes. Here's how to choose — and why Lumora includes all three.",
      "## Choose Notion if… you live on your laptop",
      "Notion is unbeatable for connected, database-driven planning. Your goals can link to your weekly plan, your habits can roll up into a dashboard, and everything updates automatically. If you already work on a computer most of the day, Notion will feel like a superpower.",
      "The trade-off: it's screen-based, so it's less suited to people who want to step away from devices.",
      "## Choose printable if… you think better on paper",
      "There's real research suggesting handwriting improves memory and reduces stress compared to typing. If you find screens draining, print the pages you need and keep them in a binder. Zero apps, zero notifications, just you and a pen.",
      "## Choose iPad / GoodNotes if… you want both",
      "A hyperlinked PDF in GoodNotes or Notability gives you the feel of handwriting with the convenience of digital — tap to jump between months, never run out of pages, and keep everything in one file. It's the most popular format for students and creatives.",
      "## Why not have all three?",
      "Your life isn't one format. You might plan your week in Notion at your desk and journal by hand in the evening. That's exactly why every Lumora pack includes Notion, printable and iPad editions for one price — use whichever fits the moment.",
      "Start with the Core Bundle if you want to try the method across all three formats.",
    ],
  },
  {
    slug: "sunday-reset-routine",
    title: "The Sunday Reset: A 30-Minute Routine for a Calmer Week",
    excerpt:
      "A simple weekly reset that takes the panic out of Monday — copy our exact checklist.",
    date: "2026-01-22",
    readingTime: "4 min read",
    keyword: "sunday reset routine",
    body: [
      "The calmest people you know usually aren't doing more — they're resetting weekly so nothing piles up. Here's a 30-minute Sunday reset you can steal.",
      "## 1. Brain dump (5 min)",
      "Empty everything swirling in your head onto one page. Tasks, worries, ideas. You can't organise what's still in your head.",
      "## 2. Review last week (5 min)",
      "What went well? What drained you? One honest look backwards makes the next week sharper. No judgement — just data.",
      "## 3. Set three weekly priorities (5 min)",
      "Pick the three things that would make next week a win. These become the anchor for your daily 3-priority lists.",
      "## 4. Plan meals + check the calendar (10 min)",
      "Glance at what's coming, decide a few dinners, and build your grocery list. Future-you will be grateful on Wednesday at 6pm.",
      "## 5. A small act of self-care (5 min)",
      "Tidy your desk, make a tea, light a candle. End the reset feeling ready, not rushed.",
      "Our Wellness & Self-Care Pack includes a printable version of this exact routine, plus the trackers that make it stick.",
    ],
  },
];

export const getPost = (slug: string) => posts.find((p) => p.slug === slug);
