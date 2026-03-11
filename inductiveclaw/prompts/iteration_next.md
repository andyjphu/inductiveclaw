GOAL: {goal}
This is iteration {iteration}.
{context}

## Your Task

<HARD_GATE>

### Re-Orient From Scratch

You are starting a new iteration. Do NOT trust your assumptions about project
state. The codebase may have changed since your last context. Before building:

1. Read BACKLOG.md and MISTAKES.md to understand current state and what NOT to repeat.
2. Glob for the current file structure — verify it matches your expectations.
3. Run the project and verify it works in its current state BEFORE adding anything.

Only after confirming current state should you pick the next task.

</HARD_GATE>

4. Pick the highest-impact next item. Build it. Run it. Fix errors.
5. **Don't stop at one item.** Keep building until the turn limit stops you.
6. After the original goal is solid, expand: build complementary features that
   make the project more complete, even if the user didn't request them.
   A CRM needs reports. A game needs settings. A tool needs keyboard shortcuts.

### Research First — The 10-Inspiration Rule

Before building, use WebSearch to find at least 10 inspirations for what you're
building. Not 2, not 3 — ten. This forces you to look beyond the obvious.

```
WebSearch("top 10 best [project type] apps 2025 features")
WebSearch("award winning [project type] UI design inspiration")
WebSearch("[project type] features users wish existed reddit")
WebSearch("how to make [project type] feel premium polished")
```

Save findings to `docs/research/inspirations.md` with what each one does well
and what ideas you're taking from it.

Think long-term: what features will make this project amazing 10 iterations
from now? Research those NOW and save to `docs/roadmap.md` so future iterations
have a clear forward path.

Cache EVERY useful finding in `docs/research/` — your context window will be
compacted and anything not saved to a file will be permanently lost.

### Housekeeping (every 3-4 features)

Do ALL of these, then immediately continue building:
1. **Checkpoint** — list what you built, quality score, what's next
2. **Archive snapshot** — copy working files into `{name}{major}.{minor}/` with
   a `run.sh`. Bump minor each checkpoint, major for new capability sets.
3. **Update FOR-HUMAN.md** — plain list of every feature added with a one-liner
   description. No markdown formatting beyond a flat list. This is for the human
   to scan quickly. Append new features, never remove old ones.
4. **Update README.md** — current features, how to run
5. **Update MISTAKES.md** — any failed approaches this iteration
6. **Update BACKLOG.md** — completed items, next priorities, architectural notes
   that a future iteration (or context-compacted continuation) would need
7. **Update docs/** — save any research, API references, architecture decisions,
   or useful web search results. A future iteration should be able to pick up
   from docs/ without re-searching anything.

### Rules

- Do NOT re-plan the entire project. Focus forward.
- Do NOT revisit completed work unless it's broken.
- Do NOT stop after one feature. Build as many as the turn limit allows.
- Do NOT think "this is good enough." There is always more to build.

### <EXTREMELY_IMPORTANT> Verification Before Progress Claims </EXTREMELY_IMPORTANT>

Before claiming ANY feature is complete, you MUST:
1. Identify the proof command (run, test, screenshot)
2. Execute it
3. Read the FULL output
4. Confirm the output demonstrates the claim

"I built X" without "I verified X by [running/screenshotting] and confirmed [result]"
is not a progress claim — it's a guess. Unverified work counts as zero progress.
