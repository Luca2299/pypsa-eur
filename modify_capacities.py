import argparse
from importlib.resources import path
import json
from time import ctime
from turtle import pd

from pandera import parser
import pypsa
import os

def load_network(home, folder, name, cluster):
    # Construct the path to the original base network in the 'resources' directory
    network_path = f"{home}/pypsa-eur/resources/{folder}{name}/networks/base_s_{cluster}_elec_.nc"
    original_path = f"{home}/pypsa-eur/resources/{folder}{name}/networks/base_s_{cluster}_elec_original.nc"

    if not os.path.exists(original_path):
        if not os.path.exists(network_path):
            print(f"ERROR: Base network file not found at {network_path}. Cannot load network.")
            return None
        else:
            n = pypsa.Network(network_path)
            n_original = n.copy()  # Keep a copy of the original network for comparison
            n_original.export_to_netcdf(original_path)
    else:
        n_original = pypsa.Network(original_path)
        n = n_original.copy()  # Load the original network for modification

    return n, network_path

def modify_carrier_capacity(network, carrier_name, new_capacity):
    chosen_generators = network.generators.index[network.generators.carrier == carrier_name]
    current_capacities = network.generators.loc[chosen_generators, "p_nom"]
    factor = new_capacity / current_capacities.sum()
    
    network.generators.loc[chosen_generators, "p_nom"] *= factor
    new_capacity_sum = network.generators.loc[chosen_generators, "p_nom"].sum()

    print(f"Modified '{carrier_name}' generator capacities from {current_capacities.sum():.2f} MW to {new_capacity_sum:.2f} MW.")

    return network

def modify_demand(network, scale_factor):
    if hasattr(network, "loads_t") and "p_set" in network.loads_t.columns and not network.loads_t.p_set.empty:
        current_total = network.loads_t.p_set.sum().sum()
        network.loads_t.p_set *= scale_factor
        network.loads["p_set"] = network.loads_t.p_set.mean(axis=0)
    else:
        current_total = network.loads["p_set"].sum()
        network.loads["p_set"] *= scale_factor

    print(f"Modified total demand from {current_total:.2f} MW to {network.loads['p_set'].sum():.2f} MW.")

    return network

def load_networks(home, cluster, base_folder, wind_condition, capacity_scenario):
    # --- BEGIN: Path Construction ---
    network_path = os.path.join(home, "pypsa-eur", "results", f"{base_folder}{wind_condition}", "networks", f"base_s_{cluster}_elec_.nc")

    export_folder = os.path.join(home, "pypsa-eur", "resources", f"{capacity_scenario}_{wind_condition}", "networks")
    os.makedirs(export_folder, exist_ok=True)
    export_path = os.path.join(export_folder, f"base_s_{cluster}_elec_.nc")

    config_path = os.path.join(home, "pypsa-eur", "config", "scenario_configs", f"{capacity_scenario}.json")
    # --- END: Path Construction ---

    # --- BEGIN: Load Network and Configuration ---
    print(f"[{ctime()}] Loading base network from: {network_path}")
    n_base = pypsa.Network(network_path)
    n_scenario = n_base.copy()  # Create a copy of the base network for modification
    
    print(f"[{ctime()}] Loading scenario configuration from: {config_path}")
    scenario_config = load_scenario_configuration(config_path)
    # --- END: Load Network and Configuration ---

    return n_scenario, export_path, scenario_config

def load_scenario_configuration(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as handle:
        return json.load(handle)
    
def create_scenario_network(network, scenario_config):
    if "capacity_modifications" in scenario_config:
        for carrier, new_capacity in scenario_config["capacities"].items():
            network = modify_carrier_capacity(network, carrier, new_capacity)
    
    if "demand" in scenario_config:
        demand_2025 = scenario_config["demand"].get("gross_TWh_2025", None)
        demand_2035 = scenario_config["demand"].get("gross_TWh_2035", None)

        if demand_2025 is not None and demand_2035 is not None:
            scale_factor = demand_2035 / demand_2025 
        else:
            print("Warning: Missing demand values in scenario configuration; skipping demand modification.")
            scale_factor = 1.0  # No scaling if values are missing
        network = modify_demand(network, scale_factor)
    
    return network


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

    # 1. Load the base network form the base-folder 
    n, export_path, scenario_config = load_networks(args.home, args.cluster, args.base_folder, args.wind_condition, args.capacity_scenario)
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
    #----------------------------------------

     # --- BEGIN: Export Scenario ---
    print(f"[{ctime()}] Exporting modified network to: {export_path}")
    n.export_to_netcdf(export_path)
    print(f"[{ctime()}] Scenario generation complete for {args.capacity_scenario} with {args.wind_condition}.")
    # --- END: Export Scenario ---

    
if __name__ == "__main__":
    main()