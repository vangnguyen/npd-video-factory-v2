# Native generation admission and protected factory

Native generation now has strict typed admission models and a protected factory over the existing provider-neutral ComfyUI adapter. These modules are not yet wired into the Native server, durable queue or Studio controls. They do not execute generation on import and do not certify Native generative completion.

The request selects image/video parameters, a saved project revision, exact source acknowledgment and a stable request key. References and an inpaint mask use only registered image IDs and SHA256, never client URLs, paths, graphs, model weights, provider results, costs or rights claims. Image contracts cover text-to-image, image-to-image, variation, inpaint and upscale; video contracts cover text-to-video, image-to-video and reference-assisted requests. Reference/mask/scale/mode relationships, finite duration, strict integer seed/scale and strict boolean acknowledgments are checked. Reference IDs are admission evidence; actual scoped byte lookup, rights admission and bridge staging remain to be connected.

The version-1 configuration is read once from a guarded bounded file outside the state root. It binds the Native workspace and optional bridge origin/token/enabled state. Duplicate keys, wrong workspace/version, extra fields, links and state-root secret storage reject with safe codes. Loading it does not enable calls; separate Owner enablement is required. Tokens remain private and only their digest enters the configuration fingerprint. The configured origin must be a local loopback or the existing isolated `comfyui-bridge` service with an explicit port, no credentials/path/query/fragment. No browser request can retarget an authenticated request.

The factory reuses the bridge's pure typed workflow/approved execution contracts without importing its HTTP server, database or jsonschema runtime into Native. It freezes the actual source manifest and graph hashes, validates unique workflow IDs and bounded guarded files, and requires Owner-reviewed metadata, matching graph SHA and executable node/output/binding structure before official configuration. Even enabled credentials cannot make the checked-in empty placeholders executable. It checks source manifest/graph fingerprints again before selection/adapter construction; drift fails before network. The independent bridge still performs full input schema, graph compilation, model/reference and GPU admission. A local static check does not certify an available GPU or working model.

Only a directly injected test `httpx.MockTransport` creates fixture factory mode. There is no registry fixture switch and no automatic fallback. Fixture use remains explicit in provider provenance, with unknown rights, ineligible production, unknown GPU/billed costs and real-provider-tested false. The factory supports existing trusted observation and exact cancellation callbacks; no keys/provider response bodies enter observations.

Seven Native contract cases cover all nine existing route combinations, strict native reference operations, protected registry/default-off behavior, origin/secret restrictions, duplicate/drift/empty reviewed graph guards and an explicit scoped lifecycle wire fixture. Temporary tokens/manifests are synthetic. No actual key, GPU, model, generated media/decode, payment, Owner UAT, external publication or deployment is used.

Next work: durable workspace/project-bound generation jobs and provider tickets/progress/cancellation/recovery, physical scoped references/rights/staging, independent worker/cost admission, full actual local result decoding, explicit attachment and Native Assets controls. Genuine approved executable workflows/models/GPU remain NOT_CONFIGURED until separately provisioned and accepted.

The independent bridge now has [reviewed HTTP execution](COMFYUI_HTTP_BACKEND.md)
and [physical reference staging](COMFYUI_REFERENCE_STAGING.md), with explicit
mock-wire/local-decode and new-process evidence. Native source lookup, actual
rights receipt issuance and service intake now have a tested
[Native source binding prerequisite](NATIVE_GENERATION_REFERENCES.md).
Native server queue/worker/cost/result/attachment/UI remain to be connected;
bridge availability does not establish Native mode readiness.
