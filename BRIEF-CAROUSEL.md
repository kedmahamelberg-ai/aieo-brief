# The Brief carousel and social links

The personal homepage fetches `https://brief.hamelberg-ai.com/data/spotlight.json` when opened. The Brief generates this public feed on every normal publication build, using its daily lead and a mix of discovery markets. Cards link to exact story routes. This is a first-party news feed, not a scraped LinkedIn feed; no social login, widget subscription or embedded platform tracking is required.

Photographs come from the rights-cleared 2026-W38 social campaign. The original files are reused as geographic illustrations, not presented as photos of each news event. Credits, source URLs and licenses are in The Brief’s `config/spotlight-photos.json` and carried in the public feed. For a new country or photo, update that register and its asset together.

The personal homepage includes five linked fallback stories for browsers without JavaScript or when the live feed is unavailable. Carousel rotation pauses while hovered, focused, offscreen or in a background tab, and defaults to off when reduced motion is requested. Readers can navigate by controls, keyboard or touch.

Social links point exclusively to The Brief’s LinkedIn company 146490147, Facebook Page 61594324679612 and Instagram account thebrief_ai.empowerment. Templates: personal `_includes/brief-social-links.html`, Brief `templates/social-links.html`.
