# Life on Walls website: working notes

Live site: https://lifeonwalls.co.uk (WordPress, Hostinger, Yoast SEO, LiteSpeed Cache).
This repo holds source assets and build scripts; the site itself is edited through the
WordPress MCP connector.

## Publishing standard: SEO, AEO and GEO (apply to EVERY blog post, press item and page)

Do all of these without being asked. If a post is published without one, fix it.

### SEO
- Slug: short, lowercase, keyword-led (`/living-wall-winter-care/`), no dates or stop words.
- Yoast via `ewpa/yoast-update-seo`: SEO title ≤ 60 chars with the keyphrase near the start;
  meta description 140–160 chars, keyphrase included, plain and specific; focus keyphrase;
  canonical = the page URL; `noindex:false`, `nofollow:false` (pages duplicated from
  "Thank you" inherit noindex, so always set these explicitly); OG and Twitter title,
  description and image.
- One `<h1>` (the article title). Logical `<h2>`/`<h3>` below it; never skip levels.
- Images: WebP, ≤ 1800 px on the long edge, descriptive kebab-case filenames, specific alt
  text (what and where, mention Life on Walls where true), width/height attributes,
  `fetchpriority="high"` on the hero, `loading="lazy"` on the rest. Set a featured image.
- Internal links: 3+ relevant pages (services, FAQ, related posts, contact) with descriptive
  anchor text. External links open in a new tab with `rel="noopener"`.
- Add the item to its index page (blog `/blog/` or press `/news/`) and update the article
  count shown there. Purge cache afterwards and check the live page returns 200, has
  `index, follow`, the right title/description/canonical, and appears in `page-sitemap.xml`.

### AEO (answer engines, featured snippets, AI overviews)
- Open with an "In short" answer of 40–70 words that directly answers the title question.
- Use question-style or task-style headings that match how people search.
- Add a visible FAQ (4–6 questions) with self-contained 40–80 word answers, and matching
  `FAQPage` JSON-LD. Only mark up questions that are visible on the page.
- Include a scannable list: checklist, steps, key figures or plant lists.
- Add an "On this page" table of contents with anchor links for longer posts.

### GEO (generative engines: ChatGPT, Perplexity, Gemini, Claude)
- JSON-LD in the page: `BlogPosting` (blog) or `NewsArticle` (press) with headline,
  description, images, datePublished/dateModified, `inLanguage: en-GB`, author and publisher
  pointing to `https://lifeonwalls.co.uk/#organization`, `about`, `keywords`; plus `FAQPage`.
  Yoast already outputs WebPage, BreadcrumbList, WebSite and Organization; don't duplicate them.
- State concrete, attributable facts (numbers, project names, places, years) in plain
  sentences so they can be quoted. Name Life on Walls and the team as the source.
- Show who wrote it and when (visible date in a `<time datetime>` element).
- Cite sources for third-party claims; for press, credit the publication, issue and author.
- After publishing, add the page to `/llms.txt` under "Key pages". It is served by a
  third-party plugin and cannot be edited through MCP, so give the user the exact line.

### Copy rules
- Keep the client's copy verbatim unless asked to edit it. Additions (summary, checklist,
  FAQ, captions) must be consistent with it and must not invent facts, locations or names.
- UK English. Anja Spice is Life on Walls' Marketing Director; Armando Raish is founder/CEO.
- Don't republish third-party articles in full; summarise in our own words with short quotes.

## How pages are built on this site
- Blog posts and press items are WordPress **pages** (not posts) using the
  `elementor_canvas` template with a self-contained HTML block (`.low-root` wrapper,
  inline styles, Newsreader + Archivo fonts, colours #0B0F0B / #9BB222 / #EDF1E3).
- Fastest reliable method: `ewpa/duplicate-post` on an existing branded page (e.g. 4796
  "Thank you" or 4805 the Landscaper press page), then `ewpa/search-replace` to swap the
  `<main>` content and add JSON-LD + page styles, then `hostinger-ai/pages-update` for title,
  slug, excerpt, featured image and `status: publish`.
- Images: commit to this repo, push, then `hostinger-ai/media-upload-from-url` from the
  `raw.githubusercontent.com` URL (the repo is public).
- Index pages are WPCode snippets: `/news/` = snippet post 4640. Edit with
  `ewpa/search-replace` on the snippet's post ID. Find the blog snippet ID from the
  `[wpcode id="…"]` shortcode in page 4634.
- Purge cache with `ewpa/clear-cache` (page) or `hostinger-ai/litespeed-cache-flush` (site).
- Section build scripts live next to their assets, e.g.
  `blog/2026-11-living-wall-winter-care/build.py`; copy one as the starting point for a new post.
