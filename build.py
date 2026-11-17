#!/usr/bin/env python3
"""
build.py
--------
Prepares the clean production distribution folder (`dist/`) and bundles
`netlify_deploy.zip` ready for 1-click drag-and-drop deployment to Netlify.
"""

import os
import shutil
import zipfile

FILES = [
    "index.html",
    "styles.css",
    "app.js",
    "fuel_saving_heatmap.png",
    "spark_advance_map.png",
    "afr_economy_map.png",
    "torque_drivability_check.png",
    "fuel_economy_calibration.csv",
    "calibration_table.csv",
    "engine_logged_dataset.csv",
    "netlify.toml",
    "_headers"
]

def build():
    os.makedirs("dist", exist_ok=True)
    os.makedirs("public", exist_ok=True)

    for f in FILES:
        if os.path.exists(f):
            shutil.copy2(f, os.path.join("dist", f))
            shutil.copy2(f, os.path.join("public", f))

    zip_name = "netlify_deploy.zip"
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            if os.path.exists(f):
                z.write(f, arcname=f)

    size_kb = os.path.getsize(zip_name) / 1024
    print(f"📦 Built {zip_name} ({size_kb:.1f} KB) & updated dist/ folder.")

if __name__ == "__main__":
    build()
