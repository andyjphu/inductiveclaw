This is an evaluation checkpoint. You must conduct a THOROUGH review before scoring.
Do NOT score from memory — you must re-examine the actual code and UI.

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

### 2d. Cross-Feature Integration
- Do features work together coherently?
- Is navigation between features intuitive?
- Consistent styling and interaction patterns across features?

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

## Documentation Health

- README: Does it exist? Does it describe what the app does, how to run it?
- Are there stale docs referencing removed features?
- Log any mistakes in a mistakes file.
