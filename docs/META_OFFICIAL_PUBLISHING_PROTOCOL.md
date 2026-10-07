# Meta official publishing protocol

The protocol helpers are inert; the default provider registry remains unconfigured.
They require an explicit Graph API version, numeric account/object IDs and the
Facebook Login contract. Version formatting is not evidence that a version,
account, permissions or application has been accepted by Meta. No login path or
target account is guessed, and no OAuth acquisition occurs.

Instagram creates a REELS container against the configured account using an
authorized public HTTPS media URL and explicit `share_to_feed`. It reads the exact
container's status and requires an observed FINISHED status before building
`media_publish`. The observation retains its account/version binding and cannot
be published against another target. Missing status remains null; unfamiliar
bounded status is retained without becoming ready. Returned media IDs remain
observations, not invented URLs.
[Meta Instagram API collection](https://www.postman.com/meta/workspace/instagram/documentation/23987686-9386f468-7714-490f-9bfc-9442db5c8f00)

Facebook creates a Reel upload session, validates the returned official rupload
origin/version/video ID, sends bounded local bytes or an authorized hosted URL,
and separately builds the explicit finish operation. The upload uses OAuth header
authorization as documented; Graph calls keep the credential in an authorization
header, outside URLs. DRAFT and PUBLISHED must agree with the selected metadata;
a draft is not a privately published post. Upload/finish success is not collapsed
into completed publication. Processing/uploading/publishing phases and progress
remain null when absent, and exact object IDs are checked.
[Meta Facebook API collection](https://www.postman.com/meta/facebook/documentation/r56bjfd/facebook-api?entity=request-23987686-a9ea20fe-d410-4804-8bbe-5cc5985e9443)

The internal caption cap is 2,200 characters and local binary body cap is 16 MiB;
these are supported safety profiles, not claims about the latest vendor maxima.
Larger server media can use hosted transfer. Storage custody, availability, URL
lifetime and provider-side retrieval are separate acceptance requirements. Current
helpers reject unsupported schedules, thumbnails, privacy and login variants
rather than rewriting the requested behavior. No automatic retry or vendor
idempotency header is invented; unknown mutations require durable reconciliation
or review in the future adapter.

Only fixed official hosts are accepted. The existing HTTP layer retains disabled
network default, TLS verification, bounded bodies/responses, timeouts, no redirects,
no proxy/cookie reuse and private request logging filters. Raw provider messages
are excluded from normalized results; rate-limit delays are bounded. The public
HTTPS prefix helper is shared with the already-tested TikTok transfer component;
accepting a prefix does not verify its ownership or its service lifetime.

## Evidence and remaining work

153 selected protocol tests pass, including 37 new Meta cases and existing
TikTok/YouTube/HTTP checks. The first collection attempt contained invalid exception
chaining syntax in the new module; it was corrected before the passing run.
A seven-request MockTransport contract transfers the preserved 4,256,257-byte
synthetic portrait source exactly to the Facebook upload fixture, finishes a draft
and retains absent processing/publication observations. Instagram's mock container
flow separately observes FINISHED and a fixture media ID; actual hosted retrieval
is not tested. Four secret-free JSON exports are preserved. Actual costs are null
and no cost records, real credentials, provider request or paid operation exist.

Durable Meta consent/account binding, credential/permission checks, encrypted
session/intent ownership, cost admission, uncertainty reconciliation, supervised
scheduling, Native/Studio provider-specific controls, full metadata variants,
authorized storage retrieval and real provider acceptance remain incomplete.
Current developer reference pages were rate-limited; the linked official Meta
collections establish mock protocol contracts, not current production acceptance.
No real publish/delete, migration, accepted media replacement or deployment occurs.
