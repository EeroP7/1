# The Lumora Life System — Notion Edition (build doc)

This document is the **content blueprint** for the Notion version of the product.
Paste these blocks into a Notion page to assemble the template, then share it as a
**duplicate link** (Share → Publish → "Allow duplicate as template"). That link is
what customers receive on purchase.

> Tip: Build it once, lock the master copy, and only ever share the *duplicate* link.

---

## 🏠 Home — "The Lumora Year Dashboard"

A single page that links everything. Suggested layout:

- **Callout (terracotta):** "Welcome to your calmer year. Start with today's three priorities."
- **Today** — linked view of the Daily database, filtered to `Date is Today`.
- **This week's 3 priorities** — synced block from the Weekly page.
- **Quick links** (buttons): Daily · Weekly · Goals · Habits · Wellness · Finance · Meals.
- **Goal progress** — linked view of Goals, showing `Progress` bar property.
- **Habit streak** — linked view of Habits with this week's checkboxes.

---

## ☀️ Daily (database)

Database name: **Daily Log**

| Property | Type |
|---|---|
| Name (Date) | Title |
| Date | Date |
| Priority 1 / 2 / 3 | Text (or 3 checkboxes "P1 done" etc.) |
| Later list | Text |
| Movement / Water / Real food | Checkbox |
| One win | Text |
| Grateful for | Text |
| Energy (1–5) | Select |

**Daily template button** (inside the database → New → template):
- Heading: "Today's 3 priorities"
- To-do list ×3 (the three priorities)
- Divider
- Heading: "Later list" → to-do list
- Heading: "Time blocks" → table (Time | Focus), rows 7am–6pm
- Three columns: Move & nourish (checkboxes) | One win | Grateful for

---

## 🗓 Weekly (page)

- **This week's 3 priorities** — 3 to-do items.
- **The week** — table, 7 columns (Mon–Sun), one row for top tasks.
- **Reflection** — two columns: "What went well" / "What to adjust".
- Link daily entries to the week via a `Week` relation if you want roll-ups.

---

## ◎ Goals (database)

Database name: **12-Week Goals**

| Property | Type |
|---|---|
| Goal | Title |
| Why it matters | Text |
| Quarter | Select (Q1–Q4) |
| Status | Select (Not started / In progress / Done) |
| Progress | Number (0–100) → show as bar |
| Next step | Text |

Add a board view grouped by `Status`, and a gallery view for the vision board
(cover images = your goals made visual).

---

## ❧ Habits (database)

Database name: **Habits**

- One row per habit. Properties: `Habit` (title), `Why`, `Cue`, `Reward`.
- A linked "tracker" database **Habit Log** with `Date`, `Habit` (relation),
  `Done` (checkbox). A calendar view of Habit Log gives you the classic
  shade-a-box streak grid.
- **Habit stack** callout: "After I ____, I will ____."

---

## ❀ Wellness (page)

- **Mood / Sleep / Energy** tracker — small database with `Date`, `Mood` (select
  with emoji), `Sleep hrs` (number), `Energy` (1–5).
- **Gratitude journal** — database with `Date` + `Entry`.
- **Self-care menu** — checklist of go-to resets (walk, bath, call a friend…).
- **Weekly reset ritual** — the 5-step Sunday reset checklist.

---

## ❖ Finance (database)

Database name: **Monthly Budget**

| Property | Type |
|---|---|
| Item | Title |
| Category | Select (Income / Housing / Food / …) |
| Planned | Number ($) |
| Actual | Number ($) |
| Difference | Formula: `prop("Planned") - prop("Actual")` |

- Add a `Sum` on Planned/Actual at the bottom of each view.
- **Debt tracker**: database with `Balance`, `Min payment`, `Rate`, ordered
  smallest-first (snowball) or highest-rate-first (avalanche).
- **Savings goals**: `Goal`, `Target`, `Saved`, `Progress` (formula).
- **Net worth**: assets − liabilities, snapshot monthly.

---

## ✿ Meals (page)

- **Weekly meal plan** — table, 7 days × (breakfast/lunch/dinner).
- **Recipe library** — database with `Recipe`, `Tags`, `Link`, `Ingredients`.
- **Grocery list** — database with `Item`, `Have it?` (checkbox), `Aisle`;
  relate to recipes so the list builds from the week's plan.
- **Pantry/freezer inventory** — simple checklist database.

---

## Delivery checklist (before sharing)

- [ ] Remove all your personal data from the master.
- [ ] Set page icons + a consistent cover image per section (brand terracotta).
- [ ] Test the duplicate link in a private/incognito window.
- [ ] Include the "7-day setup plan" page (see `product/SETUP-GUIDE.md`).
- [ ] Add a "Start here" callout linking to the setup plan.
