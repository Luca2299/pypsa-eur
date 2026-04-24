"""
Creates a custom network scenario by modifying generator capacities.
"""

import pypsa
import pandas as pd
import numpy as np
import os

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

def modify_fossil_fuel_capacity(n: pypsa.Network, factor: float = 0.8, latitude_threshold: float = 47.5) -> None:
    """
    Modifies the nominal capacity of fossil fuel generators in the south.

    Parameters
    ----------
    n : pypsa.Network
        The PyPSA network to modify.
    factor : float, optional
        The factor by which to multiply the capacity, by default 0.8.
    latitude_threshold : float, optional
        The latitude threshold to define the southern region, by default 47.5.
    """
    print(f"Modifying fossil fuel capacity by a factor of {factor} for generators south of {latitude_threshold} degrees latitude")
    fossil_carriers = ['CCGT', 'gas', 'lignite', 'hard coal', 'coal', 'oil']
    
    # Define southern buses (example: south of 47.5 degrees latitude)
    buses = n.buses.index[n.buses.y < latitude_threshold]
    
    fossil_gens = n.generators.index[
        (n.generators.carrier.isin(fossil_carriers)) &
        (n.generators.bus.isin(buses))
    ]
    n.generators.loc[fossil_gens, 'p_nom'] *= factor

if __name__ == "__main__":
    # --- Configuration ---
    # The base configuration to start from
    base_config_name = "germany_base"
    # The name for the new scenario
    scenario_config_name = "germany_scenario_1"
    cluster = "450"

    # Define home relative to the script's location
    script_dir = os.path.dirname(__file__)
    home = os.path.abspath(os.path.join(script_dir, '..', '..'))
    print(f"Home directory set to: {home}")
    print(f"Skript directory: {script_dir}")

    # 1. Load the base network
    base_network_path = f"{home}/my_pypsa/pypsa-eur/resources/{base_config_name}/networks/base_s_{cluster}_elec_.nc"
    print(f"Loading base network from: {base_network_path}")
    n = pypsa.Network(base_network_path)

    # 2. Make a copy to create the scenario
    n_scenario = n.copy()

    # 3. Modify the network
    print("--- Applying modifications ---")
    modify_offshore_capacity(n_scenario, factor=2)
    modify_fossil_fuel_capacity(n_scenario, factor=0.3, latitude_threshold=47.5)
    modify_onshore_capacity(n_scenario, factor=1.5)

    # 4. Create the path for the output file
    output_path = f"{home}//my_pypsa/pypsa-eur/resources/{scenario_config_name}/networks/"
    os.makedirs(output_path, exist_ok=True)
    
    scenario_network_path = f"{output_path}base_s_{cluster}_elec_.nc"

    # 5. Export the modified network
    print(f"Exporting scenario network to: {scenario_network_path}")
    n_scenario.export_to_netcdf(scenario_network_path)
    print("Scenario network created successfully.")
