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
    # --- Configuration ---
    # The base configuration to start from
    base_config_name = "germany_base"
    # The name for the new scenario
    scenario_config_name = "germany_scenario_1"
    cluster = "450"

    # Define home relative to the script's location
    home = "/home/lucakristin/Desktop"
    print(f"Home directory set to: {home}")

    # 1. Load the base network
    base_network_path = f"{home}/my_pypsa/pypsa-eur/resources/{base_config_name}/networks/base_s_{cluster}_elec_.nc"
    print(f"Loading base network from: {base_network_path}")
    n = pypsa.Network(base_network_path)

    # 2. Make a copy to create the scenario
    n_scenario = n.copy()

    # 3. Modify the network
    print("--- Applying modifications ---")
    modify_offshore_capacity(n_scenario, factor=2)
    modify_fossil_fuel_capacity(n_scenario, factor=0.1, latitude_quantile=0.75)
    modify_onshore_capacity(n_scenario, factor=1.5)

    # 4. Create the path for the output file
    output_path = f"{home}//my_pypsa/pypsa-eur/resources/{scenario_config_name}/networks/"
    os.makedirs(output_path, exist_ok=True)
    
    scenario_network_path = f"{output_path}base_s_{cluster}_elec_.nc"

    # 5. Export the modified network
    print(f"Exporting scenario network to: {scenario_network_path}")
    n_scenario.export_to_netcdf(scenario_network_path)
    print("Scenario network created successfully.")
