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

def set_generator_capacities_from_dataframe(
    n: pypsa.Network,
    capacity_df: pd.DataFrame,
    capacity_column: str = "p_nom",
) -> tuple[pypsa.Network, pd.DataFrame]:
    """Set generator capacities from a dataframe and return a before/after summary."""
    if capacity_column not in capacity_df.columns:
        raise ValueError(f"capacity_df must contain a '{capacity_column}' column.")

    current = n.generators.loc[capacity_df.index, ["p_nom"]].rename(columns={"p_nom": "before"})
    updated = capacity_df[[capacity_column]].rename(columns={capacity_column: "after"})
    summary = current.join(updated)
    summary["difference"] = summary["after"] - summary["before"]

    n.generators.loc[capacity_df.index, "p_nom"] = capacity_df[capacity_column].astype(float)
    return n, summary

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