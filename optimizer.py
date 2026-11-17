"""
optimizer.py
------------
ECU Calibration Optimizer retargeted for Fuel Economy (BSFC / Fuel Flow minimization).
Performs global search via scipy.optimize.differential_evolution per RPM x Load cell to
find the optimal spark advance and AFR that MINIMIZE fuel consumption while strictly
enforcing:
  1. Minimum drivability torque floor (derived from logged operational requirement)
  2. Safe knock margin (>= 1.0 deg BTDC below knock limit)
  3. Load-dependent safe AFR limits (lean-burn cruise 15.0–16.5 at light loads,
     stoich at mid-load, and thermal-protective enrichment at high loads)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy.optimize import differential_evolution

from learned_model import (
    learned_torque_nm,
    learned_fuel_consumption,
    learned_knock_margin,
    get_learned_model
)
from data_loader import EngineDataLoader, CellStats

# Global safety limits
SPARK_BOUNDS = (5.0, 34.0)
MIN_KNOCK_MARGIN_DEG = 1.0  # Must stay at least 1.0 deg below knock limit


def get_safe_afr_bounds(load: float) -> Tuple[float, float]:
    """
    Returns safe AFR optimization bounds tailored to engine load:
      - Cruise / light load (<= 0.40): Lean-for-economy cruise up to 16.5:1
      - Mid load (0.40 - 0.70): Stoichiometric transition (13.2 - 15.2:1)
      - High load / WOT (> 0.70): Safe enrichment (11.8 - 13.2:1) to keep EGT safe
    """
    if load <= 0.30:
        return (14.5, 16.5)
    elif load <= 0.45:
        return (14.0, 16.2)
    elif load <= 0.70:
        return (13.0, 15.0)
    elif load <= 0.85:
        return (12.2, 13.5)
    else:
        return (11.6, 12.8)


@dataclass
class EconomyCellResult:
    rpm: int
    load: float
    spark_advance: float
    afr: float
    torque_nm: float
    min_torque_floor: float
    fuel_flow_g_s: float
    baseline_fuel_flow: float
    fuel_saved_pct: float
    knock_margin_deg: float


# Backward-compatible alias
CellResult = EconomyCellResult


def _economy_objective(x, rpm: float, load: float, min_torque_floor: float):
    spark_advance, afr = x
    
    # Predict torque and fuel consumption using learned ML model
    pred_torque = learned_torque_nm(rpm, load, spark_advance, afr)
    pred_fuel = learned_fuel_consumption(rpm, load, spark_advance, afr)
    margin = learned_knock_margin(spark_advance, rpm, load, afr)
    
    penalty = 0.0
    
    # 1. Knock safety constraint (hard penalty)
    if margin < MIN_KNOCK_MARGIN_DEG:
        penalty += 2000.0 * (MIN_KNOCK_MARGIN_DEG - margin) ** 2
        
    # 2. Drivability torque floor constraint (hard penalty)
    # The car must still produce sufficient torque to climb hills / maintain cruising speed
    if pred_torque < min_torque_floor:
        penalty += 1500.0 * ((min_torque_floor - pred_torque) / max(min_torque_floor, 1.0)) ** 2
        
    # Objective: Minimize fuel consumption (g/s) + constraint penalties
    return pred_fuel + penalty


def optimize_economy_cell(
    rpm: int,
    load: float,
    cell_stat: Optional[CellStats] = None,
    seed: int = 42
) -> EconomyCellResult:
    """Run differential evolution to find the fuel-optimal calibration for one cell."""
    load_round = round(float(load), 2)
    afr_bounds = get_safe_afr_bounds(load_round)
    bounds = [SPARK_BOUNDS, afr_bounds]
    
    # Determine minimum required drivability torque
    if cell_stat is not None and cell_stat.sample_count > 0:
        min_torque_floor = cell_stat.min_drivability_torque
        baseline_fuel = cell_stat.mean_fuel_flow
    else:
        # Fallback estimation if no empirical samples
        min_torque_floor = max(40.0 * load_round, 12.0)
        baseline_fuel = 0.6 * load_round * (rpm / 1500.0)
        
    res = differential_evolution(
        _economy_objective,
        bounds,
        args=(rpm, load_round, min_torque_floor),
        seed=seed,
        maxiter=70,
        popsize=18,
        tol=1e-6,
        polish=True
    )
    
    opt_spark, opt_afr = res.x
    opt_torque = learned_torque_nm(rpm, load_round, opt_spark, opt_afr)
    opt_fuel = learned_fuel_consumption(rpm, load_round, opt_spark, opt_afr)
    opt_margin = learned_knock_margin(opt_spark, rpm, load_round, opt_afr)
    
    # Calculate % fuel saved relative to baseline
    fuel_saved_pct = 0.0
    if baseline_fuel > 0:
        fuel_saved_pct = max(0.0, (baseline_fuel - opt_fuel) / baseline_fuel * 100.0)
        
    return EconomyCellResult(
        rpm=rpm,
        load=load_round,
        spark_advance=round(float(opt_spark), 2),
        afr=round(float(opt_afr), 2),
        torque_nm=round(float(opt_torque), 1),
        min_torque_floor=round(float(min_torque_floor), 1),
        fuel_flow_g_s=round(float(opt_fuel), 3),
        baseline_fuel_flow=round(float(baseline_fuel), 3),
        fuel_saved_pct=round(float(fuel_saved_pct), 1),
        knock_margin_deg=round(float(opt_margin), 2)
    )


# Backward compatible drop-in function
def optimize_cell(rpm: float, load: float, seed: int = 42) -> EconomyCellResult:
    return optimize_economy_cell(int(rpm), load, None, seed=seed)


def build_calibration_table(
    rpm_points=None,
    load_points=None,
    dataset_path="engine_logged_dataset.csv"
) -> List[EconomyCellResult]:
    """Run fuel economy optimization across the full calibration grid."""
    from data_loader import RPM_POINTS, LOAD_POINTS
    if rpm_points is None:
        rpm_points = RPM_POINTS
    if load_points is None:
        load_points = LOAD_POINTS
        
    # Ensure model is trained and data binned
    get_learned_model()
    loader = EngineDataLoader(dataset_path)
    loader.load_and_clean()
    cell_stats = loader.bin_to_grid(rpm_points, load_points)
    
    results = []
    total_cells = len(rpm_points) * len(load_points)
    curr = 0
    print(f"\n🚀 Running Global Economy Optimization across {total_cells} cells...")
    
    for r in rpm_points:
        for l in load_points:
            curr += 1
            l_round = round(float(l), 2)
            stat = cell_stats.get((r, l_round))
            res = optimize_economy_cell(r, l_round, stat, seed=42 + curr)
            results.append(res)
            print(f"  [{curr:02d}/{total_cells:02d}] RPM {r:4d} | Load {l_round:0.2f} -> "
                  f"Spark: {res.spark_advance:5.1f}° | AFR: {res.afr:4.1f} | "
                  f"Torque: {res.torque_nm:5.1f} Nm (Floor: {res.min_torque_floor:5.1f}) | "
                  f"Fuel Flow: {res.fuel_flow_g_s:5.3f} g/s (-{res.fuel_saved_pct:4.1f}%)")
            
    return results


if __name__ == "__main__":
    results = build_calibration_table()
