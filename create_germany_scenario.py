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
    

def modify_load(n: pypsa.Network, factor: float = 1.1, latitude_quantile: float = 0.25) -> None:
    """
    Modifies the load by multiplying it with a factor.

    Parameters
    ----------
    n : pypsa.Network
        The PyPSA network to modify.
    factor : float, optional
        The factor by which to multiply the load, by default 1.1.
    latitude_quantile : float, optional
        The quantile to define the southern region, by default 0.25 (bottom 25%).
    """
    print(f"Modifying load by a factor of {factor}")
    
    # Calculate the latitude threshold from the quantile
    latitude_threshold = n.buses.y.quantile(latitude_quantile)
    print(f"Modifying load for buses south of latitude {latitude_threshold:.2f} ({latitude_quantile:.0%} quantile).")
    
    # Define buses based on the calculated threshold
    buses = n.buses.index[n.buses.y < latitude_threshold]
    loads = n.loads.index[n.loads.bus.isin(buses)]
    print(f"Found {len(loads)} loads in the south to modify.")
    summed_load = n.loads.loc[loads, "p_set"].sum()
    
    # Modify the load
    n.loads.loc[loads, "p_set"] *= factor
    summed_load_modified = n.loads.loc[loads, "p_set"].sum()
    print(f"Base load in the south: {summed_load / factor:.2f} MW")
    print(f"Total modified load in the south: {summed_load_modified:.2f} MW")

def modify_offshore_capacity(n: pypsa.Network, factor: float = 1.2) -> None:
    """
    Modifies the nominal capacity of offshore wind generators.

    Parameters
    ----------
    n : pypsa.Network
        The PyPSA network to modify.
    factor : float, optional
        The factor by which to multiply the capacity, by default 1.2.
    """
    print(f"Modifying offshore capacity by a factor of {factor}")
    offshore_carriers = ["offwind-ac", "offwind-dc"]
    offshore_gens = n.generators.index[n.generators.carrier.isin(offshore_carriers)]
    n.generators.loc[offshore_gens, "p_nom"] *= factor

def modify_onshore_capacity(n: pypsa.Network, factor: float = 1.2) -> None:
    """
    Modifies the nominal capacity of onshore wind generators.

    Parameters
    ----------
    n : pypsa.Network
        The PyPSA network to modify.
    factor : float, optional
        The factor by which to multiply the capacity, by default 1.2.
    """
    print(f"Modifying onshore capacity by a factor of {factor}")
    onshore_carriers = ["onwind"]
    onshore_gens = n.generators.index[n.generators.carrier.isin(onshore_carriers)]
    n.generators.loc[onshore_gens, "p_nom"] *= factor


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
    print("Modifying generator capacity mix while keeping the total capacity constant.")
    print(f"Current total capacity of selected carriers: {total_current_capacity:.2f} MW")

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
        target_capacity = total_current_capacity * normalized_share
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

        print(
            f"Carrier '{carrier}': current {current_capacity:.2f} MW -> target {target_capacity:.2f} MW "
            f"({normalized_share:.1%} share); selected band {selected_capacity:.2f} MW -> "
            f"{target_selected_capacity:.2f} MW (factor {scale_factor:.4f})"
        )

        n.generators.loc[selected, "p_nom"] *= scale_factor

    modified_total_capacity = sum(
        float(n.generators.loc[carrier_to_generators[carrier], "p_nom"].sum())
        for carrier in carriers_to_modify
    )
    print(f"Modified total capacity of selected carriers: {modified_total_capacity:.2f} MW")

def modify_fossil_fuel_capacity(n: pypsa.Network, factor: float = 0.8, latitude_quantile: float = 0.25) -> None:
    """
    Modifies the nominal capacity of fossil fuel generators in the south, defined by a latitude quantile.

    Parameters
    ----------
    n : pypsa.Network
        The PyPSA network to modify.
    factor : float, optional
        The factor by which to multiply the capacity, by default 0.8.
    latitude_quantile : float, optional
        The quantile to define the southern region, by default 0.25 (bottom 25%).
    """
    fossil_carriers = ['CCGT', 'OCGT', 'gas', 'lignite', 'hard coal', 'coal', 'oil']
    
    # First, find all fossil fuel generators to determine the latitude threshold
    fossil_gens_all = n.generators[n.generators.carrier.isin(fossil_carriers)]
    fossil_gens_locations = fossil_gens_all.join(n.buses, on='bus', rsuffix='_bus')
    
    if fossil_gens_locations.empty:
        print("No fossil fuel generators found in the network.")
        return

    # Calculate the latitude threshold from the quantile
    latitude_threshold = fossil_gens_locations['y'].quantile(latitude_quantile)
    
    print(f"Modifying fossil fuel capacity by a factor of {factor} for generators south of latitude {latitude_threshold:.2f} ({latitude_quantile:.0%} quantile).")

    # Define southern buses based on the calculated threshold
    buses = n.buses.index[n.buses.y < latitude_threshold]
    
    fossil_gens = n.generators.index[
        (n.generators.carrier.isin(fossil_carriers)) &
        (n.generators.bus.isin(buses))
    ]

    print(f"Found {len(fossil_gens)} fossil fuel generators in the south to modify.")

    summed_capacity = n.generators.loc[fossil_gens, "p_nom"].sum()
    n.generators.loc[fossil_gens, "p_nom"] *= factor
    summed_capacity_modified = n.generators.loc[fossil_gens, "p_nom"].sum()

    print(f"Base fossil fuel capacity in the south: {summed_capacity / factor:.2f} MW")
    print(f"Total modified fossil fuel capacity in the south: {summed_capacity_modified:.2f} MW")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a modified scenario network from a base network."
    )
    parser.add_argument("--base-config-name", default="germany_base")
    parser.add_argument("--scenario-config-name", default="germany_scenario_1")
    parser.add_argument("--cluster", default="450")
    parser.add_argument("--home", default="/home/lucakristin/Desktop")
    parser.add_argument("--scenario-config-file", default=None)
    args = parser.parse_args()

    # --- Configuration ---
    # The base configuration to start from
    scenario_config = {}
    if args.scenario_config_file:
        print(f"Loading scenario config from: {args.scenario_config_file}")
        scenario_config = load_scenario_configuration(args.scenario_config_file)

    base_config_name = scenario_config.get("base_config_name", args.base_config_name)
    # The name for the new scenario
    scenario_config_name = scenario_config.get("scenario_config_name", args.scenario_config_name)
    cluster = str(scenario_config.get("cluster", args.cluster))
    capacity_mix = scenario_config.get("capacity_mix", {})


    # 1. Load the base network
    home = args.home
    base_network_path = f"{home}/pypsa-eur/resources/{base_config_name}/networks/base_s_{cluster}_elec_.nc"
    print(f"Loading base network from: {base_network_path}")
    n = pypsa.Network(base_network_path)

    # 2. Make a copy to create the scenario
    n_scenario = n.copy()

    # 3. Modify the network
    print("--- Applying modifications ---")
    modify_generator_capacity_mix(n_scenario, target_mix=capacity_mix)

    # 4. Create the path for the output file
    output_path = f"{home}/pypsa-eur/resources/{scenario_config_name}/networks/"
    os.makedirs(output_path, exist_ok=True)
    
    scenario_network_path = f"{output_path}base_s_{cluster}_elec_.nc"

    # 5. Export the modified network
    print(f"Exporting scenario network to: {scenario_network_path}")
    n_scenario.export_to_netcdf(scenario_network_path)
    print("Scenario network created successfully. On " + ctime())
