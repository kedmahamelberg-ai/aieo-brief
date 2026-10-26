# Source-grounded editorial publication

The 26 October 2026 audit confirmed errors in 22 news items and seven research items, in addition to the previously corrected France Travail provenance. The approved field-level replacements and previous wording are recorded in `data/editorial/approved-corrections-2026-10-26.json`. Pending cases are explicitly locked and unchanged. The CIIS item changes the institute name only; report verification remains pending.

## Failure mechanisms found

The writer had to produce limitations, implications and examples even from thin evidence. Its private support covered only the headline, development and significance. Exact-quote matching checked that a passage existed, not that it entailed the draft. A six-Boolean review did not require evidence for each public field, and could read lossy segment summaries. Numeric validation checked digit presence without associating a number with its group, comparator or metric. Source completeness heuristics could accept navigation or captions. These mechanisms are consistent with the observed errors; retained outputs alone cannot prove the model's internal cause.

## Gates now applied

- Writer instructions allow sparse prose and omit unsupported dimensions/caveats. They prohibit invented balance, critics and applications.
- After all readability edits, a separate review call receives the original sources and each public field, including every body paragraph, deck and limitation. It must evaluate every factual clause and return supported/unsupported/uncertain plus exact citations.
- Local validation rejects missing, duplicate or unknown fields, uncertain verdicts, absent citations and quotations not literally present in their named source. Verified metadata is separately identified as source zero and cannot substantiate article claims.
- Additional checks cover source sufficiency, provenance, organizations/campuses/roles, planned versus completed events, denominators, comparators, metrics, examples and limitations. Internal limitation/placeholder markers are blocked deterministically.
- Review uses medium reasoning on the configured OpenAI model. GPT-5 nano does not support temperature, so API payloads omit it. Local-model temperature remains 0.15 on every attempt instead of increasing on retries. Temperature is not the factuality gate.
- The new engine version is part of news input fingerprints and research reuse requirements. Failed candidates cannot replace published content; budget or context failures stop the attempt without silently truncating evidence.
- Approved corrections and pending cases cannot be automatically regenerated, including forced news runs. Approved field overlays are also applied during site rendering, including archive pages. To revise a locked item, review its evidence and change the explicit manifest/lock first.
- Eight live-model minimal pairs (16 checks) cover provenance, campus, future events, survey subgroups, invented warnings, error metrics, learning speed and comparator swaps. A failed suite blocks automatic OpenAI generation. `Evaluate Editorial Grounding` can run it separately without database writes or publication. Existing job spending limits remain enforced.

## Validation and limits

Run `AIEO_AI_PROVIDER=local python -m unittest discover -s tests -p 'test_*.py'` for deterministic regression and integration tests. Run `python scripts/evaluate_grounding.py` with configured API access for the semantic minimal pairs. Fixtures are synthetic adaptations of audit patterns, not publisher article copies. Private citations and failed-review feedback stay out of the public website.

A model reviewer can still mistakenly approve a claim supported only by a related quote. Exact citations and finite regression fixtures do not prove entailment or establish an error rate for all articles. These gates reduce risk and withhold doubtful drafts; source audits and human review remain necessary for ambiguous cases. Previously published articles outside the approved correction manifest are not silently removed or rewritten by this deployment.
