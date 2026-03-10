# Landing Page (`web/`)

Next.js 16 app in the `web/` git submodule. Dark theme, scroll-driven animations, glassmorphic UI.

## Stack

- **Framework:** Next.js 16.1.6 (App Router, Turbopack)
- **Styling:** Tailwind CSS v4, `tw-animate-css`
- **Animation:** Framer Motion (`useScroll`, `useTransform`, `motion`)
- **Fonts:** Instrument Serif (display), Inter (body), JetBrains Mono (mono) via `next/font/google`
- **Colors:** oklch dark theme with four accent colors: coral, amber, cyan, sage

## Section Order

```
page.tsx
  GrainOverlay   — full-screen SVG noise texture at 8% opacity
  Hero           — background image, character-stagger title, glassmorphic sticky navbar
  Manifesto      — scroll-pinned Art Nouveau section, SVG vine draws on scroll, 4 steps
  Terminal       — animated terminal showing real iclaw interactive + autonomous workflow
  Install        — pip install + iclaw copy-to-clipboard boxes, parallax orbs
  Stats          — 3 joke stats with hacker scramble reveal animation
  Footer         — links, copyright, giant ghost text
```

## Key Components

### `hero.tsx`
- Fixed navbar: fully transparent at top, eases into glassmorphism over 0-200px scroll
- Background: `creation-of-claw.jpg` with blur + radial gradient vignette
- Section label: "The Vision" (coral)
- Title: "Build / Until / It's Right" with per-character stagger wave animation (`SplitText` component, `rotateX` flip, 40ms stagger per character)
- Subtitle uses `font-semibold` (not italic) for inline gradient text to avoid `background-clip: text` clipping
- Parallax: background orbs move at different scroll rates (`orbY1`, `orbY2`)
- Scroll indicator fades out within first 100px of scroll
- Hero height: `85vh` (not full `100vh`) to reduce gap to next section

### `manifesto.tsx`
- Section label: "The Philosophy" (amber)
- Scroll-pinned: `h-[300vh]` outer, `sticky top-0 h-screen` inner
- **Desktop:** SVG S-curve vine draws itself via `pathLength` + `useTransform`. 4 steps alternate left/right with icon orbs, decorative circles at curve inflection points. Steps positioned at 8% + index*20% from top.
- **Mobile:** SVG vine hidden. Steps render as compact vertical list (`MobileSteps` component) with smaller icons (48px), fade-in on scroll.

### `terminal-experience.tsx`
- Section label: "The Experience" (cyan)
- Full INDUCTIVECLAW ASCII art banner using Unicode block characters (░▒▓█▌▐). Each character wrapped in `inline-block width:1ch` spans for consistent monospace alignment. Font stack: Menlo → Consolas → DejaVu Sans Mono → Monaco → Courier New. Hidden on mobile.
- Shows interactive mode flow: `$ iclaw` → banner → provider status → `❯` prompt → user request → Claude Code iconography (`✻`, `⎿`) → autonomous iteration loop → self_evaluate → quality threshold reached
- Variable-speed line reveal: thinking 800ms, prompt 600ms, command 400ms, ascii 40ms, spacer 60ms, complete 500ms, default 120ms
- Scroll-driven: fade-in only, scale-up only (no reverse animations — prevents flicker)
- Mobile: ASCII art hidden, smaller text (`text-xs`), reduced min-height (350px)

### `stats.tsx`
- 3 joke statistics: "0" usage data, "1M+" tokens, "3" fake statistics
- Enhanced hacker scramble reveal: 30-frame animation, 12 frames of pure random chaos, then left-to-right character resolution
- `font-mono`, staggered 200ms per stat, triggered by IntersectionObserver at 40% threshold
- Mobile: smaller numbers (`text-5xl` vs `text-6xl`), tighter gap

### `install.tsx`
- Section label: "The Setup" (sage)
- Two copy-to-clipboard boxes: `pip install iclaw` and `iclaw`
- Glassmorphic style with gradient dividers and lucide copy/check icons
- Parallax ambient orbs moving at different scroll rates
- Mobile: smaller button text (`text-sm sm:text-lg md:text-2xl`)

### `grain-overlay.tsx`
- Full-screen SVG `feTurbulence` noise texture
- Fixed position, `z-[100]`, `pointer-events-none`, 8% opacity
- Adds film grain texture to the dark theme

### `footer.tsx`
- GitHub + PyPI links
- PHT Labs © 2026 copyright with link
- "Wraps the Claude Agent SDK" tagline (removed — see user edits)
- Giant ghost "inductiveclaw" text with gradient fill, `overflow-clip` (not `overflow-hidden` to prevent rubber-band scroll)
- Mobile: smaller logo (`text-2xl`), tighter nav gap

## Metadata

- **Title:** `iclaw`
- **Description:** `Ship while you sleep.`

## What We Implemented

1. **Character stagger wave** on hero title — per-character `rotateX` flip with cascading delay
2. **Parallax depth** on background orbs — hero and install sections, orbs move at different scroll rates
3. **Film grain overlay** — SVG noise texture at 8% opacity, fixed full-screen
4. **Enhanced stats scramble** — 30-frame animation with 12 frames of chaos before resolving
5. **Variable-speed terminal reveal** — different delays per line type simulating real thinking
6. **Full INDUCTIVECLAW ASCII banner** in terminal — Unicode block chars with `1ch` fixed-width spans
7. **Mobile responsive layout** — manifesto collapses to vertical list, ASCII art hidden, text/spacing scaled down
8. **Section header color gradient** — coral → amber → cyan → sage following the 4-color palette
9. **Scroll indicator fade** — disappears within 100px of scrolling
10. **Hero height reduction** — 85vh instead of 100vh for less dead scroll space

## What We Tried and Removed

1. **Custom cursor** (dot + ring with `mix-blend-difference`) — caused visible input lag even with raw DOM positioning. Removed entirely.
2. **Magnetic hover buttons** (`Magnetic` component) — pip install boxes pulled toward cursor. Felt gimmicky with the glassmorphic style, removed.
3. **Terminal 3D tilt on hover** — perspective transform tracking cursor position. Caused input lag on the terminal content, removed.
4. **Progress bar** on manifesto section — intersected with the SVG vine visually, removed.

## Known Gotchas

- `overflow-clip` on `<main>` and footer ghost text wrapper, not `overflow-hidden` — the latter breaks `position: sticky` and creates rubber-band scroll containers on mobile.
- Instrument Serif italic + `background-clip: text` clips descenders. Use `py-1` on block spans or `font-semibold` for inline gradient text.
- Terminal scroll animations must be unidirectional (fade/scale in only). Bidirectional animations flicker when layout shifts (e.g. cursor element toggling) nudge `scrollYProgress`.
- Unicode block characters (░▒▓█▌▐) have inconsistent widths in browser monospace fonts. Fixed by wrapping each character in `display: inline-block; width: 1ch`. System terminal fonts (Menlo, Consolas) work best.
- SVG `feTurbulence` grain at 3% opacity is invisible on dark backgrounds. 8% is the minimum visible threshold.

## Color Palette

```
coral:  oklch(0.75 0.18 25)   — primary accent, hero section header
amber:  oklch(0.80 0.16 75)   — second accent, philosophy section header
cyan:   oklch(0.78 0.12 200)  — third accent, experience section header
sage:   oklch(0.70 0.10 145)  — fourth accent, setup section header, success states
```

Section header colors follow the full gradient progression: coral → amber → cyan → sage.
