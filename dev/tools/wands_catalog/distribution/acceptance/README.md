# Private Mage-OS 3.5 acceptance instance

This is the operator harness for the explicitly approved test instance on comtom,
not a portable Mage-OS installer. Its PHP image is a pinned runtime already on that
server. Community recipients should use the portable module and distribution
guide, not these machine-specific files.

## Isolation

- Root: `/opt/comtom/wands-lab35-acceptance` on `37.27.126.105`.
- Compose project: `wands-lab35-acceptance`, with a dedicated network.
- Four containers: PHP 8.4, MariaDB 11.4, stock OpenSearch 3.1.0 and nginx.
- Fresh `mage-os/project-community-edition` 3.5.0 from the Mage-OS repository.
- No demo database, Composer credentials, vendor tree or theme copied.
- Only published port: `127.0.0.1:18035`. No edge proxy, public DNS or TLS changes.
- PHP, database and search have separate CPU/memory limits.

The starter uses `lab_starter`. Its original empty database is backed up privately
to `receipts/empty-before-module.sql`. The full profile uses a newly created
`lab_full` database populated from that empty baseline. The starter database is
not deleted, and its previous application configuration is retained privately in
`receipts/starter-env.php` with mode 0600. Generated credentials remain only in the
server's mode-0600 `.env` file. Do not download or publish these files.

## Access and logs

Create a local tunnel when inspecting the remote store:

```sh
ssh -N -L 18035:127.0.0.1:18035 root@37.27.126.105
```

Then open `http://127.0.0.1:18035/`. Magento and its catalog remain on the server.

Read `bootstrap-state.json`, `starter-state.json` or `full-state.json` for the
current phase. Detailed command output goes to `bootstrap.log` and `receipts/`.
For example, on the server:

```sh
cd /opt/comtom/wands-lab35-acceptance
tail -f receipts/full-1-simple.log
```

Scripts refuse to restart a previously attempted profile automatically. Diagnose
the recorded phase before resuming; these are not general idempotent installers.
`verify_profile.php` performs read-only field, stock, relationship and media-hash
checks against the exact staged data. It does not interpret a raw stock flag as
availability when the product explicitly disables stock management; storefront
checks separately exercise composite availability and pricing.

For enriched candidates, deploy `enrichment_checks.php` beside
`verify_profile.php`. The verifier detects specification columns or enrichment
coverage and additionally compares store-zero descriptions, URL keys, every
specification value, the synthetic disclosure and exact related/cross-sell links.
Select labels are resolved through options belonging to the correct attribute.
Missing values, unexpected populated fields and missing/extra links fail the run.
The report records `enrichment_checked` and `enrichment_checks`; an older rc2 run
does not provide evidence for these checks. Frontend rendering still needs browser
acceptance, including store-view overrides and configurable selections.

The [enriched acceptance plan](ENRICHED_ACCEPTANCE_PLAN.md) proposes a new isolated
remote fixture. The existing populated fixture is not its import destination.

## Stop without deleting data

From the exact acceptance root, `docker compose stop` stops only this project.
Retain its database directories, original baseline and profile receipts. No
cleanup, database deletion, migration of the demo, public release or source push
is implied by acceptance testing.
