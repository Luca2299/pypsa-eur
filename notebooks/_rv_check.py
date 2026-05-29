# Auto-generated concatenation of code cells from Result_visualization.ipynb
# Created for linting/execution checks

import pypsa
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Dict, Tuple, Optional, List, Union
import warnings
import cartopy.crs as ccrs

# CO2 Emissions Analysis
summary_df = pd.read_csv("/home/lucakristin/Desktop/my_pypsa/pypsa-eur/summary_csv/new/summary_df.csv")
pivot_df = summary_df.pivot(index='scenario', columns='wind_condition', values='total_co2_emissions')
fig, ax = plt.subplots(figsize=(12, 8))
pivot_df.plot(kind='bar', stacked=True, ax=ax)
ax.set_ylabel("CO2 Emissions (tCO2)")
ax.set_xlabel("Scenario")
ax.set_title("CO2 Emissions by Scenario and Wind Condition")
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
# Note: plt.show() omitted for non-interactive lint run

# From NetCDFs
RESULTS_DIR = Path("/home/lucakristin/Desktop/my_pypsa/pypsa-eur/results")
NETWORK_FILENAME = "base_s_450_elec_.nc"
NETWORKS_SUBFOLDER = "networks"

def parse_network_directory_name(dir_name: str) -> Optional[Tuple[str, str, str]]:
    if not dir_name.startswith("germany_"):
        return None
    remainder = dir_name[8:]
    wind_conditions = ['notwindy', 'windy', 'windvariability']
    wind_condition = None
    for wc in wind_conditions:
        if remainder.endswith(wc):
            wind_condition = wc
            scenario_name = remainder[:-len(wc)-1]
            break
    if wind_condition is None:
        return None
    transmission_map = {
        'base': 'fixed',
        'base2': 'fixed',
        'scenario1': 'fixed',
        'scenario2': 'fixed',
        'scenario-ext': 'extendable + projects',
        'baseTP': 'projects',
        'base-ext': 'extendable',
        'scenario2040-TP': 'projects',
        'scenario2040-ext': 'extendable',
        'scenario2040-fixed': 'fixed'
    }
    transmission_setting = transmission_map.get(scenario_name, 'unknown')
    return (scenario_name, wind_condition, transmission_setting)


def load_networks_from_results(
    results_dir: Path = RESULTS_DIR,
    network_filename: str = NETWORK_FILENAME,
    networks_subfolder: str = NETWORKS_SUBFOLDER
) -> Dict[Tuple[str, str, str], pypsa.Network]:
    networks = {}
    for scenario_dir in sorted(results_dir.iterdir()):
        if not scenario_dir.is_dir():
            continue
        metadata = parse_network_directory_name(scenario_dir.name)
        if metadata is None:
            continue
        network_path = scenario_dir / networks_subfolder / network_filename
        if not network_path.exists():
            print(f"[WARNING] Network file not found: {network_path}")
            continue
        try:
            network = pypsa.Network()
            network.import_from_netcdf(str(network_path))
            networks[metadata] = network
        except Exception as e:
            print(f"[ERROR] {e}")
    return networks

# Load networks (may be slow or fail if files missing)
# Commented out to avoid heavy I/O during linting
# networks = load_networks_from_results()

# Line widths helper
import pandas as _pd

def set_line_widths(top_count, csv_dir, n):
    bottlenecks = _pd.read_csv(csv_dir + "/bottlenecks.csv")
    if top_count is None:
        top_count = len(bottlenecks)
    top_bottlenecks = bottlenecks[0:top_count]
    top_ids = top_bottlenecks['line_id'].astype(str)
    idx_str = n.lines.index.astype(str)
    line_widths = pd.Series(1, index=n.lines.index)
    line_widths[idx_str.isin(top_ids)] = 4
    return line_widths, bottlenecks[0:top_count]

# Example usage placeholders (not executed during lint)
# n = networks.get(('scenario2040-fixed', 'windy', 'fixed'))
# if n is not None:
#     line_widths, bottlenecks = set_line_widths(None, "/home/lucakristin/Desktop/my_pypsa/pypsa-eur/summary_csv", n)
