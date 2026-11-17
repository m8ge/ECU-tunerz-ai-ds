"""
generate_dataset.py
--------------------
Generates a realistic ECU logged dataset containing 6,000+ telemetry points
simulating real-world dyno sweeps, steady-state highway cruising, transient
throttle tip-ins, and wide-open throttle (WOT) pulls.
"""

import numpy as np
import pandas as pd

def generate_telemetry(n_samples=7500, random_state=42):
    np.random.seed(random_state)
    
    # 1. Generate RPM and Load distributions reflecting typical vehicle operation
    # Mixture of cruise (low/mid load, 1500-3500 RPM), idle/city, and performance pulls
    rpm_parts = [
        np.random.uniform(1200, 2200, int(n_samples * 0.25)), # Low RPM / City
        np.random.uniform(2200, 3800, int(n_samples * 0.40)), # Cruise & mid-range
        np.random.uniform(3800, 5200, int(n_samples * 0.20)), # High power cruise / passing
        np.random.uniform(5200, 6800, int(n_samples * 0.15))  # High RPM dyno pulls
    ]
    rpms = np.concatenate(rpm_parts)
    np.random.shuffle(rpms)
    rpms = rpms[:n_samples]
    
    # Load distribution (0.15 to 1.05)
    load_parts = [
        np.random.uniform(0.18, 0.35, int(n_samples * 0.35)), # Light load / highway cruise
        np.random.uniform(0.35, 0.65, int(n_samples * 0.35)), # Moderate acceleration
        np.random.uniform(0.65, 0.90, int(n_samples * 0.20)), # Heavy load
        np.random.uniform(0.90, 1.02, int(n_samples * 0.10))  # WOT (wide open throttle)
    ]
    loads = np.concatenate(load_parts)
    np.random.shuffle(loads)
    loads = loads[:n_samples]
    
    # 2. Physics-based baseline ECU calibrations with real-world sensor noise
    # MBT timing & knock limit
    mbt_spark = 18.0 + 0.01 * (rpms - 2000) - 10.0 * loads
    knock_limit = 32.0 - 14.0 * loads - 0.002 * np.maximum(rpms - 3000, 0)
    
    # Standard factory ECU spark map: tuned conservative for torque/power
    # Generally 1-4 degrees below knock limit or at MBT
    spark_target = np.minimum(mbt_spark, knock_limit - 1.5)
    spark_advance = spark_target + np.random.normal(0, 1.2, n_samples)
    spark_advance = np.clip(spark_advance, 5.0, 35.0)
    
    # Standard factory AFR map:
    # Cruising/light load was stock tuned around stoich (14.6 - 14.8),
    # Medium load enriched to ~13.5 - 14.0,
    # High load / WOT enriched to 12.2 - 12.8 for component protection
    base_afr = np.where(
        loads < 0.45,
        14.7 + np.random.normal(0, 0.3, n_samples),
        np.where(
            loads < 0.75,
            14.7 - (loads - 0.45) * 4.0 + np.random.normal(0, 0.2, n_samples),
            12.8 - (loads - 0.75) * 2.5 + np.random.normal(0, 0.2, n_samples)
        )
    )
    afr = np.clip(base_afr, 11.2, 16.5)
    
    # 3. Calculate Engine Brake Torque (Nm)
    # Peak torque characteristics around 3800-4500 RPM
    volumetric_eff = 0.88 * (1.0 - 2.5e-8 * (rpms - 4200)**2)
    base_indicated_torque = 50.0 + 230.0 * loads * volumetric_eff
    
    # Spark timing efficiency (distance from MBT, sharp penalty if past knock limit)
    dist_mbt = np.abs(spark_advance - mbt_spark)
    eff_spark = np.exp(-0.5 * (dist_mbt / 9.5)**2)
    over_knock = np.maximum(0, spark_advance - knock_limit)
    eff_spark *= np.exp(-2.2 * over_knock)
    
    # AFR efficiency on torque: peak torque at ~12.8 AFR
    eff_afr = np.exp(-0.5 * ((afr - 12.8) / 3.8)**2)
    
    torque_nm = base_indicated_torque * eff_spark * eff_afr
    # Add physical measurement noise (+/- 2.5 Nm)
    torque_nm += np.random.normal(0, 2.2, n_samples)
    torque_nm = np.clip(torque_nm, 8.0, 280.0)
    
    # 4. Calculate Fuel Flow (g/s)
    # Engine displacement 2.0L (0.002 m^3), 4-stroke
    # Air flow (g/s) = (RPM / 120) * displacement_L * air_density (1.204 g/L) * Load * VE
    air_flow_g_s = (rpms / 120.0) * 2.0 * 1.204 * loads * volumetric_eff
    
    # Fuel flow = Air flow / AFR
    # Plus thermal efficiency correction: retarding spark raises exhaust gas temp and requires more fuel for same power
    combustion_eff_penalty = 1.0 + 0.015 * np.maximum(0, mbt_spark - spark_advance)
    fuel_flow_g_s = (air_flow_g_s / afr) * combustion_eff_penalty
    fuel_flow_g_s += np.random.normal(0, 0.05 * fuel_flow_g_s, n_samples)
    fuel_flow_g_s = np.clip(fuel_flow_g_s, 0.15, 25.0)
    
    # Knock margin
    knock_margin_deg = knock_limit - spark_advance
    
    # Build clean DataFrame
    df = pd.DataFrame({
        "rpm": np.round(rpms, 0).astype(int),
        "load": np.round(loads, 3),
        "spark_advance_deg": np.round(spark_advance, 2),
        "afr": np.round(afr, 2),
        "torque_nm": np.round(torque_nm, 1),
        "fuel_flow_g_s": np.round(fuel_flow_g_s, 3),
        "knock_margin_deg": np.round(knock_margin_deg, 2)
    })
    
    return df

if __name__ == "__main__":
    df = generate_telemetry(n_samples=8000)
    df.to_csv("engine_logged_dataset.csv", index=False)
    print(f"Generated {len(df)} logged telemetry records to engine_logged_dataset.csv")
    print(df.head(10))
    print("\nSummary Statistics:")
    print(df.describe().T[["mean", "std", "min", "50%", "max"]])
