# AIEO Brief Phase 2A.2 local-model editorial engine

Phase 2A.1 turns the working editorial preview into an evidence-bounded editorial product with clearer UX and a full sharing surface.

## What changes

### Editorial generation

A server-side generator reads only:
- current AIEO resolved development metadata
- current reviewed symbiosis relationship
- private best-available source evidence in Supabase

It generates:
- original AIEO headline
- one-sentence deck
- What happened
- Why it matters
- For humans
- For AI / operator side
- 2 concise body paragraphs

The reviewed relationship classification is fixed input. The editorial model cannot change it.

Headline-only developments are NOT sent to the editorial model. They remain Early signals.

Every generated draft is versioned in:
- `brief_generated_artifacts`
- `brief_story_versions`

The model, prompt version, input hash, output hash, evidence snapshot IDs, and superseded version are retained for future research and correction.

### Copyright guardrail

The model is explicitly instructed to paraphrase. The generator rejects a draft if it contains a 10-word exact phrase from the supplied source evidence and retries once.

Private publisher article bodies never enter the public `_site`.

### Local open-weight model

The editorial engine does not use a paid model API. It runs `Qwen3-4B` locally through `llama.cpp` inside the workflow.

Default quantization:

`ggml-org/Qwen3-4B-GGUF:Q4_K_M`

The model weights are Apache 2.0 licensed. The Q4_K_M file is about 2.5 GB and fits the standard 8 GB Linux runner used by private GitHub repositories.

The workflow pins llama.cpp to `b10516` for reproducibility and records both the model revision and llama.cpp version with every generated artifact.

Qwen3 is instructed to use non-thinking mode for this editorial task, reducing unnecessary CPU time and output.

### UX

The public preview now includes:
- sticky simplified navigation
- horizontally scrollable relationship ticker on small screens
- top, rail, in-feed, inline-story, and story-rail ad inventory
- one primary lead development
- progressive disclosure
- search and relationship filters
- only six latest cards visible at first
- "Show more" in groups of six
- Quick read on every story
- What happened and Why it matters first
- People and AI sides next
- longer Brief text behind a disclosure
- source links behind a disclosure
- sticky story actions
- prominent notification/follow CTA
- visible subscription CTA
- native mobile sharing
- desktop share dialog for WhatsApp, Telegram, LinkedIn, Reddit, X, Facebook, email, and copy link
- reduced-motion support
- large tap targets and keyboard focus states

"Trending" is deliberately renamed "Worth opening" until real first-party views, comments, shares, and saves exist.

## Install in `aieo-brief`

Replace/add:

- requirements.txt
- scripts/generate_editorial_stories.py
- scripts/build_site.py
- scripts/validate_public_site.py
- templates/base.html
- templates/index.html
- templates/story.html
- assets/site.css
- assets/app.js
- .github/workflows/generate-brief-editorial.yml
- .github/workflows/build-brief-preview.yml
- data/mock/*

Commit:

`Add evidence-bounded editorial engine and engagement-first UX`

## No paid model API key is required

You do not need `OPENAI_API_KEY` or any other paid inference credential.

The first live generation downloads the open-weight Qwen model and builds a pinned llama.cpp server. Later runs can reuse the GitHub Actions model cache.

Important: the model itself has no API fee. Because `aieo-brief` is a private repository, GitHub-hosted Actions still consume your included private-repository runner minutes. If you want zero external compute charges as well, the same workflow can later be moved to a self-hosted runner on your Mac.

## Safe rollout

### Step 1: eligibility test

Actions -> Generate AIEO Brief Editorial Drafts

Use:

- limit: 5
- dry_run: true
- force: false

This makes no model calls and writes nothing.

### Step 2: first five editorial stories

Run again:

- limit: 5
- dry_run: false
- force: false

Expected:
- 5 generated
- 0 failed

### Step 3: build preview

Actions -> Build AIEO Brief Preview

Download the new preview artifact and inspect the five generated stories.

### Step 4: generate remaining eligible current stories

When the first five look right:

- limit: 0
- dry_run: false
- force: false

Unchanged stories are skipped by evidence fingerprint.

### Step 5: rebuild preview

Run Build AIEO Brief Preview again.

## Important preview behavior

The Like, Discuss, Save, Follow, Notify, and Brief subscription buttons are deliberately visible now but do not persist data yet. They explain what the next community layer will do.

Share IS functional now.

Phase 3 will connect the visible interaction surfaces to:
- first-party pseudonymous event logging
- accounts
- comments and replies
- likes/reactions
- saves
- story follows
- notifications
- subscriptions
- real Top 5 / Trending calculations
- ad impressions and clicks

That is when no engagement signal is lost and every interaction becomes research-ready under explicit consent and governance.

## Acceptance checks

The build fails if:
- a Supabase or other server secret appears in `_site`
- private `body_text` appears in public JSON
- an em dash appears in public output
- the story page count does not match public JSON
- homepage engagement/share/ad hooks are missing
- story share/follow/ad hooks are missing

## UX principle

The first screen answers only:

1. What happened?
2. Why does it matter?
3. Who gained or was constrained?

Everything else is progressively disclosed.
