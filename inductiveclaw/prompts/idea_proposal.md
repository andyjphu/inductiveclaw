## Idea Transition

Your current idea has reached completion (score >= {threshold}, ready to ship).
Rather than adding more features to a finished thing, propose a NEW idea.

The new idea should COMPLEMENT or IMPROVE on what you just built. Think:
- A companion tool that solves a related problem
- A rewrite using a different approach or technology
- An extension that adds a major new capability (not just a feature)
- A testing/benchmarking harness for what you built
- A version for a different platform or audience

### How to propose

Call `propose_idea` with:
- **title**: Short name for the new idea (e.g., "mobile-companion", "perf-dashboard")
- **description**: 2-3 sentences explaining what it is and why it follows from the previous idea
- **relationship**: How it relates — "companion", "rewrite", "extension", "harness", "port"
- **carries_forward**: List of files/patterns from the current idea to reference (not copy)

### Rules
- The new idea gets its OWN workspace (git worktree). Start clean.
- You can READ files from previous ideas but don't modify them.
- Each idea should be independently useful — not a fragment.
- Don't propose something trivial. Each idea should be as ambitious as the original.
- If you genuinely can't think of a worthy follow-up, say so. That's better than
  a forced idea.

Previous ideas in this session:
{idea_history}
