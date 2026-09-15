# The Brief carousel and social links

The personal homepage fetches `https://brief.hamelberg-ai.com/data/spotlight.json` when opened. The Brief generates this public feed on every normal publication build, using its daily lead and a mix of discovery markets. Cards link to exact story routes. This is a first-party news feed, not a scraped LinkedIn feed; no social login, widget subscription or embedded platform tracking is required.

Photographs come from the rights-cleared launch and 2026-W38 social campaigns. The original files are reused as geographic illustrations, not presented as photos of each news event. Credits, source URLs and licenses are in The Brief’s `config/story-photos.json` and carried in the public feed. For a new country or photo, update that register and its asset together.

The personal homepage includes five linked fallback stories for browsers without JavaScript or when the live feed is unavailable. Carousel rotation pauses while hovered, focused, offscreen or in a background tab, and defaults to off when reduced motion is requested. Readers can navigate by controls, keyboard or touch.

Social links point exclusively to The Brief’s LinkedIn company 146490147, Facebook Page 61594324679612 and Instagram account thebrief_ai.empowerment. Templates: personal `_includes/brief-social-links.html`, Brief `templates/social-links.html`.

## Story images and weekly refresh
The Observatory handoff runs hourly and triggers publication of new editions. Every publication regenerates the carousel from that edition's stories; the homepage reads the feed on each visit. No manual weekly carousel edits are needed.

`config/story-photos.json` is the canonical photo pool and exact-article override registry. `scripts/story_photos.py` resolves images for story Open Graph previews, compact social links, and the carousel. Unpinned stories get a stable article-based choice from their discovery markets. The carousel skips repeated source images, selecting other current stories instead. It never fills with last week's stories. Photographs are geographic illustrations, not photographs of the reported event.

Social renderers must call `assert_distinct_story_photos` for the batch before generating assets. One story can share its photo across all platforms and its Story frames; different articles in the batch cannot. The W38 renderer now consumes this registry, preserving its seven already-approved unique photographs. The former `spotlight-photos.json` country-only mapping is retired.

Preflight a social batch with `python scripts/story_photos.py /path/to/batch.json`. Duplicate checking uses file content hashes, so renaming a photo cannot bypass it.
