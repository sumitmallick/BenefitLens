# AI Artifacts

## Session logs

This directory contains the raw session logs from Claude Code (the AI coding agent used to build this system).

The JSONL session logs are the primary Claude Code session files for this project. They are located at the Claude Code session path on the development machine.

**Where to find the JSONL logs:**

Claude Code session logs are stored at:
```
~/.claude/projects/<project-path>/
```

For this project (working directory `/Users/sumitkumarmallick/Project/Realfast`):
```
~/.claude/projects/-Users-sumitkumarmallick-Project-Realfast/
```

The JSONL files in that directory contain the full conversation transcript including:
- Every prompt sent to Claude Code
- Every tool call made (file reads, writes, bash commands)
- Iteration and revision history
- The conversation where I pushed back on Claude's suggestions (see below)

The `.jsonl` files are not committed to this repository because they are large and contain the full conversation context. They are available on request.

## Notable AI collaboration moments

### What AI got right
- Suggested `excluded_diagnosis_codes` on CoverageRule (I had missed this)
- Proposed the `derive_claim_status_from_line_items` helper function
- Generated the SQLAlchemy ORM model structure quickly

### What I caught and corrected
1. **`@dataclass_workaround = None`** — Claude Code generated an invalid Python statement in `adjudicator.py`. I caught it immediately and removed it. The commit history shows this correction.

2. **COVERED vs PARTIALLY_COVERED distinction** — Claude initially compared `covered_amount == billed_amount` for COVERED status, which fails when per-visit limits cap the payable below billed but still full coverage percentage is applied. I rewrote the status determination logic.

3. **Mutable deductible in pure function** — Claude Code wrote the adjudicator modifying `policy.deductible_met` in place, which violates the "pure function" intent. I accepted this trade-off for the demo but documented it explicitly in self-review.md as a design smell.

### Prompting approach
- Wrote domain model tests first, asked Claude to help implement to make them pass
- Used Claude for boilerplate (SQLAlchemy models, Pydantic schemas) while writing the adjudicator logic myself
- Iterated on the adjudication decision sequence — started with 7 steps, added "excluded diagnosis" check after thinking through real-world scenarios
- Pushed back on Claude's suggestion to use a rules engine DSL (too complex for 48-hour scope; flat data is sufficient)

## Chat export

The full conversation transcript (available separately) shows the iteration:
- Initial domain modeling discussion
- Adjudicator design (where I rejected the rules engine suggestion)
- Infrastructure discussion (sync vs async adjudication trade-off)
- Test strategy (why real DB vs mocks for integration tests)
