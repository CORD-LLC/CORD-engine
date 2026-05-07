# CORD Reference Dashboard

Single-file, dependency-free dashboard for visualizing CORD envelope EFS distributions, per-field loss patterns, and conformance gaps.

## What it does

Drop in a folder of `.cord.json` envelopes and inspect:

- **EFS distribution histogram** across all loaded envelopes
- **Per-field loss heatmap** showing which fields most often drop to PARTIAL or NONE
- **Sortable envelope list** with full loss reports per envelope
- **Filters** by domain, source system, and target system
- **Decimal / percentage display toggle** (decimal is canonical per the spec; percentage is presentation-only)
- **CSV export** of the filtered set

## Why it exists

The most common question from new CORD adopters is *"where do my metrics live?"* The answer per the spec is: *inside every envelope your system produces*. This dashboard exists so adopters have a working starting point for visibility — drop a folder of envelopes in and see exactly what the EFS section of the spec describes.

It is intentionally not a hosted service. CORD does not collect implementation metrics. This dashboard runs entirely in your browser; envelopes never leave your machine.

## How to use it

**Option 1 — Open directly:**

```sh
git clone https://github.com/CORD-LLC/CORD-engine.git
cd CORD-engine/dashboard
open dashboard.html   # or double-click in your file manager
```

**Option 2 — Serve locally (recommended for production-like testing):**

```sh
cd CORD-engine/dashboard
python3 -m http.server 8080
# then visit http://localhost:8080/dashboard.html
```

Once open, drop a folder or files of `.cord.json` envelopes onto the drop zone, or click *Load sample data* to see the dashboard populated with the four reference examples from the spec (healthcare, automotive, real-estate, hr).

## Input format

Any file matching the [CORD v1.0 envelope structure](https://cordspec.org/#envelope) is accepted. The dashboard reads:

- `envelope_id`, `domain`, `source_system`, `target_system`, `created_at` for filtering and display
- `loss_report.efs` for the EFS distribution and stats
- `loss_report.field_mappings[].field` and `.status` for the heatmap

Files may contain a single envelope or a JSON array of envelopes. Both `.json` and `.cord.json` extensions are accepted.

## What it deliberately does not do

- Compute EFS — the dashboard reads `loss_report.efs` from the envelope. EFS is computed at envelope-write time per the spec and never recomputed retroactively.
- Mutate envelopes — read-only.
- Send data anywhere — fully client-side, no network calls beyond the static page itself.

## Decimal vs percentage display

EFS is stored and exchanged as a decimal in `[0.0, 1.0]`. This is the canonical form referenced in the spec. The dashboard displays the decimal form by default and offers a percentage toggle for presentation. The underlying value is always the decimal — the toggle only changes the rendered string. This matches the [Display format](https://cordspec.org/#efs-display) rule in the EFS reference.

## License

Apache 2.0. Same as the rest of the engine repository and the specification.

## Contributing

Bug reports and PRs welcome via the [CORD-engine issue tracker](https://github.com/CORD-LLC/CORD-engine/issues). Substantive feature additions should be discussed in an issue first.
