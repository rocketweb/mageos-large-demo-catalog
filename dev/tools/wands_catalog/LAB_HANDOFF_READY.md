# Mage-OS Lab offline handoff

Subsequent distribution: the same rc2 profiles are now available through
[private GitHub release assets](GITHUB_RELEASE_PUBLISHED.md). The offline package
and historical preparation record below remain unchanged.

Prepared September 12, 2026. The private `2026.09.12-handoff-v3` package wraps the
unchanged starter and full rc2 profiles tested on Mage-OS 3.5.0. It adds the current
standalone tools and recipient instructions. This is a local handoff candidate,
not a public release or a new deployment.

## Package

Repository-relative directory: `var/wands/lab-handoff-20260912-v3/`.

Provide these four files together after sharing is approved:

- `START_HERE.md`: instructions, including verifier authentication.
- `manifest.json`: handoff inventory and the original profile pins.
- `release.py`: standalone verifier, authenticated before execution.
- `handoff.tar`: 2,337,249,280 bytes, containing 29 files.

The adjacent `manifest.sha256` and `build-summary.json` are conveniences, not
independent proof of authenticity. Transmit this handoff manifest SHA-256 through
a separately trusted channel:

```text
1589d02dc1019487181b7608ae19892362d49b9292972ce930927e314153e7f4
```

The wrapper includes both profiles, their separate catalog/module/media archives,
current verification/download/preflight tools, installation instructions, MIT
and CC0 notices, the original WANDS license and citation, and a portable 3.5.0
acceptance summary. No store credentials, database, vendor tree, theme package,
private server configuration or generation environment is included.

The preliminary `lab-handoff-20260912-v1` is superseded and must not be shared.
Its bootstrap instructions used Python assertions; a regression test showed
optimization could disable them. V2 uses explicit failure checks. The original
rc2 profile archives were unaffected.

V3 supersedes V2 with a corrected preflight: it also refuses an existing
`wands_catalog` store-group code, and missing catalog files fail quietly in the
log before Magento bootstrap. Instructions explicitly select the current
handoff preflight instead of the older one inside the immutable rc2 archives.
No catalog data, module behavior or rc2 archive bytes changed.

## Verification

- Full suite: 454 tests passed, including loopback HTTPS interruption/resume.
- Handoff tests cover deterministic archives, exact profile identity, corrupt
  inputs, output overwrite refusal, allowlisted contents and standalone commands.
- The documented bootstrap rejects wrong pins and modified verifier code even
  with Python optimization enabled.
- Preflight regression tests reproduced the missed store-group collision and
  noisy missing-file failures before the fix; both now pass. The database test
  double exposes only reads, and the failure cases perform no provisioning.
- The actual wrapper was authenticated and extracted in a separate temporary
  directory, with no dependency on the source checkout.
- Both actual enclosed profiles passed member verification and extraction using
  only the enclosed verifier. The standalone downloader starts successfully;
  the enclosed PHP preflight passes syntax validation.

See [the runtime acceptance record](LAB35_ACCEPTANCE.md) for the earlier Mage-OS
installation and storefront results. This follow-up performed offline packaging
and extraction, not another Magento installation or storefront test.

## Remaining decisions

The catalog can be handed over offline without a hosting service. Matt approved
the local source commit on September 12. Public hosting, upload, push and
publication remain separate, unperformed actions.
Import recovery is still restore-and-retry from an empty baseline, not resumable
or idempotent import. Mage-OS 3.4, clean-install Hyvä and checkout/payment support
have not been established by this acceptance.
