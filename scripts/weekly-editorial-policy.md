# Weekly editorial publication

The signed format starts with edition 2026-W41, covering 5 to 11 October and
normally published after the Observatory handoff on Monday 12 October 2026.
Earlier editions retain their existing presentation.

Both reviews use flowing prose in normal type, credited to Kedma Hamelberg.
The title, prose and evidence-scope note together must stay below 200 words.
Natural punctuation is allowed. The prose links directly to the Brief posts.
The writer must use plain English, preserve uncertainty and never invent
personal experiences. The title, prose and artwork reason use full forms
instead of contractions; grammatical possessives remain acceptable.

The news review requires five different completed summaries, one per discovery
market, drawn from the edition week. Markets describe discovery streams, not
necessarily the location of events. The research review requires two different
papers dated within that week. Shared vocabulary proposes a close pair and an
independent model check must confirm a meaningful connection and accurate limits.
Institution metadata is not a requirement for selecting a paper.

The writer chooses a metaphorical illustration from the existing CC0/public-domain
art library and explains its relationship to the prose. Credits and source links
remain visible and the image is shown without cropping. Used files, source URLs
and artwork identities are excluded so duplicate catalog records cannot repeat
an illustration. Extend the verified art library if the unused pool runs out.

The Monday Prepare Weekly Brief Review workflow uses the latest validated
Observatory release and Brief summaries to make a private draft artifact. It
also runs after a manually dispatched Observatory handoff or when dispatched
directly. The artifact contains a JSON record for exact approval verification
and a self-contained HTML preview for reading. The owner email shows the same
visual cards, selected rights-cleared artwork, full prose, and source links.
When either section is pending, the email explains why and offers no approval
action.
The public build renders only editions with an owner-approved file in
data/weekly-overviews/approved/; it cannot generate or publish new prose.

When both sections pass, GitHub's weekly-editorial environment waits for a
review by kedmahamelberg-ai. The owner can approve or reject with a correction
comment on the workflow run. The approval job verifies GitHub's review history,
the exact draft digest, both editorial checks, and the current source hashes.
Only then may the scheduled publisher commit that reviewed edition and run the
public build. Rejecting the review leaves the draft unpublished. A revision
requires another review run and another approval.

Each section may use two bounded structural repairs and one revision after a failed
independent check, always followed by a fresh independent check and within the
existing shared AI job spending cap. An incomplete source set, failed review or
depleted image pool produces a clearly labelled pending section without an
author byline. GitHub warns when manual attention is needed. Do not edit ready
prose or source provenance to bypass checks.

Approved sections are cached with hashes of their selected public sources.
Daily ordering and rebuilds preserve the prose and pictures. Changes or withdrawal
of a selected summary invalidate that section. Earlier archive records remain intact.

Search indexing checks require sitemap entries to use the same canonical URLs as
their HTML, reject duplicates and accidental public noindex, and verify all local
links. Internal links use directory canonicals, including the full past-edition
archive in the sitemap. Search Console's duplicate-canonical category is expected
for old index.html URLs. Google controls when discovered pages are crawled or indexed.
