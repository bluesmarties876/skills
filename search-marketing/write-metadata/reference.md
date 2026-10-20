# write-metadata: reference

Not loaded by default. Rationale, sources and the full worked example behind
[SKILL.md](SKILL.md). Nothing the steps need is only here.

## Sources

Each was read when this skill was written (October 2026).

| Source | What it supports |
| --- | --- |
| [Google: Influencing your title links](https://developers.google.com/search/docs/appearance/title-link) | unique, descriptive, concise titles; no stuffing or boilerplate; brand once with a separator; one clear main heading; no length limit, only truncation; the sources Google builds title links from; the language and writing-system rule |
| [Google: Control your snippets](https://developers.google.com/search/docs/appearance/snippet) | snippets come mainly from page content; the description is used when it describes the page better; unique per page; concrete facts over keyword lists; `nosnippet` and `max-snippet` |
| [Zyppy: title rewrite study](https://zyppy.com/seo/google-title-rewrite-study/) (2022, 80,959 titles) | 61.6% rewritten; 20.6% when the title matches the h1; 51 to 60 characters rewritten least; over 70 characters almost always rewritten |
| [Search Engine Land: Google changed 76% of title tags in Q1 2025](https://searchengineland.com/google-changed-76-of-title-tags-in-q1-2025-heres-what-that-means-454847) | 76% rewritten; brand removal in 63% of changed titles |
| [Portent: how often Google rewrites title tags](https://www.portent.com/blog/seo/how-often-google-rewrites-our-title-tags.htm) | 63% rewritten across about 1.47 million URLs |
| [Ahrefs: meta description study](https://ahrefs.com/blog/meta-description-study/) | the written description shown about 37% of the time; still worth writing |
| [Search Engine Journal on Portent's description study](https://www.searchenginejournal.com/google-rewrites-meta-descriptions-over-70-of-the-time/382140/) | about 30% shown; 150 to 160 characters; key information in the first 100 |
| [Ahrefs: search intent](https://ahrefs.com/blog/search-intent/) | the three Cs: content type, format and angle, read from the top results |
| [NN/g: information scent](https://www.nngroup.com/articles/information-scent/) | the link label is the strongest cue; avoid jargon and branded terms; the summary should add detail to the label |
| [NN/g: the pinball pattern](https://www.nngroup.com/articles/pinball-pattern-search-behavior/) | people scan results non-linearly |
| [Backlinko: organic CTR study](https://backlinko.com/google-ctr-stats) | 40 to 60 character titles had higher click-through rate. Correlation only, from a study owned by an SEO tool vendor |
| [SearchPilot case studies](https://www.searchpilot.com/resources/case-studies) | controlled title tests, for example shortening titles so the price shows (+11%) and moving the location first (+8.5%); results vary by site |

## Why each threshold

| Threshold | Value | Why |
| --- | --- | --- |
| Title soft maximum | 60 characters | Zyppy: 51 to 60 rewritten least; Backlinko: 40 to 60 best click-through rate |
| Title hard maximum (fail) | 70 characters | Zyppy: over 70 rewritten 99.9% of the time |
| Title minimum | 40 characters | Backlinko's lower bound; Zyppy: very short titles almost always rewritten |
| Title-to-h1 agreement | half the h1's words | Zyppy: titles matching the h1 rewritten 20.6% against 61.6% overall. "Half" is this skill's judgement of "says roughly the same thing" |
| Description range | 120 to 160 characters | Portent's 150 to 160 recommendation; about 120 is where Portent saw mobile snippets cut, and Google's "too short" example |
| Key information | first 100 characters | Portent |
| Repeat and stuffing | twice warns; three times fails in titles | Google's keyword-stuffing guidance; the counts are this skill's judgement |
| Description repeats title | 80% of the first sentence's words | NN/g: the summary should add to the label. The figure is this skill's judgement |

Google publishes no length limit. Truncation is by pixel width and device, so character
bands are proxies.

## Full worked example

Fictional: the business, brand and page are invented. `page.html`:

```html
<!doctype html>
<html lang="en"><head>
<title>Home | Ledgerly</title>
<meta name="description" content="Ledgerly is the best expense software. Expense app, expense tool, expenses.">
<meta property="og:title" content="Ledgerly">
</head><body>
<h1>Expense tracking for small teams</h1>
<p>Snap receipts, approve claims on your phone and sync to your accounts.</p>
</body></html>
```

The candidates file is SKILL.md's step 4 sample with `page` set to `fetch`'s full output for
that file, and two more candidates: the third is shown in SKILL.md's step 5 output, and the
second is:

```json
{"title": "Ledgerly: Expense Tracking Software",
 "description": "Ledgerly is the best expense tracking software for small teams. Expense claims, expense reports and expense approvals in one expense app."}
```

Verdicts: candidate 0 `OK`; candidate 1 `WARN` (`title-under-40`,
`query-missing-from-title`, `description-stuffing`); candidate 2 `FAIL` (`title-over-70`,
`description-under-120`). Candidate 2's "Small-Team" counts as having "teams" because the
script folds plurals.

## Common failure modes

- **Writing to a keyword the page cannot win.** A product page will not rank for a query
  whose results are all "best X" lists, whatever its title says. Step 2 catches this.
- **Two pages of one site chasing one query.** A team or feature page that repeats a
  section of the main product page splits the same searches with it. Step 2 catches this.
- **Treating the description as a ranking lever.** It is not one. It earns clicks, when
  Google shows it.
- **Brand first on every page.** Google strips brands from most rewritten titles. Put it
  last, once, unless house rules say otherwise.
- **Changing the title and calling the result.** Click-through rate moves with position and
  season. Compare like positions, or test against a control group.
- **One title template for every page.** Google treats near-identical titles as
  boilerplate and replaces them.

## Script limits

Characters, not pixels. Whole-word matching; simple English plurals fold to the singular, but there is no other
stemming, and other languages' plurals are not folded. Raw HTML only. Writing-system
detection compares the dominant script only, not the language: English and French both read
as Latin. At most 5 MB read and a 20-second timeout. The script judges form, not whether a
candidate is true of the page or fits the intent; that is the agent's job in steps 2 to 6.
