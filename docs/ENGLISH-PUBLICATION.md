# English publication

The source collection remains multilingual. Public news, research and cultural text gets an English display layer. Identifiers, source URLs, edition dates, directions, human review history and original evidence are not translated or reclassified.

New editorial drafts must use English in every public field. Exact private support quotes remain in the original language so evidence-matching checks continue to work. Existing non-English summaries and source titles pass through a display translator. Proper Latin-script author and publisher names retain their customary spelling. Non-Latin names are transliterated. Original linked webpages, images and audio remain the originals; the Brief does not dub recordings or edit source websites.

The source-language detector supports a finite set of languages; automatic detection, translation and model review can make mistakes. The tested logic covers language-agnostic field routing, cache invalidation, preservation and fail-closed notices, not validated accuracy for every language. Review a sample of live English translations against the originals after the first run. Literary translation is explicitly labelled as automatically prepared for the Brief, rather than presented as the author's exact English wording.

The existing model runtime and schedule are retained. The Build and Publish workflow now has access to OPENAI_API_KEY and a dedicated translation ledger. The existing AIEO_AI_MAX_JOB_USD value is used, default US$0.50 per build. This is not a monthly cap. Separate jobs and manual reruns have separate limits. The translation phase stops when its ten-minute time budget or the runtime spending/request limit is reached. Cached translations avoid repeating the same paid work on later builds.

`data/english/public-text.json` holds English output, model identification and checks, not complete original article bodies. Source changes create a different cache key. Current-edition news is processed before older archive content. A failed or unfinished translation displays an English pending notice, rather than leaking untranslated prose or inventing a completed summary. The original record is preserved in the existing archive/source system. It may take additional builds to clear a backlog. Build success does not mean every item finished translation; inspect `english_publication.pending_items` in the build summary.

`_site/data/public-items.json` contains the English public items used to register community item titles and versioned public-content snapshots in Supabase. It does not contain source-body evidence or private engagement history. Internal research and product events reference content hashes without exposing reader identities.

## First live checks

After installing and pushing, wait for a NEW Build and Publish AIEO Brief run on main. In its summary, inspect translated, cached and pending item counts, and the AI usage report. Confirm examples from Chinese and French news plus Portuguese culture. Open the privacy dialog and check the analytics/research options separately. Do not assume a published layout proves that a generated summary or translation passed.

No paid model calls or complete unmocked language-detector evaluation were performed while preparing this patch. The pinned language-detector dependency must install in GitHub Actions. If a workflow fails, inspect the failed step; do not bypass language, source-evidence or privacy checks.
