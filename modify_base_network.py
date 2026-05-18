import argparse
from importlib.resources import path

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

def disable_line_extension(network, extendable_lines):
    if extendable_lines == False:
        if "s_nom_opt" in network.lines and not network.lines.s_nom.equals(network.lines.s_nom_opt):
            # Set s_nom_extendable to False
            for component in network.iterate_components(["Line", "Link"]):
                if "s_nom_extendable" in component.df.columns:
                    component.df["s_nom_extendable"] = False
            print("Line extension disabled: 's_nom_extendable' set to False for all lines and links.")
        else:
            print("No line extension detected or 's_nom_opt' column missing; no changes made to line extension settings.")
    return network
             

def modify_carrier_capacity(network, carrier_name, new_capacity):
    chosen_generators = network.generators.index[network.generators.carrier == carrier_name]
    current_capacities = network.generators.loc[chosen_generators, "p_nom"]
    factor = new_capacity / current_capacities.sum()
    
    network.generators.loc[chosen_generators, "p_nom"] *= factor
    new_capacity_sum = network.generators.loc[chosen_generators, "p_nom"].sum()

    print(f"Modified '{carrier_name}' generator capacities from {current_capacities.sum():.2f} MW to {new_capacity_sum:.2f} MW.")

    return network

def modify_coal_costs(network, factor):
    carrier_name = "coal"
    # Use the generators DataFrame directly to avoid deprecated APIs.
    if hasattr(network, "generators"):
        g = network.generators
        if "carrier" in g.columns and "marginal_cost" in g.columns:
            mask = g["carrier"] == carrier_name
            if mask.any():
                original_costs = g.loc[mask, "marginal_cost"].copy()
                g.loc[mask, "marginal_cost"] *= factor
                print(f"Modified marginal costs for '{carrier_name}' generators from {original_costs.iloc[0]:.2f} to {g.loc[mask, 'marginal_cost'].iloc[0]:.2f}.")
            else:
                print(f"No '{carrier_name}' generators found to modify costs.")
        else:
            print("Generator dataframe missing required columns; skipping coal cost modification.")
    else:
        print("No generator component found on the network; skipping coal cost modification.")
    return network


def main():
    # --- BEGIN: Argument Parsing ---
    parser = argparse.ArgumentParser(description="Create a custom network scenario for Germany.")
    parser.add_argument("--name", type=str, nargs='+', required=True, help="One or more wind conditions for the base network.")
    parser.add_argument("--folder", type=str, default="germany_base_", help="Base folder name (default: 'germany_base_').")
    parser.add_argument("--capacity", type=float, default=50000.0, help="Desired new capacity for the specified carrier in MW (default: 50000.0 MW).")
    parser.add_argument("--carrier", type=str, default="solar", help="Carrier name to modify (default: 'solar').")

    args = parser.parse_args()
    # --- END: Argument Parsing ---

    home = "/home/lucakristin/Desktop/my_pypsa"
    cluster = "450"
    folder = args.folder
    name = args.name[0]  # Take the first provided wind condition
    carrier_name = args.carrier
    new_capacity = args.capacity  # Desired new capacity in MW

    n, n_path = load_network(home, folder, name, cluster)
    n = modify_carrier_capacity(n, carrier_name, new_capacity)

    # Save the corrected network back to its original location
    n.export_to_netcdf(n_path)
    
if __name__ == "__main__":
    main()