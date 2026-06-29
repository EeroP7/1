# Lumora — Product Files

The actual digital goods that customers receive. These map 1:1 to the catalog in
`../store/lib/products.ts`.

```
product/
├── printable/
│   ├── lumora-daily-planner.html   # source (edit here)
│   └── lumora-daily-planner.pdf    # the deliverable (8 pages, A4, print-ready)
├── notion/
│   └── lumora-notion-template.md   # build blueprint for the Notion edition
├── SETUP-GUIDE.md                  # the 7-day onboarding included with every pack
└── README.md
```

## What's production-ready right now

- **The printable Daily Planner PDF** is a finished, sellable product — cover,
  the 3-Priority Method guide, daily / weekly / monthly layouts, a habit tracker,
  a 12-week goals page, and a closing page. This alone is the "Daily Planner Pack."

## Regenerating the PDF after edits

The PDF is rendered from HTML with headless Chromium (no extra tooling):

```bash
chrome --headless --no-pdf-header-footer \
  --print-to-pdf=printable/lumora-daily-planner.pdf \
  file://$(pwd)/printable/lumora-daily-planner.html
```

(Any Chrome/Chromium works. On the build machine the binary lives at
`/opt/pw-browsers/chromium-1194/chrome-linux/chrome`.)

## Building out the rest of the catalog

Each additional pack follows the same pattern: author an HTML page per layout,
render to PDF, and build the matching Notion section from
`notion/lumora-notion-template.md`. The flagship "Lumora Life System" is simply
all packs combined plus the Year Dashboard. Doing one pack well (this one) proves
the format; the rest is repetition.

## License to ship to customers

Sell as **personal-use** digital downloads. Add a one-line license to the order
email: "For personal use. Please don't resell or redistribute the files."
