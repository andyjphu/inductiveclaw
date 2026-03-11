<EXTREMELY_IMPORTANT>

This is an evaluation checkpoint. You must conduct a THOROUGH review before scoring.
Do NOT score from memory — you must re-examine the actual code and UI.

## Distrust Your Own Work

Assume the builder (you, in previous turns) cut corners, missed edge cases, and
is overconfident about quality. The builder finished "suspiciously quickly." Their
progress reports may be incomplete, inaccurate, or optimistic.

You MUST verify everything independently. DO NOT:
- Take your previous claims about what works at face value
- Trust your memory of what features exist or how they look
- Accept your own interpretation of "done" without fresh evidence
- Score based on what you INTENDED to build rather than what EXISTS

DO:
- Read the actual code and run it fresh
- Compare actual implementation to the goal line by line
- Screenshot every page and READ the screenshots
- Test every interactive element yourself

## Banned Language

Until you have FRESH EVIDENCE (screenshots read, tests run, code executed), you
may NOT use any of these words in your evaluation:
- "should" / "should be" / "should work"
- "probably" / "likely" / "presumably"
- "seems to" / "appears to"
- "I believe" / "I think" / "I expect"

Replace every "should work" with "I verified by [action] and confirmed [result]."
Expressing confidence without evidence is not evaluation — it's guessing.

</EXTREMELY_IMPORTANT>

## Phase 1: Feature Inventory

List EVERY user-facing feature and page/view in the project. For each one, note:
- What it does
- Whether you've verified it works (run it, click it, test edge cases)
- Any input fields, buttons, or interactive elements it contains

Do NOT skip features you "already tested." Re-verify now.

## Phase 2: Per-Feature Deep Review

For EACH feature from Phase 1, do ALL of the following:

### 2a. Functional Testing
Run the feature. Try:
- Normal use case (happy path)
- Empty/blank input
- Extremely long input
- Special characters, unicode
- Rapid repeated actions (double-click, spam submit)
- Browser back/forward if applicable

If it's a form or tool with multiple fields: verify EVERY field works. Check that
labels, inputs, and values all render correctly. The SVG editor's H field being
invisible is exactly the kind of bug this catches.

### 2b. Visual Inspection (if applicable)
Take a screenshot. Then Read the screenshot and examine:
- Is every UI element fully visible? No clipping, no overflow, no missing fields?
- Text readable at all sizes? Truncation handled gracefully?
- Consistent spacing and alignment across all sections?
- Colors/contrast meet accessibility guidelines (4.5:1 for text)?
- Does it look intentionally designed or like a default/template?

For multi-page apps: screenshot EACH page/view separately.
For interactive elements: screenshot different states (empty, filled, error, loading).

### 2c. Completeness Check
For each feature, ask: "If I told a friend about this app, would they find this
feature complete or half-baked?"
- Missing obvious sub-features? (e.g., an SVG generator with no AI generation)
- Missing keyboard shortcuts a power user would expect?
- Missing undo/redo where applicable?
- Missing export/save/share where applicable?
- Missing error states and recovery?

### 2d. Cross-Feature Integration (THE COLLISION TEST)

Features built across many turns accumulate hidden conflicts. The builder added
each feature in isolation and likely never tested them TOGETHER. This is where
the worst bugs live.

<HARD_GATE>

**You MUST use `smoke_test` to verify cross-feature interactions.** Reading code
is not enough — you need to actually run the app and exercise features together.

Write smoke tests that cover:

**1. Input binding collisions:**
```
# Example: space shooter game — verify spacebar doesn't restart during gameplay
smoke_test(test_name="spacebar_collision", script="""
# Start the game
click:#start-button
wait:500
# Press space to shoot (should fire, not restart)
press:Space
wait:100
assert_eval:document.querySelector('#game').dataset.state === 'playing'
# Now die / reach game over somehow
assert_eval:typeof window.playerScore === 'number'
assert_no_errors
""")
```

For EVERY key binding in the app, test it in EVERY state. If the app has states
(menu, playing, paused, game-over), press every bound key in every state and
assert the correct behavior.

**2. State transitions:**
```
# Example: verify game over screen doesn't leak gameplay handlers
smoke_test(test_name="state_transitions", script="""
click:#start-button
wait:500
# Navigate to game over (however the app does it)
press:Escape
wait:100
# Verify we're in the right state
assert_visible:#game-over-screen
assert_not_visible:#gameplay-hud
# Verify no console errors from orphaned handlers
assert_no_errors
""")
```

**3. Full user journey:**
Write a smoke test that simulates 60+ seconds of real usage — navigating
between features, using keyboard shortcuts mid-interaction, switching modes,
and verifying the app stays coherent throughout.

</HARD_GATE>

**Code-level audit (in addition to smoke tests):**
- Grep for ALL `addEventListener`, `on(`, `keydown`, `keyup`, `keypress`
- Check: are handlers properly scoped to the current state?
- Check: are handlers removed or guarded on state transitions?
- Check: do features share global variables, timers, or animation frames?

**The "play the game" test:**
- Use the app like a real user would for 2+ minutes of continuous interaction.
- Don't test features in isolation — use them in sequence and combination.
- Try the "impatient user" pattern: click rapidly, switch between features
  mid-action, use keyboard shortcuts while clicking, resize the window.

If you find ANY collision or conflict, it is a CRITICAL bug. Fix it before scoring.
Cross-feature bugs are invisible in per-feature testing — this is the only phase
that catches them.

## Phase 3: Goal Alignment

Re-read the original goal. Ask:
- What would a reasonable person EXPECT when they read this goal?
- "Build an SVG generator" → they expect AI text-to-SVG, not just a manual editor
- "Build a timer" → they expect at least countdown + stopwatch
- "Build a color tool" → they expect picker + palette + contrast checker
- Are ALL plausible interpretations of the goal addressed?
- What features would make someone SHARE this with others?

## Phase 4: Score

ONLY after completing Phases 1-3, call self_evaluate with honest scores.

### Functionality (weight: 30%)
- 1-3: Core features broken or missing
- 4-6: Core works but edge cases fail, some features incomplete
- 7-8: All features work, edge cases handled, minor issues only
- 9-10: Bulletproof — handles everything thrown at it

### Code Quality (weight: 20%)
- 1-3: Spaghetti, inconsistent, dead code everywhere
- 4-6: Functional but messy, some organization
- 7-8: Clean, well-organized, consistent patterns
- 9-10: Exemplary — someone would learn from reading this code

### Polish & UX (weight: 25%)
- 1-3: Looks like a homework assignment, placeholder text, broken layouts
- 4-6: Functional but generic, missing loading/error/empty states
- 7-8: Feels designed, good attention to detail, responsive
- 9-10: Delightful — animations, transitions, keyboard shortcuts, accessibility

### Completeness (weight: 25%)
- 1-3: Only the most basic interpretation of the goal, missing obvious features
- 4-6: Core goal met but a user would immediately ask "why can't I...?"
- 7-8: All reasonable interpretations addressed, few gaps
- 9-10: Exceeds expectations — features the user didn't ask for but loves

## After Scoring

- If overall < 7: your top_improvement must be a SPECIFIC bug or missing feature
  you found in Phase 2, not a vague "improve UX." Example: "H field in Position
  panel is clipped/invisible — fix CSS grid layout."
- If overall >= 7 < 9: list the 3 most impactful specific improvements.
- If overall >= 9: focus on the one thing that would make someone share this.

<HARD_GATE>

## Evidence Requirement for High Scores

- **Score >= 7 requires:** At least one screenshot READ and examined per page/view,
  plus successful test execution output for core features.
- **Score >= 8 requires:** Screenshots of EVERY page/view/state, all edge cases
  tested, responsive check at multiple widths.
- **Score >= 9 requires:** Everything above, PLUS cross-feature integration tested,
  performance verified, accessibility checked, and zero known unfixed bugs.

If you cannot provide this evidence, your score MUST be lower. A high score
without evidence is dishonesty, not optimism.

</HARD_GATE>

## Documentation Health

- README: Does it exist? Does it describe what the app does, how to run it?
- Are there stale docs referencing removed features?
- Log any mistakes in a mistakes file.
