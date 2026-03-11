<EXTREMELY_IMPORTANT>

## Visual Review Protocol — MANDATORY, NOT OPTIONAL

Screenshots are the ONLY way you can verify visual output. You are an LLM without
eyes — you cannot "imagine" what the UI looks like from reading code. Every time
you skip a screenshot, you are shipping blind.

</EXTREMELY_IMPORTANT>

Do NOT take a single screenshot and call it done. Systematic visual review:

### Step 1: Enumerate all views
List every distinct page, tab, modal, panel, and state the app has.
Example for an SVG editor: Editor view, Generator view, Code view, export modal,
color picker popover, layers panel expanded, layers panel with many items, etc.

### Step 2: Screenshot each view
For each view, take_screenshot with the appropriate URL/route. If views require
interaction to reach (clicking tabs, opening modals), use Bash to run a Playwright
script that navigates to that state before screenshotting.

### Step 3: Inspect each screenshot
Read each screenshot file and check:

**Layout integrity:**
- Are ALL form fields visible? Check every input, label, dropdown, slider.
- Any elements clipped by overflow: hidden or pushed off-screen?
- Proper spacing — nothing crammed or floating disconnected?
- Scroll areas work? Content doesn't disappear behind fixed headers/footers?

**Typography:**
- Text readable? No single-line text wrapping unexpectedly?
- Consistent font sizes for same-level headings?
- Sufficient contrast (especially placeholder text, disabled states)?

**Interactive elements:**
- Buttons look clickable? Clear hover/active states?
- Form inputs have visible borders/backgrounds?
- Selected/active states distinguishable from inactive?

**Responsive check (if applicable):**
- Screenshot at 1280px AND 768px widths
- Does the layout adapt or just clip/overflow?

### Step 4: State variations
For key interactive features, screenshot multiple states:
- Empty state (no data, no selection)
- Populated state (typical usage)
- Error state (invalid input, failed operation)
- Loading state (if async operations exist)

### Step 5: Fix before scoring
If ANY visual issue is found, fix it BEFORE calling self_evaluate.
Visual bugs found during review that aren't fixed should fail the eval.

### Anti-Rationalization

| Your excuse for skipping screenshots | Why it's wrong |
|---|---|
| "I already know what it looks like" | You're an LLM. You literally cannot see. Take the screenshot. |
| "The code is correct so the UI must be fine" | CSS bugs, z-index issues, overflow clipping — code review can't catch these. |
| "It's just a small change" | Small CSS changes cause big visual regressions. Screenshot. |
| "Screenshots take too long" | A 5-second screenshot saves a 30-minute debugging session. |
| "I'll screenshot at the eval" | Visual bugs compound. Catch them when you make them, not 5 features later. |
