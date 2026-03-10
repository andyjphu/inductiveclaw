# How to Prompt This Codebase Faster

Lessons from building the iclaw landing page. Each row shows what was said, what went wrong, and what would have landed it in one shot.

---

## Sticky scroll-pinned sections

**What you said:** "put release text to the right of the scroll parallax following line"

**What happened:** Multiple rounds clarifying layout, then it still didn't pin correctly, then a separate "you aren't locking scrolling correctly, do a websearch" was needed.

**Say this instead:** "Make this a scroll-pinned section: outer container `h-[300vh]`, inner `sticky top-0 h-screen`. Content reveals as user scrolls through the tall outer container. Important: the parent `<main>` must use `overflow-clip` not `overflow-hidden` or sticky breaks."

---

## Italic text clipping with gradient fills

**What you said:** "keeps going text under the philosophy cut off"

**What happened:** Diagnosed as a scroll fade issue first. Two rounds before identifying it was `background-clip: text` + tight line-height on Instrument Serif italic clipping descenders.

**Say this instead:** "The italic text is visually clipped — descenders are cut off. This is the `background-clip: text` + tight `leading` bug with Instrument Serif. Add vertical padding to the gradient-filled italic span, or switch to `font-semibold` instead of italic for inline gradient text."

---

## Section ordering

**What you said:** "the statistic page should be put after the begin page (sorry meant section)"

**Say this instead:** "In `page.tsx`, move `<Stats />` below `<Install />`." — reference the component names and file directly.

---

## Color/style matching a reference

**What you said:** "take as much of the style of the website in web-design ref"

**What happened:** Colors, fonts, and CSS variables were all wrong. Required a follow-up "please refer to the root/v0-ref to copy exactly."

**Say this instead:** "Copy `globals.css` verbatim from `v0-ref/app/globals.css`. Match the exact font imports from `v0-ref/app/layout.tsx`. Only change text content, not styling."

---

## Navbar behavior

**What you said:** "make navbar go down with the user (glassmorphism the under of the navbar)"

**What happened:** First pass made it always-glassmorphic. Then needed: "navbar should be 100% transparent until scroll starts, and transition should ease into the current transparency."

**Say this instead:** "Fixed navbar, starts fully transparent (`bg-transparent backdrop-blur-0`). Between 0-200px scroll, ease into `bg-card/60 backdrop-blur-xl border-b border-border/30`. Use `useScroll` + `useTransform` for the transition, no sudden jump."

---

## Animation specifics

**What you said:** "statistics revealed in a hacker way like (A->#->0->?->0)"

This actually worked well because you gave a concrete visual example of the scramble sequence. More of this.

**Even better:** "Each character scrambles through random glyphs (`#@$%?!*&`) for ~18 frames at 60fps before resolving to the real character, left to right. Stagger each stat by 200ms. Trigger on intersection. Use `font-mono`."

---

## Tone/copy rewrites

**What you said:** "too AI sounding, rephrase, no em dash"

**What happened:** Multiple rounds. "Remove em dash" → done. "Still AI sounding" → another pass.

**Say this instead:** "Rewrite this copy. Rules: no em dashes, no 'revolutionize/transform/empower/seamlessly', no rhetorical questions, no tricolons (X, Y, and Z pattern). Tone: casual dev README, not marketing. Example of what I want: 'burns through your leftover tokens so you can sleep.'"

---

## Design direction

**What you said:** "the philosophy section could be made artsy, refer to noveau art"

This was good — naming a specific art movement gives a concrete direction. It still took one pass because the scope was large.

**Even better:** "Redesign the Philosophy section as Art Nouveau-inspired. Specifics: SVG path (flowing S-curve vine) that draws itself on scroll via `pathLength`. Steps alternate left/right along the vine. Each step has a large icon in a glowing orb. Decorative circles at curve inflection points. Keep the scroll-pin mechanic from before."

---

## General rules for faster prompts

1. **Name the component and file.** "In `stats.tsx`, change X" beats "the statistics page."
2. **Name the CSS/React pattern.** "Use `useTransform` with scroll progress" beats "make it animate on scroll."
3. **Give a visual example** when describing animation. `A → # → 0` was perfect.
4. **State the constraint with the fix.** "Italic clips because of `background-clip: text` — add `py-1`" beats "text is cut off."
5. **Say what NOT to change.** "Only change text content, keep all styles identical" prevents scope creep.
6. **Reference existing code.** "Same glassmorphic box style as the pip install button" beats describing the style from scratch.
