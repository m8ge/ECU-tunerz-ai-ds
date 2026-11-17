"""
learned_model.py
----------------
Machine learning regression surrogate model trained on empirical engine
telemetry data. Exposes drop-in replacements for torque, fuel consumption,
and knock safety calculations with the exact function signatures required
by optimizer.py.
"""

import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from data_loader import EngineDataLoader

MODEL_CACHE_FILE = "learned_engine_models.joblib"


class LearnedEngineModel:
    def __init__(self, dataset_path: str = "engine_logged_dataset.csv"):
        self.dataset_path = dataset_path
        self.torque_model = None
        self.fuel_model = None
        self.knock_model = None
        self.metrics = {}
        
    def train(self, force_retrain: bool = False):
        """Train GradientBoostingRegressor models on telemetry dataset."""
        if not force_retrain and os.path.exists(MODEL_CACHE_FILE):
            data = joblib.load(MODEL_CACHE_FILE)
            self.torque_model = data["torque_model"]
            self.fuel_model = data["fuel_model"]
            self.knock_model = data.get("knock_model")
            self.metrics = data.get("metrics", {})
            return self
            
        loader = EngineDataLoader(self.dataset_path)
        df = loader.load_and_clean()
        
        feature_cols = ["rpm", "load", "spark_advance_deg", "afr"]
        X = df[feature_cols].values
        y_torque = df["torque_nm"].values
        y_fuel = df["fuel_consumption"].values
        
        # Knock margin if present
        y_knock = df["knock_margin_deg"].values if "knock_margin_deg" in df.columns else None
        
        X_train, X_test, y_t_train, y_t_test, y_f_train, y_f_test = train_test_split(
            X, y_torque, y_fuel, test_size=0.2, random_state=42
        )
        
        # Fit Torque Model
        print("  ⚡ Training GradientBoostingRegressor for Engine Torque (Nm)...")
        self.torque_model = GradientBoostingRegressor(
            n_estimators=150, max_depth=5, learning_rate=0.08, subsample=0.85, random_state=42
        )
        self.torque_model.fit(X_train, y_t_train)
        t_pred = self.torque_model.predict(X_test)
        r2_t = r2_score(y_t_test, t_pred)
        mae_t = mean_absolute_error(y_t_test, t_pred)
        
        # Fit Fuel Consumption Model (g/s)
        print("  ⛽ Training GradientBoostingRegressor for Fuel Consumption (g/s)...")
        self.fuel_model = GradientBoostingRegressor(
            n_estimators=150, max_depth=5, learning_rate=0.08, subsample=0.85, random_state=42
        )
        self.fuel_model.fit(X_train, y_f_train)
        f_pred = self.fuel_model.predict(X_test)
        r2_f = r2_score(y_f_test, f_pred)
        mae_f = mean_absolute_error(y_f_test, f_pred)
        
        # Fit Knock Margin Model
        if y_knock is not None:
            X_k_train, X_k_test, y_k_train, y_k_test = train_test_split(
                X, y_knock, test_size=0.2, random_state=42
            )
            self.knock_model = GradientBoostingRegressor(
                n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42
            )
            self.knock_model.fit(X_k_train, y_k_train)
            k_pred = self.knock_model.predict(X_k_test)
            r2_k = r2_score(y_k_test, k_pred)
            mae_k = mean_absolute_error(y_k_test, k_pred)
        else:
            self.knock_model = None
            r2_k, mae_k = 0.0, 0.0
            
        self.metrics = {
            "torque": {"r2": r2_t, "mae": mae_t},
            "fuel": {"r2": r2_f, "mae": mae_f},
            "knock": {"r2": r2_k, "mae": mae_k}
        }
        
        # Cache to disk
        joblib.dump({
            "torque_model": self.torque_model,
            "fuel_model": self.fuel_model,
            "knock_model": self.knock_model,
            "metrics": self.metrics
        }, MODEL_CACHE_FILE)
        
        print("\n" + "=" * 62)
        print("  🏆 LEARNED SURROGATE MODEL ACCURACY METRICS")
        print("=" * 62)
        print(f"  Torque Model R²:            {r2_t:0.4f}  |  MAE: {mae_t:0.2f} Nm")
        print(f"  Fuel Consumption Model R²:  {r2_f:0.4f}  |  MAE: {mae_f:0.3f} g/s")
        if self.knock_model:
            print(f"  Knock Margin Model R²:      {r2_k:0.4f}  |  MAE: {mae_k:0.2f} deg")
        print("=" * 62 + "\n")
        
        return self
        
    def predict_torque(self, rpm: float, load: float, spark_advance: float, afr: float) -> float:
        """Predict engine brake torque (Nm)."""
        x = np.array([[rpm, load, spark_advance, afr]], dtype=float)
        return float(self.torque_model.predict(x)[0])
        
    def predict_fuel(self, rpm: float, load: float, spark_advance: float, afr: float) -> float:
        """Predict fuel consumption rate (g/s)."""
        x = np.array([[rpm, load, spark_advance, afr]], dtype=float)
        return float(self.fuel_model.predict(x)[0])
        
    def predict_knock_margin(self, spark_advance: float, rpm: float, load: float, afr: float = 14.7) -> float:
        """Predict safety knock margin (deg). Positive = safe."""
        if self.knock_model is not None:
            x = np.array([[rpm, load, spark_advance, afr]], dtype=float)
            return float(self.knock_model.predict(x)[0])
        # Empirical fallback physics limit
        limit = 32.0 - 14.0 * load - 0.002 * max(rpm - 3000, 0)
        return float(limit - spark_advance)


# Global singleton instance for drop-in function calls
_GLOBAL_MODEL: LearnedEngineModel = None

def get_learned_model() -> LearnedEngineModel:
    global _GLOBAL_MODEL
    if _GLOBAL_MODEL is None:
        _GLOBAL_MODEL = LearnedEngineModel()
        _GLOBAL_MODEL.train()
    return _GLOBAL_MODEL


# --- Drop-in replacement functions matching engine_model.py signatures ---

def learned_torque_nm(rpm: float, load: float, spark_advance: float, afr: float) -> float:
    """Drop-in replacement for simulated_torque_nm(). Returns brake torque in Nm."""
    model = get_learned_model()
    return model.predict_torque(rpm, load, spark_advance, afr)


def learned_fuel_consumption(rpm: float, load: float, spark_advance: float, afr: float) -> float:
    """Predicts fuel flow rate (g/s). Target to minimize in economy calibration."""
    model = get_learned_model()
    return model.predict_fuel(rpm, load, spark_advance, afr)


def learned_knock_margin(spark_advance: float, rpm: float, load: float, afr: float = 14.7) -> float:
    """Drop-in replacement for knock_margin(). Positive = safe margin below knock limit."""
    model = get_learned_model()
    return model.predict_knock_margin(spark_advance, rpm, load, afr)


if __name__ == "__main__":
    model = LearnedEngineModel()
    model.train(force_retrain=True)
    
    # Test drop-in calls at cruise (2500 RPM, 0.4 Load)
    t = learned_torque_nm(2500, 0.4, 22.0, 14.7)
    f = learned_fuel_consumption(2500, 0.4, 22.0, 14.7)
    k = learned_knock_margin(22.0, 2500, 0.4)
    print(f"Sample cruise prediction (2500 RPM, 0.4 Load, 22° spark, 14.7 AFR):")
    print(f"  Torque: {t:.1f} Nm | Fuel Flow: {f:.3f} g/s | Knock Margin: {k:.1f}°")
