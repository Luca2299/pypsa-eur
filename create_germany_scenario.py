"""
Creates a custom network scenario by modifying generator capacities.
"""

import argparse
import json
from time import ctime

import pypsa
import pandas as pd
import numpy as np
import os


def load_scenario_configuration(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as handle:
        return json.load(handle)

def reduce_generator_capacity(n: pypsa.Network, factor: float) -> None:
    """Scale all generator nameplate capacities by a global factor."""
    if factor <= 0:
        raise ValueError("capacity_scale must be greater than 0.")
    n.generators.loc[:, "p_nom"] *= factor

def _normalize_capacity_mix(
    target_mix: dict[str, dict[str, float | None]] | list[tuple[str, float]],
) -> dict[str, dict[str, float | None]]:
    """Normalize legacy and new capacity-mix inputs to a common structure."""
    if isinstance(target_mix, list):
        return {carrier: {"share": float(share), "min_latitude": None, "max_latitude": None} for carrier, share in target_mix}

    normalized_mix: dict[str, dict[str, float | None]] = {}
    for carrier, spec in target_mix.items():
        if isinstance(spec, (int, float)):
            normalized_mix[carrier] = {"share": float(spec), "min_latitude": None, "max_latitude": None}
            continue

        if not isinstance(spec, dict):
            raise TypeError(f"Capacity mix entry for '{carrier}' must be a number or a dictionary.")

        share = spec.get("share", spec.get("percentage"))
        if share is None:
            raise ValueError(f"Capacity mix entry for '{carrier}' must define 'share' or 'percentage'.")

        normalized_mix[carrier] = {
            "share": float(share),
            "min_latitude": spec.get("min_latitude", spec.get("min_lat")),
            "max_latitude": spec.get("max_latitude", spec.get("max_lat")),
        }

    return normalized_mix


def modify_generator_capacity_mix(
    n: pypsa.Network,
    target_mix: dict[str, dict[str, float | None]] | list[tuple[str, float]],
    capacity_scale: float = 1.0,
    target_total_capacity: float | None = None,
) -> None:
    """
    Modify generator capacities so the installed capacity mix matches target shares.

    The input is a dictionary keyed by carrier name. Each entry contains a
    target share of the total installed capacity and optional latitude bounds.
    If ``min_latitude`` and ``max_latitude`` are given, only generators whose
    bus latitude falls inside that band are modified. If either bound is missing,
    all generators of that carrier are modified.

    Parameters
    ----------
    n : pypsa.Network
        The PyPSA network to modify.
    target_mix : dict[str, dict[str, float | None]] | list[tuple[str, float]]
        Target shares and optional latitude bounds for each carrier.
    """
    if not target_mix:
        print("No target shares provided; skipping capacity mix modification.")
        return

    normalized_mix = _normalize_capacity_mix(target_mix)
    share_map = {carrier: spec["share"] for carrier, spec in normalized_mix.items() if spec["share"] > 0}
    total_share = sum(share_map.values())
    if total_share <= 0:
        print("Target shares must sum to a positive value; skipping modification.")
        return

    zero_share_carriers = [carrier for carrier, spec in normalized_mix.items() if spec["share"] <= 0]
    if zero_share_carriers:
        zero_share_mask = n.generators.carrier.isin(zero_share_carriers)
        zero_share_capacity = float(n.generators.loc[zero_share_mask, "p_nom"].sum())
        if zero_share_capacity > 0:
            print(
                f"Removing capacity from zero-share carriers {zero_share_carriers}: "
                f"{zero_share_capacity:.2f} MW"
            )
        n.generators.loc[zero_share_mask, "p_nom"] = 0.0

    carrier_to_generators: dict[str, pd.Index] = {}
    current_capacities: dict[str, float] = {}
    for carrier_name in normalized_mix:
        generators = n.generators.index[n.generators.carrier == carrier_name]
        carrier_to_generators[carrier_name] = generators
        current_capacities[carrier_name] = float(n.generators.loc[generators, "p_nom"].sum())

    carriers_to_modify = [carrier for carrier in share_map if carrier in carrier_to_generators]
    if not carriers_to_modify:
        print("No matching carriers with positive target shares were found; skipping modification.")
        return

    total_current_capacity = sum(current_capacities.get(carrier, 0.0) for carrier in carriers_to_modify)
    if target_total_capacity is None:
        target_total_capacity = total_current_capacity * capacity_scale

    print(f"Current total capacity of selected carriers: {total_current_capacity:.2f} MW")
    print(f"Scale capacity of selected carriers by {capacity_scale:.3f} to {target_total_capacity:.2f} MW")

    for carrier in carriers_to_modify:
        spec = normalized_mix[carrier]
        current_capacity = current_capacities[carrier]
        generators = carrier_to_generators[carrier]
        if current_capacity <= 0:
            print(f"Carrier '{carrier}' has no installed capacity in the base network; skipping.")
            continue

        carrier_locations = n.generators.loc[generators].join(n.buses, on="bus", rsuffix="_bus")

        min_latitude = spec["min_latitude"]
        max_latitude = spec["max_latitude"]
        if min_latitude is not None or max_latitude is not None:
            if min_latitude is None or max_latitude is None:
                print(f"Carrier '{carrier}' is missing one latitude bound; applying the modification to all generators of that carrier.")
                selected = generators
            else:
                min_latitude = float(min_latitude)
                max_latitude = float(max_latitude)
                selected = carrier_locations.index[
                    (carrier_locations["y"] > min_latitude) & (carrier_locations["y"] < max_latitude)
                ]
        else:
            selected = generators

        if len(selected) == 0:
            print(
                f"Warning: carrier '{carrier}' has 0 generators with latitude between "
                f"{min_latitude} and {max_latitude}; skipping."
            )
            continue

        selected_capacity = float(n.generators.loc[selected, "p_nom"].sum())
        outside_capacity = current_capacity - selected_capacity

        normalized_share = share_map[carrier] / total_share
        target_capacity = target_total_capacity * normalized_share
        target_selected_capacity = target_capacity - outside_capacity

        if target_selected_capacity < 0:
            raise ValueError(
                f"Carrier '{carrier}' cannot reach the requested target share because the fixed capacity "
                f"outside the latitude band already exceeds the target."
            )

        if selected_capacity <= 0:
            if target_selected_capacity == 0:
                print(f"Carrier '{carrier}' has zero capacity in the selected band and needs no change.")
                continue
            raise ValueError(f"Carrier '{carrier}' has no modifiable capacity in the selected latitude band.")

        scale_factor = target_selected_capacity / selected_capacity

        print(f"{carrier}: modified from {selected_capacity:.2f} MW to {target_selected_capacity:.2f} MW")

        n.generators.loc[selected, "p_nom"] *= scale_factor

    modified_total_capacity = sum(
        float(n.generators.loc[carrier_to_generators[carrier], "p_nom"].sum())
        for carrier in carriers_to_modify
    )
    print(f"Modified total capacity of selected carriers: {modified_total_capacity:.2f} MW")


def main():
    # --- BEGIN: Argument Parsing ---
    parser = argparse.ArgumentParser(description="Create a custom network scenario for Germany.")
    parser.add_argument("--wind-condition", type=str, nargs='+', required=True, help="One or more wind conditions for the base network.")
    parser.add_argument("--capacity-scenario", type=str, nargs='+', required=True, help="One or more capacity scenarios (e.g., 'germany_scenario1').")
    parser.add_argument("--home", type=str, required=True, help="Home directory path.")
    parser.add_argument("--cluster", type=str, default="450", help="Number of clusters (default: 450).")
    parser.add_argument("--base-folder", type=str, default="germany_base_", help="Base folder name (default: 'germany_base_').")
    args = parser.parse_args()
    # --- END: Argument Parsing ---

    for capacity_scenario in args.capacity_scenario:
        for wind_condition in args.wind_condition:
            print(f"[{ctime()}] Processing scenario: {capacity_scenario} with wind condition: {wind_condition}")

            # --- BEGIN: Path Construction ---
            network_path = os.path.join(args.home, "pypsa-eur", "results", f"{args.base_folder}{wind_condition}", "networks", f"base_s_{args.cluster}_elec_.nc")
            
            export_folder = os.path.join(args.home, "pypsa-eur", "resources", f"{capacity_scenario}_{wind_condition}", "networks")
            os.makedirs(export_folder, exist_ok=True)
            export_path = os.path.join(export_folder, f"base_s_{args.cluster}_elec_.nc")

            config_path = os.path.join(args.home, "pypsa-eur", "config", "scenario_configs", f"{capacity_scenario}.json")
            # --- END: Path Construction ---

            # --- BEGIN: Load Network and Configuration ---
            print(f"[{ctime()}] Loading base network from: {network_path}")
            n = pypsa.Network(network_path)
            
            print(f"[{ctime()}] Loading scenario configuration from: {config_path}")
            scenario_config = load_scenario_configuration(config_path)
            # --- END: Load Network and Configuration ---

            extendable_lines = scenario_config.get("extendable_lines", False)

            if not extendable_lines:
                is_non_extendable = True
                for component in n.iterate_components(["Line", "Link"]):
                    if "s_nom_extendable" not in component.df or component.df["s_nom_extendable"].any():
                        is_non_extendable = False
                        break
                
                if is_non_extendable:
                    print(f"[{ctime()}] Lines of network {network_path} are already not extendable.")
                else:
                    print(f"[{ctime()}] Setting 's_nom_extendable' to False on base network and saving.")
                    for component in n.iterate_components(["Line", "Link"]):
                        component.df["s_nom_extendable"] = False
                    n.export_to_netcdf(network_path)
                n_scenario = n.copy()
            else:
                n_scenario = n.copy()

            # --- BEGIN: Network Modification ---
            print(f"[{ctime()}] Modifying generator capacities for scenario '{capacity_scenario}'.")
            modify_generator_capacity_mix(
                n_scenario,
                target_mix=scenario_config["capacity_mix"],
                capacity_scale=float(scenario_config.get("capacity_scale", 1.0)),
            )

            print(f"[{ctime()}] Setting line property 's_nom_extendable' to {extendable_lines}.")
            for component in n_scenario.iterate_components(["Line", "Link"]):
                component.df["s_nom_extendable"] = extendable_lines
            # --- END: Network Modification ---

            # --- BEGIN: Export Scenario ---
            print(f"[{ctime()}] Exporting modified network to: {export_path}")
            n_scenario.export_to_netcdf(export_path)
            print(f"[{ctime()}] Scenario generation complete for {capacity_scenario} with {wind_condition}.")
            # --- END: Export Scenario ---

if __name__ == "__main__":
    main()