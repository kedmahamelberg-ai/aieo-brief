# Funding the Brief

The repository currently has GA4 measurement ID **G-QC9205V7V7** and AdSense publisher ID **ca-pub-5170234738371400**. Analytics uses reader opt-in. Advertising is disabled, the Google consent message is unconfirmed, and no banner ad-unit IDs are configured. A configured ID is not proof that Google has received events or approved the site.

## Check Analytics

After deploying, open the live Brief, accept its optional analytics choice, and open a story. In Google Analytics, select the property containing G-QC9205V7V7 and check Realtime. Also test the culture/research carousel links; `feature_open` records the placement after consent. If the wrong property appears, set the repository variable `GA4_MEASUREMENT_ID` to the correct ID. GitHub variables override the repository config.

## Activate advertising

1. In AdSense → Sites, check that `brief.hamelberg-ai.com` is approved and ready. The build includes the publisher verification metadata and ads.txt entry.
2. Publish the site's Google consent message in AdSense Privacy & messaging.
3. Open `owner-tools/MONETIZE-THE-BRIEF.html` locally. Choose either Auto ads or the feed/rail/story placements. For placements, paste the numeric ad-unit IDs created in AdSense. Confirm approval and the consent message only after completing those steps.
4. Download `Brief-Monetization.json`. Use the update package's `APPLY-SETTINGS.command` to apply it, then commit and push the settings in GitHub Desktop. It preserves the other settings and saves a backup.

Advertising appears only on eligible editorial news pages. Metadata-only entries, private/account screens and cultural pages do not request ads. The desktop rail is hidden on narrow screens. The existing Google consent integration controls whether an ad request can be made; analytics consent alone does not enable ads. Empty ad units collapse.

## Direct sponsorship

The new `/support/` page invites sponsors and commissioned AI research briefings at your existing business email address. Its links open a visitor's email draft; they do not send messages automatically.

Once a sponsor has agreed to a campaign, use the same local settings form to enter its name, short message, HTTPS destination, and inclusive start/end dates. The banner appears on eligible news pages during that campaign. It is clearly labelled SPONSORED and does not alter editorial rankings or research findings. There is no invented sponsor or promised audience size.

## Reader support and useful products

Add your own Ko-fi, Buy Me a Coffee, payment or membership HTTPS link in the settings form. Until then, the support page offers sharing and sponsorship enquiries rather than a nonfunctional payment button.

Optional products and affiliate resources can be listed in `config/site.json` → `revenue.offers`:

```json
{
  "kind": "product",
  "title": "Your published resource",
  "description": "What readers receive and who it helps.",
  "url": "https://your-real-checkout.example/resource"
}
```

Replace the example destination with your actual product before adding the entry. Use `affiliate` instead of `product` for a commissioned link; the site then adds a commission disclosure and `rel="sponsored"`. Up to six resources are supported. No resources are active by default.

Start with a clearly priced sponsorship or a useful paid research briefing. Display advertising income depends on audience, geography, demand and eligibility; it is not a guaranteed source of model funding. Compare actual receipts with the AI usage report before increasing the spending limit.

## Owner audit

Run `python scripts/audit_monetization.py` for a safe summary of current configuration. Never put an OpenAI key or private server key into site config, a payment URL, or this settings form.

References checked 8 September 2026: [GA4 Realtime](https://support.google.com/analytics/answer/9271392), [AdSense site readiness](https://support.google.com/adsense/answer/12169212), [ads.txt](https://support.google.com/adsense/answer/12171612), [Google consent API](https://developers.google.com/funding-choices/fc-api-docs).
