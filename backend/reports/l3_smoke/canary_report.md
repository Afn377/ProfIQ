# Canary detection report

_scan_time:_ `2026-04-18T23:45:15.338674+00:00`
_layers:_ `l3`

## Layer 3 — fake-institution check

- checked: **25** distinct institutions, queried: **25**, errors: **0**, in 8.73s
- flagged institutions: **0**, affected professors (collateral cleanup candidates): **0**

_Every checked institution had a plausible OpenAlex match above the fuzzy threshold._

---
Layer 1 catches obvious / legacy canaries only. Layer 2's flagged rows are *suspicious*, not confirmed — adjuncts, retired faculty, and lecturers who never published often look like orphans too. Layer 3 is much higher-confidence: a school with a real catalog of programs will be in OpenAlex's institutions index, so anything missing is either a fake-school canary, a typo, or an org so obscure (private training school, unlisted clinic) that pruning it costs little even if it's real.
