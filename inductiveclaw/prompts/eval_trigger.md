This is an evaluation checkpoint. Use self_evaluate to score the current state.
Be critical — grade what exists, not what you plan to build.

## Evaluation Rubric

Score each dimension 1-10, then compute the overall score:

### Functionality (weight: 30%)
- Does the core feature work end-to-end without errors?
- Are edge cases handled (empty input, invalid data, network failures)?
- Can a new user pick it up and use it without reading source code?

### Code Quality (weight: 20%)
- Clean architecture, consistent style, no dead code or TODOs left behind?
- Files small and focused? No module over 300 lines?
- Dependencies minimal and appropriate?

### Polish & UX (weight: 25%)
- Does it feel finished? No placeholder text, no broken layouts, no raw error dumps?
- Keyboard shortcuts, loading states, responsive design, error messages — present?
- Would a user say "this is nice" or "this is a demo"?

### Completeness (weight: 25%)
- Are there obvious features a user would expect that are missing?
- Would a developer on GitHub star this, or close the tab?
- Does the README explain what it does, how to run it, and show a screenshot?

## After Scoring

- If overall score < 7: identify the SINGLE lowest-scoring dimension and focus
  your next iteration on raising it. Don't spread effort across everything.
- If overall score >= 7 but < 9: look for quick wins that raise multiple
  dimensions (e.g., error handling improves both Functionality and Polish).
- If overall score >= 9: focus on completeness — what would make someone share
  this project with a friend?

## Documentation Health Check

- Are docs accurate? Do they describe the code as it actually is right now?
- Are there stale docs referencing removed features or old architecture? Archive them.
- Log any mistakes you made (wrong assumptions, failed approaches) in a mistakes file.
- Update README and architecture docs if they've drifted from the current state.
