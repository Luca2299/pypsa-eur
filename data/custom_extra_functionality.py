# SPDX-FileCopyrightText: : 2023- The PyPSA-Eur Authors
#
# SPDX-License-Identifier: MIT


def custom_extra_functionality(n, snapshots, snakemake):
    """
    Add custom extra functionality constraints.
    """
    # Optional runtime bias to prefer lignite over coal.
    # Enable by adding to your config under `bias: prefer_lignite: true`.
    bias_cfg = snakemake.config.get("bias", {}) if hasattr(snakemake, "config") else {}
    if not bias_cfg.get("prefer_lignite", False):
        return

    import numpy as _np

    g = n.generators
    if "carrier" not in g.columns:
        return

    coal_mask = g["carrier"] == "coal"
    lignite_mask = g["carrier"] == "lignite"
    if lignite_mask.sum() == 0:
        return

    # Ensure marginal_cost column exists
    if "marginal_cost" not in g.columns:
        g["marginal_cost"] = 0.0

    # Reference coal cost (mean of available coal marginal_costs)
    coal_mean = g.loc[coal_mask, "marginal_cost"].replace([_np.inf, -_np.inf], _np.nan).mean()
    if _np.isnan(coal_mean):
        coal_mean = g["marginal_cost"].replace([_np.inf, -_np.inf], _np.nan).mean()
    if _np.isnan(coal_mean):
        coal_mean = float(bias_cfg.get("default_coal_marginal_cost", 10.0))

    # Lower lignite marginal cost by delta (configurable)
    delta = float(bias_cfg.get("lignite_cost_delta", 5.0))
    new_lignite_cost = max(0.0, float(coal_mean) - delta)
    n.generators.loc[lignite_mask, "marginal_cost"] = new_lignite_cost

    # Optional: scale capital cost for lignite (factor <1 reduces cost)
    cap_factor = float(bias_cfg.get("lignite_capital_factor", 1.0))
    if "capital_cost" in g.columns and cap_factor != 1.0:
        n.generators.loc[lignite_mask, "capital_cost"] = (
            n.generators.loc[lignite_mask, "capital_cost"].fillna(0.0) * cap_factor
        )
