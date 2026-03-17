## Browser-Based Product Evaluation — MANDATORY

Before calling `self_evaluate`, you MUST run `browser_evaluate` to get an objective
assessment of the running application. This is not optional — it replaces guessing
with measurement.

### What browser_evaluate does

- Discovers all routes and pages in the app
- Clicks every button, fills every form, presses common keyboard shortcuts
- Monitors console errors and network failures
- Detects keybinding conflicts (same key bound to multiple actions)
- Captures screenshots of each discovered state

### How to use it

Call `browser_evaluate` with no arguments (defaults are fine). If you haven't started
the dev server, the tool will start it automatically.

### Hard score gates (MANDATORY)

The browser eval report contains objective findings. These OVERRIDE your subjective
assessment when scoring:

| Finding                        | Score cap                          |
|--------------------------------|------------------------------------|
| Any console errors             | functionality_score capped at 6    |
| Any keybinding conflicts       | functionality_score capped at 5    |
| Network errors (failed fetches)| functionality_score capped at 6    |
| >25% broken interactions       | functionality_score capped at 4    |
| Health score < 5               | overall_score capped at 5          |

### What to do with the results

1. Read the full browser eval report at `.iclaw/browser-eval/latest.md`
2. Fix ALL console errors before scoring
3. Fix ALL keybinding conflicts before scoring
4. Fix network errors if they affect user-facing features
5. If health_score < 7, fix the top issues and re-run `browser_evaluate`
6. Only THEN call `self_evaluate` — reference the browser eval findings in your critique
