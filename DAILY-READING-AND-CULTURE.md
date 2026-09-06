# Daily reading and the stored cultural collection

The Brief receives a weekly edition from the Observatory. It offers seven daily
front-page layouts, with a different lead, highlights and starting batch of
stories. Every current story stays accessible. Source publication dates,
headlines, classifications, story identities and measured popularity are not
changed by rotation. The default reading order changes at the next page load
after midnight in Europe/Amsterdam; it does not jump while someone is reading.

The existing newest-reporting, market, topic, search, most-read, like, discussion,
save and share controls remain available. Popularity ordering uses actual opted-in
reading or interaction counts, not generated figures.

## The database shipped with this update

| Category | Entries | What is stored |
| --- | ---: | --- |
| Art and illustration | 400 | Museum metadata, credits and the original web JPG |
| Poetry | 400 | Poem text, line breaks, creator, edition and translator |
| Short readings | 400 | A passage with its book, creator, edition and source location |
| Quotations | 400 | Exact words, surrounding passage and edition/translation credits |
| Music | 400 | Recording metadata, composer/performer, recording credits, licence and playback/source URLs |

These are 2,000 collection entries, not 2,000 different artists or books. Readings
and quotations are selected passages from a smaller set of works. Music entries
are recordings; different performances or movements can belong to one composition.
The first calendar uses every entry once per category over 400 days, then cycles.
The JSON source lists and the SQLite database are both included. There is no
additional Supabase migration or new paid service for this collection.

Museum cultural attribution is preserved, including uncertainty or an unknown
artist. We do not invent an artist's nationality from the place where an object
was found. Named writers/composers carry their nationality or cultural background.
Translation and recording credits are visible on the reading pages. Some readings
are in their original Portuguese; the language is labelled. Historical text can
express views different from the reader's or the Brief's.

The broad collection includes Asian, African, European and American traditions,
with work from or associated with India, Iran, China, Tibet, Nepal, Japan, Brazil,
Russia and other places. It is a selected collection, not equal representation of
every country. The licensed recording section is mainly historical European
classical music, with other origins also represented.

A separate discovery shelf links to contemporary/protected work at the original
institution: for example Dalí at MoMA, Clarice Lispector at Instituto Moreira Salles,
Orwell at his foundation, Kafka's credited translation and Nobel biographies.
It includes Tolstoy's documented 1902 literature nomination, labelled as a
nomination, not a prize or a shortlist. These additional links do not inflate
the five 400-entry category totals.

## Automatic publishing

- The local cultural calendar runs at 03:25 UTC daily, with another opportunity
  at 15:25 UTC. Both choose the same date's records. No museum, book, poetry or
  music catalogue is scraped during selection. Existing selections are retained
  for 45 days in the current culture feed; published page URLs remain archived.
- The normal site build also selects today's five works from the database, so a
  delayed collection job does not require new scraping or leave the build without
  a daily selection.
- Audio is not stored in this package: it streams from the credited music host
  only after Play. If that host is unavailable, the page retains its source link.
- News follows the completed Observatory release. Research keeps its existing
  daily discovery and summary workflow. GitHub's scheduled starts may be delayed;
  the full publishing workflow still needs GitHub, the Observatory and Supabase.
- News alerts remain opt-in and weekly. Daily rearrangement or culture selection
  does not send readers another news-edition notification.

## Verification and maintenance

`python -m unittest discover -s tests -p 'test_*.py'` checks the entire 400-day
calendar, all source/credit fields and cached artworks, exact quotation contexts,
news-count preservation, week boundaries, and no network use during selection.
`node --test tests/core.test.js tests/news-worker.test.js` checks filters, sharing,
real metrics and notification behavior. The existing PostgreSQL tests cover
community and notification permissions. Public-page validation checks actual
links and counts after building.

`data/culture/library-manifest.json` contains record counts and hashes. Source
metadata and text integrity were checked automatically; attribution was sampled
and problematic extracts removed. This is not a claim of manual review of every
line of all 2,000 entries. Source documents and museum/recording records remain the
reference for corrections.

To deliberately change the collection, edit the relevant attributed JSON list,
then run `python scripts/build_culture_library.py`, test and commit the resulting
database and manifest together. The normal daily job never rebuilds the collection
or changes an existing author's words.

The update also includes the preceding Monday handoff and news-notification
changes. See `MONDAY-AND-NEWS-ALERTS.md` if browser notifications have not yet been
connected. The cultural database itself requires no SQL setup.
