GOAL: {goal}
This is iteration {iteration}.
{context}

## Your Task

1. Read BACKLOG.md and MISTAKES.md to understand current state, priorities, and
   what NOT to repeat.
2. Pick the highest-impact next item. Build it. Run it. Fix errors.
3. **Don't stop at one item.** Keep building until the turn limit stops you.
4. After the original goal is solid, expand: build complementary features that
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
3. **Update README.md** — current features, how to run
4. **Update MISTAKES.md** — any failed approaches this iteration
5. **Update BACKLOG.md** — completed items, next priorities, architectural notes
   that a future iteration (or context-compacted continuation) would need
6. **Update docs/** — save any research, API references, architecture decisions,
   or useful web search results. A future iteration should be able to pick up
   from docs/ without re-searching anything.

### Rules

- Do NOT re-plan the entire project. Focus forward.
- Do NOT revisit completed work unless it's broken.
- Do NOT stop after one feature. Build as many as the turn limit allows.
- Do NOT think "this is good enough." There is always more to build.
