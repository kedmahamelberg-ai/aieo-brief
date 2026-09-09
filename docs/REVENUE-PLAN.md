# A concrete revenue plan for the Brief

## Current facts from the repository inspection

Google Analytics ID G-QC9205V7V7 is configured behind analytics consent. Receipt in that Google property still requires a Realtime check. AdSense publisher ca-pub-5170234738371400 is present, but ads and the consent message are disabled; feed, rail and story ad-unit IDs are empty. No active sponsor, reader-payment link or paid product is configured. This is infrastructure, not yet an operating passive-income business. Resend verification enables email sending; it is unrelated to Google advertising approval.

## Turn on real banner placements

In AdSense, confirm that the Brief is approved and eligible to serve under Sites. Add/verify the site as Google requests. Publish Google's European-regulations consent message (Privacy & messaging) for the Brief. A code flag does not create or publish that message. Google's EU user-consent policy and certified-CMP requirements must be satisfied where applicable.

Create three responsive DISPLAY ad units under Ads > By ad unit > Display ads, named Brief feed, Brief rail, and Brief story. Each produces code containing a numeric data-ad-slot value. Use those three actual values in GitHub's aieo-brief > Settings > Secrets and variables > Actions > Variables:

| Variable | Value |
|---|---|
| BRIEF_ADSENSE_ENABLED | true, only after approval |
| BRIEF_ADSENSE_CMP_ENABLED | true, only after publishing the actual consent message |
| BRIEF_ADSENSE_MODE | placements |
| BRIEF_ADSENSE_FEED_SLOT | numeric ID for Brief feed |
| BRIEF_ADSENSE_RAIL_SLOT | numeric ID for Brief rail |
| BRIEF_ADSENSE_STORY_SLOT | numeric ID for Brief story |

Then start a new Build and Publish AIEO Brief workflow run. Changing a GitHub variable does not rebuild a static site by itself. The template already contains the banner placements; no invented ad-unit IDs or manual pasted ad scripts are needed. Check an eligible article with original Brief editorial content, not a source-only stub or account/privacy page. Those low-content/administrative pages intentionally request no ads. The rail is hidden on small screens. Do not click your own ads to test them. Ad blockers, a declined ad-consent choice, unfilled inventory or Google restrictions can still prevent ads from appearing.

Official setup: https://support.google.com/adsense/answer/9274025?hl=en
Google consent requirements: https://www.google.com/about/company/user-consent-policy-help/

## Revenue sequence

First, make the free product worth returning to: complete English briefs, clear source attribution, useful research limits and an inviting daily cultural pause. Distribution should initially use your own professional channels, stable searchable topic pages and referral links, not paid acquisition. The two optional browser alerts are a return mechanism, not an email mailing list.

Second, enable modest, clearly labelled AdSense placements. Keep the reading experience intact. Measure page revenue and return behavior, not merely ad-button clicks. Use Google reports for billable advertising measurements. The Brief's first-party counters are not those reports.

Third, create ONE evergreen paid resource that draws on your expertise. A proposed first test is an AI Claims Evaluation Toolkit: a practical workbook, worked examples and an evaluation template. A €19 introductory price would be a hypothesis to test, not a researched price recommendation or a published offer. A real product, checkout and automatic file delivery must exist before adding its link to the Brief. Add it to config/site.json under revenue.offers, kind product, with its actual title, description and HTTPS payment/product URL. Do not publish a fake checkout or claim that payments are connected.

Fourth, add only genuinely relevant, clearly disclosed affiliate resources after you have actual approved affiliate relationships. A book or resource should be helpful without the commission. Never monetize by selling raw reader research data or by inventing engagement.

Sponsorship can supplement these streams, but sponsor outreach, negotiations and tailored briefings are active work. They are not passive income. The existing contact invitation supports enquiries; it is not automatic monetization.

## Illustrative arithmetic, not a forecast

Ad revenue = AdSense page views / 1,000 × measured page RPM. Google defines page RPM here: https://support.google.com/adsense/answer/112030?hl=en .

At a hypothetical €4 page RPM, 10,000 measured monthly page views produce €40, 50,000 produce €200, and 100,000 produce €400. These are chosen arithmetic examples, not estimates of this site's attainable traffic or RPM. Thirty sales of a €19 digital product would generate €570 gross. Neither the sales nor the conversion rate is assumed to occur. Deduct payment costs, refunds, tax obligations and operating costs before treating gross receipts as spendable income.

This comparison is why I would combine an evergreen paid resource with advertising rather than expect banner ads alone to provide meaningful income at small scale. Track content generation costs, hosting/email/database usage, repeat readership, actual paid conversions and net cash receipts. Set a monthly operating budget outside the existing per-job model cap. No paid traffic is proposed while the content and conversion path are unproven.

## What still requires the owner's accounts

The SMTP username and password must be corrected in Supabase's SMTP form. AdSense approval, ad-unit IDs and consent-message publication are not established by these screenshots or repository files. Analytics must be verified in Google Realtime. A product, payment account, approved affiliate programme or sponsor must be real before its destination is added. The patch does not create or purchase any of these, upgrade a plan, or promise income.
