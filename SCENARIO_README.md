# Scenario Work Summary

Concise summary of recent scenario-related additions and analyses.

- **Files touched**: [pypsa-eur/create_germany_scenario.py](pypsa-eur/create_germany_scenario.py), [pypsa-eur/config/scenario_configs/germany_scenario.json](pypsa-eur/config/scenario_configs/germany_scenario.json), [pypsa-eur/config/config.germany_scenario.yaml](pypsa-eur/config/config.germany_scenario.yaml), [pypsa-eur/config/config.germany_base.yaml](pypsa-eur/config/config.germany_base.yaml), [pypsa-eur/notebooks/Comparing_Scenarios.ipynb](pypsa-eur/notebooks/Comparing_Scenarios.ipynb)

- **Keywords / Topics**: scenarios, capacity mix, capacity_scale, load modification, load shedding (marginal prices), plotting, line congestion, curtailment, energy balance, solver config, base configuration file

## What was implemented

- Scenario creation: `create_germany_scenario.py` copies a base network, applies capacity-mix rules and a global `capacity_scale`, and exports a scenario network into `resources/<scenario>/networks/`.
- Capacity-mix logic: normalization of input specs, handling of zero-share carriers, optional latitude bounds to restrict carrier modifications, and per-carrier target allocation to meet the scaled total capacity.
- Generator utilities: functions to adjust offshore, onshore, fossil-fuel (south-limited), and globally scale generator `p_nom` values.
- Load changes: `modify_load` to scale loads for buses in a geographic subset (latitude quantile), used to create demand-side scenario variants.

## Analysis & visualization (notebook)

- [Comparing_Scenarios.ipynb](pypsa-eur/notebooks/Comparing_Scenarios.ipynb) contains:
  - Line loading and congestion analysis (average and snapshot), colored network maps and difference plots, and latitude marker overlays.
  - Curtailment plots for offshore wind and stacked dispatch area charts by carrier (including battery discharge).
  - Pie charts of total energy production by carrier.
  - Per-bus energy balance, residual diagnostics (absolute, peak, relative), and top-bus residual reporting.
  - Use of bus marginal prices to size/color buses for congestion context.

## Solver & operational notes

- Scenario config enables solver `highs` and turns on `load_shedding` options; transmission project expansion is disabled in the scenario config to compare current topology.
- Snapshots in the example configs are limited to a single-day window to enable quick, focused diagnostics.

## Quick commands

Create a scenario network (example):

```bash
python pypsa-eur/create_germany_scenario.py --scenario-config-file pypsa-eur/config/scenario_configs/germany_scenario.json --home /home/lucakristin/Desktop/my_pypsa
```

Run solver (example using snakemake in the `pypsa-eur` directory):

```bash
cd pypsa-eur
snakemake -call solve_elec_networks --configfile config/config.germany_scenario.yaml
```

