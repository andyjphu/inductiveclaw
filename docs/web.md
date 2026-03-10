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
  Hero           — background image, tagline, glassmorphic sticky navbar
  Manifesto      — scroll-pinned Art Nouveau section, SVG vine draws on scroll, 4 steps
  Terminal       — animated terminal showing real iclaw workflow
  Install        — pip install + iclaw copy-to-clipboard boxes
  Stats          — 3 joke stats with hacker scramble reveal animation
  Footer         — links, giant ghost text
```

## Key Components

### `hero.tsx`
- Fixed navbar: fully transparent at top, eases into glassmorphism over 0-200px scroll
- Background: `creation-of-claw.jpg` with blur + radial gradient vignette
- Title: "Builds / Until / It's Right"
- Subtitle uses `font-semibold` (not italic) for inline gradient text to avoid `background-clip: text` clipping

### `manifesto.tsx`
- Scroll-pinned: `h-[300vh]` outer, `sticky top-0 h-screen` inner
- SVG S-curve vine draws itself via `pathLength` + `useTransform`
- 4 steps alternate left/right: Run iclaw → Walk away → It keeps going → Come back to output
- Each step: lucide icon in radial-gradient orb, serif title, description
- Decorative circles at curve inflection points

### `terminal-experience.tsx`
- Typewriter-style line reveal (120ms per line) triggered by IntersectionObserver
- Shows: pip install, iclaw run with goal, OAuth auth, iterations, self_evaluate scores, threshold reached
- Scroll-driven opacity: fade in only (no fade out — prevents flicker from layout shifts)

### `stats.tsx`
- 3 joke statistics: "0" usage data, "1M+" tokens, "3" fake statistics
- Hacker scramble reveal: each character cycles through random glyphs before resolving
- `font-mono` for the numbers, staggered 200ms per stat

### `install.tsx`
- Two copy-to-clipboard boxes: `pip install iclaw` and `iclaw`
- Glassmorphic style with gradient dividers and lucide copy/check icons

### `footer.tsx`
- GitHub + PyPI links
- "Wraps the Claude Agent SDK" tagline
- Giant ghost "inductiveclaw" text with gradient fill

## Known Gotchas

- `overflow-clip` on `<main>`, not `overflow-hidden` — the latter breaks `position: sticky`
- Instrument Serif italic + `background-clip: text` clips descenders. Use `py-1` on block spans or `font-semibold` for inline gradient text.
- Terminal scroll opacity must be unidirectional (0→1 only). Bidirectional (0→1→0) flickers when layout shifts nudge `scrollYProgress`.

## Color Palette

```
coral:  oklch(0.75 0.18 25)   — primary accent, section headers start here
amber:  oklch(0.80 0.16 75)   — second accent
cyan:   oklch(0.78 0.12 200)  — third accent
sage:   oklch(0.70 0.10 145)  — success/completion
```

Section header colors follow the gradient progression: coral → amber → cyan.
