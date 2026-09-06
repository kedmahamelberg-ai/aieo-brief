# Your new Brief

This update belongs in **kedmahamelberg-ai/aieo-brief**. The Observatory remains the source of the news and classifications.

The download contains the complete repository, a working reading preview and a Mac installer. The preview contains all 110 W35 developments, seven newly written news briefs five research summaries and a daily culture selection. The other developments retain their source headlines and links. The automatic writer can fill eligible stories from the complete evidence stored in your Supabase project.

## 1. Install the files

1. Unzip the update. Open `START-HERE.html` for the short version of these instructions.
2. In **GitHub Desktop**, select **aieo-brief** under **Current Repository**. If it is missing, use **File → Clone Repository**, select your `aieo-brief` repository and clone it. Then choose **Repository → Show in Finder** to see its location.
3. Open `INSTALL-BRIEF.command` in the download. Select that existing `aieo-brief` folder. Choose **Use current settings** for the first installation, or **Choose settings file** if you have completed the settings form below. The installer verifies the files and saves a backup beside your repository.
4. In GitHub Desktop, enter **Upgrade the Brief** in Summary, click **Commit to main**, then **Push origin**.

If double-clicking the installer does not run it: open Terminal, type `bash` followed by a space, drag `INSTALL-BRIEF.command` into Terminal and press Return. The download's `Repository` folder is the source; the existing GitHub Desktop clone is the destination. Do not drag the whole download into GitHub.

The installer does not commit, push, change your database or enable paid services. Existing `config/site.json` settings are preserved unless you explicitly choose a new settings file. Your backup includes every existing file that was overwritten and a list of newly added files.

## 2. Connect the existing database once

Use the same Supabase project as the Observatory and existing Brief.

1. In the download, open `Repository/supabase/migrations/202609060001_brief_community.sql` as text and copy its entire contents.
2. In **Supabase → SQL Editor → New query**, paste it and click **Run**. This adds the Brief's community and private editorial provenance tables. It can be run again. It does not replace the Observatory's tables.
3. Run `Repository/supabase/migrations/202609060002_brief_culture.sql` in a second query. It lets the same accounts like, save and discuss cultural works. Run the files in number order.
4. In the **aieo-brief GitHub repository → Settings → Secrets and variables → Actions → Secrets**, retain the existing `SUPABASE_URL` and `SUPABASE_SECRET_KEY`. If missing, add the project URL and server secret/service-role key there. The server secret must never be entered in the website settings form.

The first migration is required for the automatic writer even if you choose not to enable public comments. A successful website build alone does not establish that new editorial drafts were generated.

## 3. Choose the public website address

The included automatic publishing route is GitHub Pages.

1. In **aieo-brief → Settings → Pages**, choose **GitHub Actions** as the build/deployment source.
2. In **Settings → Secrets and variables → Actions → Variables**, create `BRIEF_PUBLISH` with the value `true`.
3. Without a custom domain, the default address is `https://kedmahamelberg-ai.github.io/aieo-brief/`. The default configuration uses this address; enter it in the settings form if you use that form.
4. To use a custom domain you control, set it in GitHub Pages, configure the DNS records GitHub provides, enable HTTPS and enter that same HTTPS address in the settings form. A separate Brief subdomain is appropriate; keep the existing Observatory address for the Observatory.

Your uploaded Brief repository is private. GitHub Pages for a private repository requires an eligible paid GitHub plan. If Pages is unavailable in Settings, resolve that hosting requirement before enabling `BRIEF_PUBLISH`. Keep this repository private: it connects to the research database and may have private material in its history. This package includes a static website build for other hosting, but a second provider's deployment connection has not been configured. [GitHub Pages availability](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)

## 4. Enable reader accounts, comments and likes

Reading, source links, sharing and device-local bookmarks work without an account. Public likes and comments use verified email sign-in and the database from step 2.

1. In **Supabase → Authentication**, enable email sign-in. Under **URL Configuration**, add the final Brief website URL as an allowed redirect, including its `/account/` page. For the default Pages address, this is `https://kedmahamelberg-ai.github.io/aieo-brief/account/`. Preserve the existing Observatory URLs in this shared project.
2. Configure **custom SMTP** in Supabase Authentication for public email delivery. Supabase's default mailer is restricted to pre-authorised project team addresses and has a very low sending limit. Reuse your existing mail provider if suitable. [Supabase SMTP setup](https://supabase.com/docs/guides/auth/auth-smtp), [email link sign-in](https://supabase.com/docs/guides/auth/auth-email-passwordless)
3. Open `owner-tools/CONFIGURE-THE-BRIEF.html` in the download. Enter the public website address, enable community, enter the Supabase project URL and its **publishable key**. A legacy **anon** key also works. These public keys are protected by the included database permissions; the service-role/secret key is rejected by the form and build.
4. Click the form's connection check after applying the migration. Download **Brief-Settings.json**.
5. Run `INSTALL-BRIEF.command` again. Select your **aieo-brief** repository, choose **Choose settings file**, then select `Brief-Settings.json`. Commit and push the changes in GitHub Desktop.
6. On the published Brief, sign in with your own email. In the offline settings form, enter that email in the moderator section and copy its generated SQL into Supabase SQL Editor. Run it once. Your account can then open **Moderation** from the account page.

Comments remain private until a moderator approves them. Readers can reply, report a comment and delete their own contributions. Moderation needs occasional attention even though collecting and publishing news is automatic. Likes require sign-in. “Most read” uses measured reading sessions after consent, not invented numbers or claims about unique people.

If you already set `BRIEF_SITE_URL`, `BRIEF_COMMUNITY_ENABLED`, `SUPABASE_PUBLISHABLE_KEY` or `GA4_MEASUREMENT_ID` as GitHub Actions **variables**, they override the corresponding settings file values. Keep one set of settings consistent.

## 5. Connect Google Analytics and automatic adverts once

The settings form handles both. The Brief uses **Google Auto ads**, so Google supplies and places adverts. There is no sponsor-selling step and no individual ad-unit setup.

1. Add the Brief website to your AdSense account. Use a domain root, such as a Brief subdomain you control, so `ads.txt` is available at its required location.
2. In `owner-tools/CONFIGURE-THE-BRIEF.html`, enter your `ca-pub-…` publisher ID. Install the downloaded settings file, commit and push. This publishes verification metadata and `ads.txt` while ad serving is still off.
3. After Google approves the site, open **AdSense → Ads → By site → your Brief → Edit**, turn on **Auto ads** and apply it to the site. For a calm experience, start with a low ad load and in-page formats. Turn off overlay anchors, vignettes and ad-intent links.
4. In AdSense **Privacy & messaging**, publish the consent message for the Brief. In the settings form, check the consent-message box and the approved/Auto-ads box. Install those settings, commit and push.
5. For Analytics, enter your GA4 web stream’s `G-…` measurement ID in the same form. Measurement starts only after a reader opts in.

Google then manages the adverts on newly published pages as well. Approval, ad availability and earnings depend on your account and audience. The code cannot activate your Google account or guarantee income. [Google Auto ads](https://support.google.com/adsense/answer/9261805?hl=en), [site approval](https://support.google.com/adsense/answer/7584263?hl=en), [ads.txt](https://support.google.com/adsense/answer/12171612?hl=en), [consent message requirements](https://support.google.com/adsense/answer/13554116?hl=en)

## 6. Start the first update and recognise success

After steps 1–3, go to **aieo-brief → Actions**:

1. Open **Update Brief News and Research → Run workflow → Run workflow**. Keep the default budgets for the first pass. It reuses successful saved work and checks source support for new headlines.
2. When that run ends, **Build and Publish AIEO Brief** starts automatically. Open it. The **build** job validates the content and the **deploy** job publishes it when `BRIEF_PUBLISH=true`.
3. Run **Update Brief Daily Culture → Run workflow** once to refresh the first daily selection. Future runs happen automatically.
4. Open the website using the deployment link. Check one story, an original-source link, a bookmark and your email sign-in. Approve one test comment through your moderation page. These live account checks cannot be performed inside the offline preview.

If only **build** is green and **deploy** is skipped, the files were built but publishing has not been enabled. If the writer reports failures, open that run's summary: successful stories are retained, unsupported drafts keep source links, and later scheduled passes continue. The website build can succeed while some stories still await a supported original brief; that is shown on the cards.

## What happens automatically afterwards

- **Every day at 12:15 UTC:** check the latest completed Observatory release and read its retained article evidence from the same Supabase database. Resume supported headlines and original summaries. When the Observatory publishes its next weekly edition, the next check brings it into the Brief. Daily checks do not claim that a new Observatory release exists every day.
- **Research, daily:** check the last seven calendar days through arXiv’s official API and Crossref metadata for SSRN and PNAS, up to six matched records per source per pass. Retain a rolling 28 days in the research feed, plus historical pages. Failed providers do not wipe earlier papers. Abstract summaries keep their study limits and publication status. Missing abstracts retain source links. This is selective discovery, not an exhaustive literature review. [arXiv API](https://info.arxiv.org/help/api/basics.html), [Crossref API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- **Culture, 05:25 UTC daily:** select a drawing or illustration, a poem, a short reading, a quotation and a music track. **17:25 UTC** retries any missing category; a completed selection is not replaced just to look new. Source failures preserve earlier work and appear in the Actions summary.
- **Culture sources:** Cleveland Museum of Art CC0 images, PoetryDB’s historical poems, original English texts from the permitted Project Gutenberg mirrors, and artist-published Internet Archive / ccMixter music with commercial reuse licences and declared source credits. Work dates, creators, original links and reuse information accompany every selection. Music loads only on an explicit Play click. Older works are selected today; they are not described as newly made or automatically related to AI. These collections are set in `config/culture.json`. [Museum API](https://www.clevelandart.org/open-access-api), [PoetryDB](https://github.com/thundercomb/poetrydb), [Gutenberg mirrors](https://www.gutenberg.org/MIRRORS.ALL), [ccMixter API](https://ccmixter.org/query-api)
- **After either update:** build from the latest saved inputs, check all pages and totals, preserve old URLs, and publish when enabled. News, research and culture have separate counts; cultural works never enter the Observatory’s 110-development totals.
- **Every day at 04:00 UTC:** delete detailed reading sessions older than 90 days. Reader comments still need moderation.

Schedules use UTC. GitHub may start scheduled jobs late; jobs also require Actions to be enabled on the default `main` branch. The Brief does not replace the Observatory’s own collection schedule. Creative selection uses existing works; it does not generate fake author quotations, new songs or scientific findings.

The default local-model writing budget is 45 minutes for news and 15 minutes for research per run. An unchanged release with no pending work avoids starting the model. There is no paid model API in this implementation, but GitHub Actions runner usage, your hosting plan, Supabase, mail delivery and any payment provider can have costs. Keep an eye on their usage pages. After a new release, several passes may be needed to write all eligible stories.

## Editorial boundaries

The Brief keeps the Observatory's independent human and AI/operator readings. A source need not discuss both dimensions. Company claims remain claims; forecasts remain forecasts; abstract-based findings retain their study population and limitations. It does not equate more AI with an automatic human benefit.

The initial W35 snapshot has **110 developments from 111 source pages**. Human readings are **45 gain, 3 loss, 26 mixed, 8 no directional effect and 28 unresolved**. AI/operator readings are **36 gain, 2 loss, 38 mixed, 6 no directional effect and 28 unresolved**. Each set totals 110. The Brief does not add those axes together. It does not restore the superseded 17/6 or 9/2 figures.

New headlines require complete retained news evidence and explicit source support. If that evidence is unavailable, the card identifies the publisher's original headline. Research summaries are based on available abstracts, not an unperformed full-paper review. Automated checks and a separate model review reduce unsupported claims but do not guarantee that every sentence is correct.

## Where files belong

| Download item | Destination/use |
|---|---|
| `Repository/` contents | Your existing **aieo-brief** repository; the installer copies them |
| `Repository/config/site.json` | Public website settings; the form and installer manage this |
| Both files in `Repository/supabase/migrations/`, numbered `001` then `002` | Run once in that order in your existing Supabase SQL Editor |
| `Preview/index.html` | Local website preview; does not change the live site |
| `owner-tools/CONFIGURE-THE-BRIEF.html` | Offline settings form; does not receive your server secret |
| `Brief-Settings.json` downloaded by the form | Select it when the installer asks for settings |
| `FILES-TO-INSTALL.tsv`, installer and validation reports | Keep beside `Repository`; they do not belong in the public website |

The complete source repository contains the templates, styles, scripts, data and workflows needed for future builds. Publishing uploads only the generated `_site` directory. Private article evidence and the database server secret do not enter that directory.
