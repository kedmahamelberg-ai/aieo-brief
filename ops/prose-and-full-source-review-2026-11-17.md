# W46 prose and complete-source review

Owner request: remove repeated attribution and irrelevant defensive caveats; use complete sources and replace inaccessible articles.

Reviewed all 67 selected news stories and 24 research records dated November 9–15. Explicit edits are registered in `data/editorial/prose-review-2026-11-17.json`. Most changes shorten repeated framing while preserving approved facts, uncertainty, and effect labels. The Montpellier event no longer comments on the absence of meeting outcomes or a date in supplied text. Meaningful limitations remain, including unproven allegations, study populations and legal status.

Recovered the complete published video subtitles for the Xinhua Shenzhen/Dongguan report (130.64 seconds), Qiushi's Zhou Bowen interview (618.24 seconds), and Xinhua's World Media Summit interviews (319.08 seconds). Read subtitles across each full video with local macOS Vision extraction, then wrote source-based summaries. These are editorial corrections, not passed model-review outputs. Source video and subtitle hashes are recorded; copyrighted transcripts are not committed.

Le Temps remains subscriber-only. Per the owner's replacement instruction, its chart-only reading is replaced by Kevin Webb's complete November 9 Kiplinger column about AI earnings and financing. The existing AI-finance URL is retained with an explicit replacement note, new attribution and source date. Both implication labels now reflect the replacement's risks. Original source URLs remain in the audit. The verifier's existing registered-override handling follows these new labels.

Recovered WeightBench (arXiv 2611.18553v1) as complete HTML, including methods, results and appendices. Replaced its source-only record with a 178-word full-paper reading and version-bound evidence metadata. This is additional to the previously completed 18 selected W46 papers; date-window and selected-week counts differ.

Future writing and existing final-review instructions now favor direct prose, necessary attribution and one meaningful caveat instead of repeated source framing. Chart captions cannot serve as full-article supplements. Partial-source metadata remains disqualifying even for long text; supplement quality checks now retain its recorded content basis. Existing full-paper publication gates remain in place. No model/version bump or forced regeneration.

Validation: 394 Python tests with AIEO_AI_PROVIDER=local; 27 JavaScript tests. Publication rehearsal used downloaded live news cards, current public Observatory input and repository research/culture/archive data, with database reads replaced and model translation disabled. All 67 news and 24 date-window research items remain complete. The site validator checked 6,200 pages and 276,081 local destinations. Two pre-existing translation-pending archive papers from September/October remain unchanged.

Merge uses `[no-cost-build]` to disable model translation. No manual generation, research, collection or import workflow is dispatched. Social completion already marks W47 finished, so the existing social/email completion gate skips it. Stable URLs, community identities and signed weekly reviews are preserved.
