import argparse
import json
import os
from time import ctime

import pandas as pd
import pypsa


def modify_carrier_capacity(network, carrier_name, new_capacity):
    chosen_generators = network.generators.index[network.generators.carrier == carrier_name]
    current_capacities = network.generators.loc[chosen_generators, "p_nom"]
    factor = new_capacity / current_capacities.sum()
    
    network.generators.loc[chosen_generators, "p_nom"] *= factor
    new_capacity_sum = network.generators.loc[chosen_generators, "p_nom"].sum()

    print(f"Modified '{carrier_name}' generator capacities from {current_capacities.sum():.2f} MW to {new_capacity_sum:.2f} MW.")

    return network

def modify_demand(network, scale_factor):
    # Scale either the time-series load profile or the static load snapshot.
    if hasattr(network.loads_t, "p_set") and not network.loads_t.p_set.empty:
        current_total = network.loads_t.p_set.sum().sum()
        network.loads_t.p_set *= scale_factor
        network.loads["p_set"] = network.loads_t.p_set.mean(axis=0)
        new_total = network.loads_t.p_set.sum().sum()
    else:
        current_total = network.loads["p_set"].sum()
        network.loads["p_set"] *= scale_factor
        new_total = network.loads["p_set"].sum()

    print(f"Modified total demand from {current_total:.2f} MW to {new_total:.2f} MW.")

    return network

def load_networks(home, cluster, base_folder, wind_condition, scenario_config_name, lines_setting):
    config_path = os.path.join(home, "pypsa-eur", "config", "scenario_configs", f"{scenario_config_name}.json")

    print(f"[{ctime()}] Loading scenario configuration from: {config_path}")
    scenario_config = load_scenario_configuration(config_path)
    scenario_name = scenario_config.get("name", "unknown_scenario")

    # --- BEGIN: Path Construction ---
    network_path = os.path.join(
        home,
        "pypsa-eur",
        "resources",
        f"{base_folder}_{wind_condition}",
        "networks",
        f"base_s_{cluster}_elec_.nc",
    )

    export_folder = os.path.join(home, "pypsa-eur", "resources", f"{scenario_name}-{lines_setting}_{wind_condition}", "networks")
    os.makedirs(export_folder, exist_ok=True)
    export_path = os.path.join(export_folder, f"base_s_{cluster}_elec_.nc")

    # --- BEGIN: Load Network and Configuration ---
    print(f"[{ctime()}] Loading base network from: {network_path}")
    n_base = pypsa.Network(network_path)
    n_scenario = n_base.copy()  # Create a copy of the base network for modification
    # --- END: Load Network and Configuration ---

    return n_scenario, export_path, scenario_config

def load_scenario_configuration(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as handle:
        return json.load(handle)
    
def create_scenario_network(network, scenario_config):
    if "capacities" in scenario_config:
        for carrier, new_capacity in scenario_config["capacities"].items():
            network = modify_carrier_capacity(network, carrier, new_capacity)
    
    if "demand" in scenario_config:
        demand_2025 = scenario_config["demand"].get("gross_TWh_2025", None)
        target_year = scenario_config.get("year")
        demand_target = scenario_config["demand"].get(f"gross_TWh_{target_year}", None) if target_year is not None else None

        if demand_2025 is not None and demand_target is not None:
            scale_factor = demand_target / demand_2025
        else:
            print("Warning: Missing demand values in scenario configuration; skipping demand modification.")
            scale_factor = 1.0  # No scaling if values are missing
        network = modify_demand(network, scale_factor)
    
    return network


def main():
     # --- BEGIN: Argument Parsing ---
    parser = argparse.ArgumentParser(description="Create a custom network scenario for Germany.")
    parser.add_argument("--wind-condition", type=str, required=True, help="Wind condition for the base network.")
    parser.add_argument("--scenario_config", type=str, required=True, help="Scenario configuration name without .json (e.g., 'germany_scenario2040').")
    parser.add_argument("--home", type=str, required=True, help="Home directory path.")
    parser.add_argument("--cluster", type=str, default="450", help="Number of clusters (default: 450).")
    parser.add_argument("--base-folder", type=str, default="germany_base_", help="Base folder name (default: 'germany_base_').")
    parser.add_argument("--lines-setting", type=str, default=None, help="Lines setting (default: None).")
    args = parser.parse_args()
    # --- END: Argument Parsing ---

    # 1. Load the base network form the base-folder 
    n, export_path, scenario_config = load_networks(args.home, args.cluster, args.base_folder, args.wind_condition, args.scenario_config, args.lines_setting)
    n = create_scenario_network(n, scenario_config)

    # 2. Print the installed capacity by carrier for the modified network
    component_specs = [("generators", "p_nom"), ("storage_units", "p_nom"), ("links", "p_nom")]
    carrier_capacity = pd.Series(dtype=float)

    for component_name, capacity_column in component_specs:
        component = getattr(n, component_name, None)
        if component is None or component.empty or "carrier" not in component.columns or capacity_column not in component.columns:
            continue
        carrier_capacity = carrier_capacity.add(component.groupby("carrier")[capacity_column].sum(), fill_value=0)

    carrier_capacity = carrier_capacity.sort_values(ascending=False)
    print(f"\n{n.name} installed capacity by carrier [MW]")
    if carrier_capacity.empty:
        print("  No carrier capacity found.")
    else:
        print(carrier_capacity.to_string(float_format=lambda value: f"{value:.2f}"))
    print(f"  Total capacity: {carrier_capacity.sum():.2f} MW")

    # print total demand for the modified network
    total_demand = n.loads["p_set"].sum()
    print(f"\n{n.name} total demand: {total_demand:.2f} MW")
    #----------------------------------------
    n.export_to_netcdf(export_path)
    
if __name__ == "__main__":
    main()