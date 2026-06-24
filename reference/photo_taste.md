# Rahul Mathur's image taste (learned from his last 30 posts)

His images split into two families: **self-made data graphics** (most analytical posts) and
**sourced real photos** (human-interest posts). Many posts have no image at all (pure text takes).

## Shared DNA of his self-made graphics
- White background, no heavy branding. Looks like a sharp analyst's worksheet, not a marketing asset.
- A **bold dark headline = the thesis** of the post (occasionally one emoji like 🔥).
- An **italic gray attribution line** right under it:
  `created by @<handle> | Source: <source> (retrieved on <date>)`
- **Color used to highlight the punchline**: green = good/positive, red = bad/loss, yellow = neutral,
  and a single highlighted cell for "the number that matters".
- Precise units everywhere: ₹ crore/lakh, x-multiples, %, XIRR, FY labels.

## Content -> image mapping (the taste)
| If the post is about... | He uses... | Seen in |
|---|---|---|
| VC fund returns / exit / IPO math | **Color-coded data table** (red/green/yellow row banding, Gross MOIC column) | Blume 36.65x on Turtlemint; Sauce VC 8x on Innovist |
| "Let me do the unit-economics math" deep dive | **Calculations worksheet**: a table + an "Aggressive model / Conservative model" text breakdown, doc-style | Urban Company CX/PX support cost per order |
| Revenue / growth story | **Clean bar chart**, gradient bars, ₹ value labels per bar, headline + attribution | SNITCH revenue FY21->FY26 (₹11Cr -> ₹900Cr) |
| App / product / platform comparison | **Play Store-style app cards** with green/red annotation boxes around key metrics | Swiggy Toing v/s Ownly (Rapido) |
| Founder / brand / company story | **Real photo** (founder podcast still, etc.), sourced not generated | SNITCH founder interview still |
| Consumer / product moment | **Real flat-lay photo** of the product | food/snacks box flat-lay |
| Business history / storytelling / book reference | **Photo of a book page with yellow highlighter** on the key passage | Tata/Lakme cosmetics history |

## What this means for automation
1. **Templates to build (HTML -> PNG, headless Chrome):**
   - `returns_table`  (color-coded financial table)  <- highest frequency
   - `bar_chart`      (growth/revenue bars)
   - `app_showdown`   (Play Store comparison)  [prototype done]
   - `calc_worksheet` (table + model breakdown)  [optional, advanced]
   - `thesis_card`    (headline + attribution fallback when no structured data)
2. **Real-photo posts** are not generated. For founder/product/history stories, either fetch a
   relevant real image (founder photo, product shot) or skip the image and post text-only.
3. **The generator decides per post:** which family, which template, or no image. Driven by the
   content type and whether structured numbers exist.
4. Every generated graphic carries the headline + `created by @<your_handle> | Source: ... (retrieved on <date>)`
   line, using YOUR handle (this posts as you, not as Rahul).
