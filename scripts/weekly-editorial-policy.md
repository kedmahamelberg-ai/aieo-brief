# Weekly editorial publication

The signed format starts with edition 2026-W41, covering 5 to 11 October and
normally published after the Observatory handoff on Monday 12 October 2026.
Earlier editions retain their existing presentation.

Both reviews use flowing prose in normal type, credited to Kedma Hamelberg.
The title, prose and evidence-scope note together must stay below 200 words.
The prose contains no colon, en dash or em dash. It links directly to the Brief
posts and ends with one relevant reflective question. The writer must use plain
English, preserve uncertainty and never invent personal experiences.

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

The regular publication build runs this after validating the Observatory export
and loading the Brief summaries. The existing Follow Observatory Editions workflow
starts publication after the news-writing handoff. Its hourly check also retries
pending weekly checks without rerunning the whole news-writing job. Daily research
publication can supply missing papers. No additional scheduled service is required.

Each section uses at most one draft and one independent review per attempt, within
the existing shared AI job spending cap. Three attempts per unchanged input are
allowed. An incomplete source set, failed review or depleted image pool produces
a clearly labelled pending section without an author byline. GitHub warns when
manual attention is needed. A deliberate retry after fixing a transient problem
can remove the pending section's attempts and input_hash fields from
data/weekly-overviews/history.json and rerun publication. Do not edit ready prose
or source provenance to bypass checks.

Approved sections are cached with hashes of their selected public sources.
Daily ordering and rebuilds preserve the prose and pictures. Changes or withdrawal
of a selected summary invalidate that section. Earlier archive records remain intact.

Search indexing checks require sitemap entries to use the same canonical URLs as
their HTML, reject duplicates and accidental public noindex, and verify all local
links. Internal links use directory canonicals, including the full past-edition
archive in the sitemap. Search Console's duplicate-canonical category is expected
for old index.html URLs. Google controls when discovered pages are crawled or indexed.
