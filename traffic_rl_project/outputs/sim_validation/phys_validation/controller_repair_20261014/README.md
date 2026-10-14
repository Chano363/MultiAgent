# Controller repair experiment archives, 2026-10-14

This is an experimental evidence archive, not an accepted controller or a main-table evaluation. Production code does not import this directory.

37 completed diagnostic runs were copied from the extended and pressure archives. Empty or incomplete test directories were omitted. `publication_manifest.json` maps every copied file to its repository path, original local path, byte size and SHA256. Original result metadata and source snapshots remain unchanged.

- `extended/<run>/` and `pressure/<run>/`: result.json, trajectory.npz, trajectory.csv and the actual source snapshots available for that run.
- `*/reports/`: original review reports, including rejected candidates and known bottlenecks.
- `*/frozen_sources/`: historical diagnostic helpers, policy candidates and checks. These are for reproduction, not automatic deployment.
- `*/comparisons/`: comparisons and the route reference extracted from the supplied workbook.
- Figures: `../../figures/controller_repair_20261014/`, relative to this directory.

## Read and reproduce

Use the repository paths in the manifest; the D/E/F-drive paths in historical metadata are provenance, not portable runtime paths. Reports were copied without rewriting their historical links. Locate a report's referenced run under the corresponding `extended` or `pressure` group. Source hashes and diagnostic_protocol determine which runs can be compared. Old physical models must not be relabeled as the current model.

From traffic_rl_project, redraw the chase comparison without rerunning physics:

```sh
python src/evaluation/plot_low_level_control.py --before outputs/sim_validation/phys_validation/controller_repair_20261014/pressure/reset_baseline_02 --after outputs/sim_validation/phys_validation/controller_repair_20261014/pressure/chase_release_after_02 --output outputs/sim_validation/figures/controller_repair_20261014/chase_reproduced.png --title "Braking coordination under the same route conditions"
```

That chart uses requested air commands. For post-safety air inputs inspect trajectory.npz `ab_command_to_physics`; a command switch is not a fully released and recharged braking cycle. Pressure fields are normalized coefficients, not kPa. Some older runs lack these fields.

## Interpretation

The archived 120-second cyclic chart is a segment, not a completed full route or current final training result. The latest 60-second route-limit phase candidate worsened the peak (2359.654 to 2447.213 kN) and was rejected. The earlier chase candidate reduced force in a different protocol but worsened other metrics; it was also not adopted. Failures and mixed results are retained intentionally.

The route is rebased K15.9–K65.5 (49.6 km). The supplied workbook's ordinary 50 kPa reduction is not equivalent to the current SERVICE 140 kPa mapping. K40 conditional release and K42 summary release remain a reference discrepancy. Neither a completed four-phase controller nor a calibrated safety guarantee is claimed.
