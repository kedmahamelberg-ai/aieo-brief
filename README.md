# AIEO Brief

A source-linked AI news and research publication, with reading lists, email sign-in, moderated discussion and daily art, words and music, and Google Auto ads.

The Brief uses the Observatory’s canonical weekly release and independent human/AI readings. It preserves those classifications. New headlines and summaries are written only from retained complete article evidence. Research summaries use actual abstracts and identify their limited scope.

## Owner setup

Open `OWNER-SETUP.md`. The downloadable update also includes a point-and-click settings form and a Mac installer for this repository.

The separate Observatory repository is not the installation target.

## Build and test

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p 'test_*.py'
node --test tests/core.test.js
python scripts/build_site.py --preview
python scripts/validate_public_site.py
```

Open `_site/index.html`. `--preview` uses the real W35 snapshot included in `data/preview`; it has 110 developments, seven original news summaries and five paper summaries. Sign-in, live counts and advertising are disabled in this offline preview.

For a live build, set `SUPABASE_URL` and `SUPABASE_SECRET_KEY`, configure `config/site.json`, then run `python scripts/build_site.py --update-archive`. The service key stays on the server. `SUPABASE_PUBLISHABLE_KEY` is the only browser key. Apply the included database migration before the automatic writer or community services run.

The optional database tests run a real PostgreSQL engine locally through PGlite:

```bash
npm ci
npm run test:database
```

## Automatic operation

- The daily 12:15 UTC job checks for unfinished news and research published in the last seven days before loading its local model.
- Successful news versions are saved individually to Supabase. A failed draft retains its source link, and subsequent passes prioritise less-attempted items.
- Daily default writing budgets are 45 minutes for news and 15 for research. A no-change pass does not download/start the model. GitHub runner minutes still apply.
- Research collection uses the arXiv and Crossref APIs, with a maximum of six selected records per source per week. It is a selection, not an exhaustive review of AI science. PNAS/SSRN records without abstracts keep their original titles and links.
- Every generation pass triggers a fresh validated website build. GitHub Pages deployment is enabled by the `BRIEF_PUBLISH=true` repository variable after Pages is configured.
- The archive preserves story URLs and discussion keys. A separate 04:00 UTC job expires detailed reading sessions after 90 days.
- No publisher article bodies or private support quotes are copied into the website. Source support lives in the service-only `brief_editorial_provenance` table.

## Editorial limits

Automatic support checks and model review reduce errors; they do not certify truth. Company claims, forecasts, opinion and study findings keep their attribution. A paper abstract is never labelled as a full-paper reading. Headlines from sources lacking suitable evidence remain clearly identified as publisher headlines.

The seven curated W35 summaries are strictly bound to that release hash and its independent axes. They do not override future releases or corrected classifications.

## Automatic daily publishing

News reads the existing Observatory/Supabase evidence and current weekly release every day at 12:15 UTC. Research discovery checks arXiv and Crossref (PNAS/SSRN) daily, retains recent papers and resumes summaries. Cultural selections run at 05:25 UTC with a 17:25 retry of missing categories. The five daily categories are illustration, poetry, a short reading, an attributed quotation and music. Both update workflows trigger the validated build/publication workflow.

Culture uses museum CC0 images, historic poetry and books, and licensed artist-published Internet Archive / ccMixter music. Original creators, source links, work dates and reuse information are kept. The selection date never replaces the original work date. Configuration: `config/culture.json`. New culture identities use migration `202609060002_brief_culture.sql`, after the first migration.

AdSense defaults to Auto ads. The owner connects their publisher ID and published Google consent message once, enables Auto ads in their approved account, and Google then manages ad placement. There is no sponsor solicitation workflow in the public site. No revenue or account approval is guaranteed. See `OWNER-SETUP.md`.
