# Brief visitor count

The footer uses cumulative GA4 Total users for property 549530905, filtered to the exact hostname brief.hamelberg-ai.com, from 1 September 2026. It displays the report end date above the existing 1,000-user publication threshold. The initial saved report counted 287 users through 28 October 2026.

The repository workflow “Refresh Brief GA4 visitor total” requests one cumulative number daily at 05:39 UTC. The end date is two calendar days before the run in Europe/Amsterdam, allowing time for GA4 processing. A successful refresh updates the saved report and triggers the ordinary no-cost publication. An unavailable or incomplete report fails the workflow and preserves the last verified value.

## Enable the report

1. Enable the Google Analytics Data API in the Google Cloud project. Give the reporting service account the Viewer role on GA4 property 549530905.
2. Configure Google Cloud Workload Identity Federation for GitHub Actions. Restrict the trust to this repository and its main branch. Grant that workload permission to impersonate the reporting service account.
3. In the Brief repository's Actions variables, set GA4_WORKLOAD_IDENTITY_PROVIDER to the full provider resource name and GA4_READER_SERVICE_ACCOUNT to the reporting service account email. The workflow requests the analytics.readonly scope.
4. Run the workflow once. Inspect its result and the dated snapshot in config/site.json.

[Google Analytics Data API setup](https://developers.google.com/analytics/devguides/reporting/data/v1/quickstart-client-libraries) · [Google’s GitHub Actions authentication guide](https://github.com/google-github-actions/auth#workload-identity-federation-through-a-service-account)
