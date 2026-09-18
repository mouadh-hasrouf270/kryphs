# Provider capabilities

| Provider | Capability in this build | Verification |
| --- | --- | --- |
| Local storage | Signature/size-validated private uploads and authorized download | Unit/API tests |
| Google Drive | OAuth, refresh, inventory/change sync, ID reconciliation, root mappings, resumable copy of local masters | Mock-transport and identity tests; live account unverified |
| YouTube | Approved local master, persisted resumable state, privacy selection, confirmed video receipt | Mock-transport tests; live account unverified |
| Meta | Explicit token/account/version configuration, local video upload, ad creative, paused ad, durable step ledger | Safety tests; live publishing unverified |
| Meta performance | Daily ad insights for explicitly bound ad IDs; immutable normalized observations | Implementation present; live provider unverified |
| TikTok / Google Ads | Connection records and manual deployments/performance | Live sync/publishing not implemented; fail explicitly |

The production publishing registry contains only `MetaPublishingProvider`. There is no fallback mock. Browser Drive fixtures live under `backend/tests` and require DEBUG. They never authorize or perform network requests.

Configure Meta credentials through the connection's Credentials action: access token and a supported API version such as the version approved for your own app. The account ID is stored separately. Do not guess the provider version or use an expired token. The credentials endpoint is write-only and encrypts its input.

Each Meta step is marked running before sending its HTTP request. A confirmed response saves the real object ID. If a timeout/process crash occurs after the provider might have accepted a write, the step is uncertain and cannot be replayed automatically. Reconcile in the provider account with a qualified operator before creating another job. Publishing creates **paused** ads.

Provider receipts and credentials are omitted from general API records; step external IDs remain visible for authorized operations staff. HTTP calls have bounded timeouts and never run inside a long-lived database transaction.

The source module's deterministic ad adapter and mock AI provider were deliberately not included in the production registry. No external campaign/ad/video/file ID is generated to simulate success.
