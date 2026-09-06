# Monday editions and news notifications

The Observatory collects at 00:17 UTC on Monday. On 7 September 2026 this is
02:17 in the Netherlands. The completed reporting week is 31 August–6 September,
2026-W36. Collection uses five markets, with separate English and French
searches for Canada. Eight-day discovery results are filtered by publication
date when the seven-day release is built.

The Brief checks the published Observatory at minute 41 of each hour. When its
release or classifications change, it runs a bounded news-writing pass and
publishes a matching edition. Incomplete drafts retain their source links.
Research still refreshes daily; culture refreshes twice daily. GitHub may delay
scheduled starts. No exact finish time is promised.

The Monday evening check **Verify Both Live Weekly Editions** compares the dates,
release identity, classification fingerprint and development counts on the two
public websites. A failed check appears in GitHub Actions. It does not replace
the complete previous edition with incomplete data.

## Turn on browser notifications once

1. In Supabase → SQL Editor, run all of
   `supabase/migrations/202609060003_brief_notifications.sql`.
2. In Supabase → Project Settings → API Keys, copy your **publishable** key
   (beginning `sb_publishable_`). In **aieo-brief → Settings → Secrets and
   variables → Actions → Variables**, add `SUPABASE_PUBLISHABLE_KEY` with that
   value. Keep the existing server secret in Secrets. Never use a secret key
   as this variable.
3. In **Actions → Build and Publish AIEO Brief**, run the workflow on **main**.
4. When it finishes, visit the Brief and click **Get news updates → Turn on news
   notifications**. Allow the browser prompt. The page confirms activation.

No paid notification account or new signing-secret setup is required. A signing
key is generated once by the build and stored in a private Supabase table. Only
its public counterpart is included in the website. New readers start with the
edition already online, so their first alert is for a later weekly edition.

Alerts are opt-in, one per new weekly news edition. Rebuilding or correcting the
same edition does not create another alert. A reader can turn alerts off from
the same page. Supported iPhones and iPads need the site added to the Home Screen
first; the page explains this. RSS and the existing Monthly Pulse remain
available without browser notifications.

The sender reads the live Brief after successful deployment. Private browser
addresses are not placed in GitHub, public files, analytics or workflow logs.
Expired delivery addresses are removed; transient failures retry with a bounded
attempt count. No test notification or newsletter is sent by the test suite.

## Checks performed before this update

Date-boundary and five-market tests; matching-release and correction tests;
31 Brief Python tests; 8 Node tests; 46 PostgreSQL permission and behavior checks;
130 generated pages and 4,074 local destinations. Notification encryption was
checked locally without contacting any push recipient. Real device delivery
still requires the one-time connection above and a reader's explicit opt-in.
