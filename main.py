#!/usr/bin/env python3
"""
main.py
-------
AI ECU Calibration Optimizer - Fuel Economy Edition (BSFC / Fuel Flow Minimization)
Executes empirical ML model training, cell-by-cell global optimization with
drivability and knock-safety enforcement, and exports:
  - fuel_economy_calibration.csv (full comparison table)
  - fuel_saving_heatmap.png      (% Fuel Flow Reduction / Projected MPG Boost)
  - spark_advance_map.png        (Optimal ignition timing map)
  - afr_economy_map.png          (Optimal AFR targets including lean-burn cruise)
  - torque_drivability_check.png (Delivered Torque vs Drivability Floor)
"""

import os
import csv
import numpy as np

# Ensure matplotlib uses a clean non-interactive backend and writable cache dir before importing
os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib"
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

from data_loader import EngineDataLoader, RPM_POINTS, LOAD_POINTS
from learned_model import get_learned_model
from optimizer import build_calibration_table


def set_sporty_carbon_style():
    """Configures clean sporty dark styling with carbon/motorsport accents."""
    plt.rcParams.update({
        "figure.facecolor": "#121316",
        "axes.facecolor": "#181a1f",
        "axes.edgecolor": "#383c48",
        "axes.labelcolor": "#e0e3eb",
        "xtick.color": "#9ca3af",
        "ytick.color": "#9ca3af",
        "text.color": "#f3f4f6",
        "font.family": "sans-serif",
        "font.weight": "bold",
        "axes.titleweight": "bold",
        "axes.titlesize": 13,
        "figure.titlesize": 15,
        "grid.color": "#262932",
        "grid.linestyle": ":",
        "grid.alpha": 0.6
    })


def main():
    set_sporty_carbon_style()
    
    print("\n" + "=" * 74)
    print("  🏁 CARBON-AI // ECU FUEL ECONOMY CALIBRATION OPTIMIZER (BSFC/MPG)  ")
    print("=" * 74)
    
    # 1. Telemetry Loader & Density Check
    loader = EngineDataLoader("engine_logged_dataset.csv")
    loader.load_and_clean()
    loader.bin_to_grid()
    loader.print_density_report()
    
    # 2. Train / Verify ML Surrogate Models
    print("⚡ Verifying Empirical Surrogate Regression Models...")
    model = get_learned_model()
    
    # 3. Global Optimization
    results = build_calibration_table(RPM_POINTS, LOAD_POINTS, "engine_logged_dataset.csv")
    
    # 4. Display Comparison Table
    print("\n" + "=" * 94)
    print("  📊 CALIBRATION SUMMARY: AS-LOGGED BASELINE vs. OPTIMIZER-RECOMMENDED ECONOMY")
    print("=" * 94)
    header = (f"{'RPM':>5} | {'Load':>5} | {'Base Fuel':>9} | {'Opt Fuel':>8} | "
              f"{'Saved %':>7} | {'Proj MPG+':>9} | {'Spark°':>6} | {'AFR':>5} | "
              f"{'Torque':>6} | {'Floor':>5} | {'Knock':>5}")
    print(header)
    print("-" * len(header))
    
    total_base_fuel = 0.0
    total_opt_fuel = 0.0
    
    for r in results:
        mpg_multiplier = (1.0 / (1.0 - r.fuel_saved_pct / 100.0)) if r.fuel_saved_pct < 100 else 1.0
        mpg_gain_str = f"+{(mpg_multiplier - 1.0) * 100:0.1f}%"
        print(f"{r.rpm:5d} | {r.load:5.2f} | {r.baseline_fuel_flow:8.3f}g | {r.fuel_flow_g_s:7.3f}g | "
              f"{r.fuel_saved_pct:6.1f}% | {mpg_gain_str:>9} | {r.spark_advance:6.1f} | {r.afr:5.1f} | "
              f"{r.torque_nm:6.1f} | {r.min_torque_floor:5.1f} | {r.knock_margin_deg:5.1f}")
        total_base_fuel += r.baseline_fuel_flow
        total_opt_fuel += r.fuel_flow_g_s
        
    avg_savings = (total_base_fuel - total_opt_fuel) / total_base_fuel * 100.0
    print("-" * len(header))
    print(f"  🏁 MAP-WIDE AVERAGE FUEL FLOW REDUCTION: {avg_savings:0.1f}%  |  "
          f"PROJECTED FLEET MPG BOOST: +{(1.0 / (1.0 - avg_savings / 100.0) - 1.0) * 100:0.1f}%\n")
          
    # 5. Export CSV
    csv_file = "fuel_economy_calibration.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rpm", "load", "baseline_fuel_flow_g_s", "optimized_fuel_flow_g_s",
            "fuel_savings_pct", "projected_mpg_gain_pct", "spark_advance_deg",
            "afr", "torque_nm", "min_drivability_torque_nm", "knock_margin_deg"
        ])
        for r in results:
            mpg_boost = ((1.0 / (1.0 - r.fuel_saved_pct / 100.0)) - 1.0) * 100 if r.fuel_saved_pct < 100 else 0.0
            writer.writerow([
                r.rpm, r.load, r.baseline_fuel_flow, r.fuel_flow_g_s,
                r.fuel_saved_pct, round(mpg_boost, 1), r.spark_advance,
                r.afr, r.torque_nm, r.min_torque_floor, r.knock_margin_deg
            ])
    print(f"💾 Saved calibrated economy map to {csv_file}")
    
    # Also save standard calibration_table.csv for drop-in prototype compatibility
    with open("calibration_table.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["rpm", "load", "spark_advance_deg", "afr", "torque_nm", "knock_margin_deg"])
        for r in results:
            writer.writerow([r.rpm, r.load, r.spark_advance, r.afr, r.torque_nm, r.knock_margin_deg])
            
    # 6. Plot Sporty Carbon Heatmaps
    plot_carbon_heatmaps(results)
    print("🎨 Generated 4 sporty carbon-fiber telemetry heatmaps:")
    print("   - fuel_saving_heatmap.png")
    print("   - spark_advance_map.png")
    print("   - afr_economy_map.png")
    print("   - torque_drivability_check.png")

    # Sync artifacts with public/ directory if it exists
    if os.path.isdir("public"):
        import shutil
        for fname in [
            "fuel_economy_calibration.csv", "calibration_table.csv",
            "fuel_saving_heatmap.png", "spark_advance_map.png",
            "afr_economy_map.png", "torque_drivability_check.png"
        ]:
            if os.path.exists(fname):
                shutil.copy(fname, os.path.join("public", fname))


def plot_carbon_heatmaps(results):
    """Generates motorsport-inspired telemetry heatmaps with carbon styling."""
    n_rpm = len(RPM_POINTS)
    n_load = len(LOAD_POINTS)
    
    savings_grid = np.array([r.fuel_saved_pct for r in results]).reshape(n_rpm, n_load)
    spark_grid = np.array([r.spark_advance for r in results]).reshape(n_rpm, n_load)
    afr_grid = np.array([r.afr for r in results]).reshape(n_rpm, n_load)
    torque_grid = np.array([r.torque_nm for r in results]).reshape(n_rpm, n_load)
    floor_grid = np.array([r.min_torque_floor for r in results]).reshape(n_rpm, n_load)
    
    # 1. Fuel Savings Heatmap (% reduction)
    _render_carbon_grid(
        savings_grid,
        title="CALIBRATION FUEL SAVINGS (% REDUCTION)",
        subtitle="Lean-burn cruise & MBT spark advance optimization vs as-logged baseline",
        filename="fuel_saving_heatmap.png",
        cmap="YlGnBu",
        val_fmt="{:0.1f}%",
        cbar_label="Fuel Flow Savings (%)"
    )
    
    # 2. Spark Advance Heatmap
    _render_carbon_grid(
        spark_grid,
        title="OPTIMIZED IGNITION TIMING MAP",
        subtitle="Spark Advance (deg BTDC) satisfying knock-safety >= 1.0° margin",
        filename="spark_advance_map.png",
        cmap="plasma",
        val_fmt="{:0.1f}°",
        cbar_label="Advance (deg BTDC)"
    )
    
    # 3. AFR Map
    _render_carbon_grid(
        afr_grid,
        title="OPTIMIZED AIR-FUEL RATIO (AFR) MAP",
        subtitle="Lean cruise (~15.5-16.5) at light load | Safe enrichment (<13.0) at heavy load",
        filename="afr_economy_map.png",
        cmap="viridis",
        val_fmt="{:0.1f}:1",
        cbar_label="Air-to-Fuel Ratio"
    )
    
    # 4. Torque Drivability Verification (Delivered / Floor Ratio)
    margin_ratio = (torque_grid - floor_grid)
    _render_carbon_grid(
        margin_ratio,
        title="DRIVABILITY TORQUE HEADROOM (Nm)",
        subtitle="Delivered Torque minus Required Floor (>0 indicates satisfied floor)",
        filename="torque_drivability_check.png",
        cmap="cividis",
        val_fmt="+{:0.0f} Nm",
        cbar_label="Torque Headroom (Nm)"
    )


def _render_carbon_grid(grid, title, subtitle, filename, cmap, val_fmt, cbar_label):
    fig, ax = plt.subplots(figsize=(7.5, 6.0), dpi=140)
    
    # Subtle carbon grid border
    for spine in ax.spines.values():
        spine.set_color("#444957")
        spine.set_linewidth(1.8)
        
    im = ax.imshow(grid, cmap=cmap, aspect="auto", origin="lower", interpolation="nearest")
    
    # Tick markers
    ax.set_xticks(range(len(LOAD_POINTS)))
    ax.set_xticklabels([f"{l:0.1f}" for l in LOAD_POINTS], fontsize=10, fontweight="bold")
    ax.set_yticks(range(len(RPM_POINTS)))
    ax.set_yticklabels([f"{r:d}" for r in RPM_POINTS], fontsize=10, fontweight="bold")
    
    ax.set_xlabel("ENGINE LOAD (Relative MAP / Throttle)", fontsize=10, labelpad=8)
    ax.set_ylabel("ENGINE SPEED (RPM)", fontsize=10, labelpad=8)
    
    # Title & Subtitle
    plt.suptitle(title, fontsize=12, fontweight="heavy", color="#ffffff", y=0.98)
    ax.set_title(subtitle, fontsize=8.5, color="#9ca3af", pad=10)
    
    # Overlay values inside cells
    # Dynamic text contrast
    norm = mcolors.Normalize(vmin=grid.min(), vmax=grid.max())
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            val = grid[i, j]
            # Use darker text on bright background
            brightness = norm(val)
            txt_color = "#111827" if (brightness > 0.65 and cmap != "plasma") else "#ffffff"
            ax.text(
                j, i, val_fmt.format(val),
                ha="center", va="center",
                color=txt_color, fontsize=9.5, fontweight="bold"
            )
            
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(cbar_label, fontsize=9, color="#e5e7eb", weight="bold")
    cbar.ax.tick_params(labelsize=8, colors="#9ca3af")
    cbar.outline.set_edgecolor("#383c48")
    
    fig.tight_layout()
    fig.subplots_adjust(top=0.88)
    fig.savefig(filename, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)


if __name__ == "__main__":
    import sys
    main()
    if "--serve" in sys.argv or "-s" in sys.argv:
        from server import start_server
        start_server()
