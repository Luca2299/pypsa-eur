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


def modify_carrier_capacity(network, carrier_name, new_capacity):
    chosen_generators = network.generators.index[network.generators.carrier == carrier_name]
    current_capacities = network.generators.loc[chosen_generators, "p_nom"]
    factor = new_capacity / current_capacities.sum()
    
    network.generators.loc[chosen_generators, "p_nom"] *= factor
    new_capacity_sum = network.generators.loc[chosen_generators, "p_nom"].sum()

    print(f"Modified '{carrier_name}' generator capacities from {current_capacities.sum():.2f} MW to {new_capacity_sum:.2f} MW.")

    return network


def main():

    
if __name__ == "__main__":
    main()