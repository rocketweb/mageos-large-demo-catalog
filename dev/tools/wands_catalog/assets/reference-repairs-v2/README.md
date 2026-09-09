# Selected reference repairs

These four synthetic lab catalog images were generated locally with MFLUX
`flux2-klein-4b`, 4-bit quantization, four steps, 768 by 768 pixels. The prompts
and seeds are in `../../reference-repairs.json` and `generation-events.jsonl`.
No cloud image-generation API was used.

All four were visually inspected against the intended corrections. All four,
plus the unchanged rug used in the bundle trial, passed the local
`Qwen3.8-27B-8bit` reference audit on September 4, 2026 using the v3 structured
response policy. `reference-audit.jsonl` retains the exact model verdicts,
source facts, image hashes and completion metadata. Machine-local paths in that
evidence identify the generation/audit inputs. The JPEG files are no longer
tracked in Git. Existing local copies remain intact, and their hashes match
the retained provenance records. Fresh clones receive this evidence only.

The local generation directory is `var/wands/reference-repairs-v2/`, relative
to the catalog repository root. A recipient must restore the exact JPEGs and
matching generation events from a separately supplied media archive, or
generate new candidates and re-audit them. No public media archive has been
published by this preparation work. Do not reuse a historic approval unless
the actual image bytes and all audit-policy inputs still match.

The table was refined after the first candidate's clipped corners were ambiguous.
The selected candidate clearly shows an eight-sided tabletop. The first candidate
and all original catalog images remain in their original local directories.

These are fictional product illustrations for the internal lab, not manufacturer
photography or proof of unobservable dimensions, functions, materials or compliance.
Generated downstream variants and bundles still require visual acceptance before
any later remote import.
