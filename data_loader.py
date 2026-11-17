"""
data_loader.py
--------------
Loads and cleans logged ECU engine telemetry data, bins data points into
the RPM x Load calibration grid, and derives baseline cell statistics
including sample densities and drivability torque floors.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd

RPM_POINTS = [1500, 2500, 3500, 4500, 5500, 6500]
LOAD_POINTS = [0.2, 0.4, 0.6, 0.8, 1.0]

@dataclass
class CellStats:
    rpm: int
    load: float
    sample_count: int
    mean_torque: float
    min_drivability_torque: float
    mean_fuel_flow: float
    mean_spark: float
    mean_afr: float
    mean_knock_margin: float


class EngineDataLoader:
    def __init__(self, csv_path: str = "engine_logged_dataset.csv"):
        self.csv_path = csv_path
        self.raw_df = None
        self.clean_df = None
        self.cell_stats: Dict[Tuple[int, float], CellStats] = {}
        self.grid_counts = np.zeros((len(RPM_POINTS), len(LOAD_POINTS)), dtype=int)
        
    def load_and_clean(self) -> pd.DataFrame:
        """Load CSV, validate columns, drop NaNs, and clean sensor anomalies."""
        self.raw_df = pd.read_csv(self.csv_path)
        
        # Verify required fields
        required_cols = {"rpm", "load", "spark_advance_deg", "afr", "torque_nm"}
        missing = required_cols - set(self.raw_df.columns)
        if missing:
            raise ValueError(f"Missing required columns in dataset: {missing}")
            
        # Fuel consumption column resolution
        if "fuel_flow_g_s" in self.raw_df.columns:
            self.raw_df["fuel_consumption"] = self.raw_df["fuel_flow_g_s"]
        elif "fuel_consumption" not in self.raw_df.columns:
            raise ValueError("No fuel consumption or fuel_flow_g_s column found.")
            
        # Drop invalid entries
        df = self.raw_df.dropna().copy()
        
        # Clean physical bounds
        df = df[
            (df["rpm"] >= 800) & (df["rpm"] <= 8000) &
            (df["load"] >= 0.05) & (df["load"] <= 1.20) &
            (df["spark_advance_deg"] >= 0.0) & (df["spark_advance_deg"] <= 45.0) &
            (df["afr"] >= 10.0) & (df["afr"] <= 20.0) &
            (df["torque_nm"] >= 0.0) & (df["torque_nm"] <= 350.0) &
            (df["fuel_consumption"] > 0.0)
        ]
        
        self.clean_df = df
        return self.clean_df
        
    def bin_to_grid(self, rpm_points=RPM_POINTS, load_points=LOAD_POINTS) -> Dict[Tuple[int, float], CellStats]:
        """Bin each data sample to the nearest RPM x Load grid node."""
        if self.clean_df is None:
            self.load_and_clean()
            
        df = self.clean_df.copy()
        
        # Calculate nearest grid point for each sample
        rpm_arr = np.array(rpm_points)
        load_arr = np.array(load_points)
        
        def find_nearest_rpm(val):
            idx = np.abs(rpm_arr - val).argmin()
            return rpm_arr[idx]
            
        def find_nearest_load(val):
            idx = np.abs(load_arr - val).argmin()
            return round(float(load_arr[idx]), 2)
            
        df["binned_rpm"] = df["rpm"].apply(find_nearest_rpm)
        df["binned_load"] = df["load"].apply(find_nearest_load)
        
        self.cell_stats.clear()
        self.grid_counts = np.zeros((len(rpm_points), len(load_points)), dtype=int)
        
        for i, r in enumerate(rpm_points):
            for j, l in enumerate(load_points):
                l_round = round(float(l), 2)
                cell_samples = df[(df["binned_rpm"] == r) & (df["binned_load"] == l_round)]
                count = len(cell_samples)
                self.grid_counts[i, j] = count
                
                if count > 0:
                    m_torque = float(cell_samples["torque_nm"].mean())
                    # Drivability floor: must deliver at least 92% of observed mean torque
                    # (or 10th percentile of logged cell torque) to preserve vehicle driveability
                    p10_torque = float(np.percentile(cell_samples["torque_nm"], 10))
                    min_floor = max(0.92 * m_torque, p10_torque, 10.0)
                    
                    stats = CellStats(
                        rpm=r,
                        load=l_round,
                        sample_count=count,
                        mean_torque=round(m_torque, 1),
                        min_drivability_torque=round(min_floor, 1),
                        mean_fuel_flow=round(float(cell_samples["fuel_consumption"].mean()), 3),
                        mean_spark=round(float(cell_samples["spark_advance_deg"].mean()), 2),
                        mean_afr=round(float(cell_samples["afr"].mean()), 2),
                        mean_knock_margin=round(float(cell_samples.get("knock_margin_deg", pd.Series([2.0])).mean()), 2)
                    )
                else:
                    stats = CellStats(
                        rpm=r,
                        load=l_round,
                        sample_count=0,
                        mean_torque=50.0 * l,
                        min_drivability_torque=45.0 * l,
                        mean_fuel_flow=0.5 * l,
                        mean_spark=15.0,
                        mean_afr=14.7,
                        mean_knock_margin=3.0
                    )
                self.cell_stats[(r, l_round)] = stats
                
        return self.cell_stats
        
    def print_density_report(self):
        """Displays a clean sporty ASCII report of sample binning."""
        if not self.cell_stats:
            self.bin_to_grid()
            
        print("\n" + "=" * 68)
        print("  🏁 ENGINE TELEMETRY BINNING & CELL DENSITY REPORT [CARBON-AI]  ")
        print("=" * 68)
        print(f"Total Valid Telemetry Samples: {len(self.clean_df):,}")
        print("\nSamples per [RPM x Load] Calibration Cell:")
        
        header = f"{'RPM / Load':>10} |" + "".join([f"{l:^10.1f}" for l in LOAD_POINTS])
        print("-" * len(header))
        print(header)
        print("-" * len(header))
        
        for i, r in enumerate(RPM_POINTS):
            row_str = f"{r:>8} RPM |"
            for j, l in enumerate(LOAD_POINTS):
                cnt = self.grid_counts[i, j]
                row_str += f"{cnt:^10d}"
            print(row_str)
            
        print("-" * len(header))
        print(f"{'Cell Mean:':>10} |" + "".join([f"{int(self.grid_counts.mean()):^10d}"]) * len(LOAD_POINTS))
        print("=" * 68 + "\n")


if __name__ == "__main__":
    loader = EngineDataLoader()
    loader.load_and_clean()
    loader.bin_to_grid()
    loader.print_density_report()
