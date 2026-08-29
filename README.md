# AIEO Brief Phase 2A

This is the first actual AIEO Brief product build. Install it in the separate private `aieo-brief` repository.

## What it reads

At build time only:

- the current public Observatory release JSON
- the current human-reviewed relationship JSON
- private `brief_stories` for permanent story slugs
- private `brief_event_evidence_readiness` for evidence strength

The Supabase service key is used only in GitHub Actions. It is never written into `_site` or browser JavaScript.

## Evidence rule

The current active-event evidence profile is approximately half with at least one full source and half headline-only. Phase 2A therefore uses two editorial modes.

For a development with retained full-source support, the story can show the AIEO event summary and the reviewed relationship explanation.

For headline-only evidence, the page is labeled `Early signal`, uses only the AIEO resolved event title and source metadata, and does not manufacture a detailed body.

Publisher article body text is never copied into the public output.

## Before installation

In GitHub repository `kedmahamelberg-ai/aieo-brief` add Actions secrets:

- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`

Use the same Supabase project as the Observatory.

## Install

Upload the package contents to the root of the private `aieo-brief` repository on `main`.

Commit message:

`Build first AIEO Brief editorial preview`

## Build

GitHub -> Actions -> Build AIEO Brief Preview -> Run workflow

The workflow builds one current-week living story page per Observatory development and uploads `_site` as an artifact named:

`aieo-brief-preview-<run-id>`

## Inspect

Download and extract the artifact. The static site should be served through a local web server because it uses root-relative paths.

From Terminal:

```bash
cd path/to/_site
python3 -m http.server 8080
```

Then open `http://localhost:8080`.

If you prefer not to use Terminal, after the first successful build we will connect `aieo-brief` to Cloudflare Pages and use a temporary `*.pages.dev` preview URL before attaching `brief.hamelberg-ai.com`.

## What Phase 2A contains

- Reuters-like relationship ticker
- lead development
- ranked-story placeholder rail
- four relationship streams
- latest current-week developments
- persistent living story URLs from `brief_stories`
- source links
- People and AI direction cards
- evidence-strength gating
- ad inventory placeholders
- Research Radar placeholder
- community interaction placeholders
- working browser share / copy-link action

## Not live yet

- comments
- likes
- saves
- follows
- measured views
- live popularity rankings
- Research Radar ingestion
- ads
- premium

Those are intentionally deferred until the editorial product is validated.

## Acceptance checks

Homepage:

- current Observatory period is shown
- current relationship counts match the Observatory
- relationship colors match AIEO
- lead story opens
- latest stories open
- repeated source coverage is grouped into developments
- headline-only stories are marked `Early signal`

Story page:

- original publisher links open in a new tab
- People and AI directions match reviewed AIEO relationship evidence
- full publisher bodies are not republished
- share works through native share or copies the link

Security:

- `_site` contains no Supabase secret
- `_site/data/current.json` contains no private source body text
