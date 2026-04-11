import os
import pandas as pd

DATA_PATH = r"D:\mimic-iv-clinical-database-demo-2.2"

print("=== MIMIC DEMO CHECK ===")

# Check dataset path
print("Dataset path exists:", os.path.exists(DATA_PATH))

# Try loading chartevents
file_path = r"C:\chartevents.csv"

if not os.path.exists(file_path):
    print("chartevents.csv NOT FOUND")
else:
    print("\nLoading chartevents sample...")

    df = pd.read_csv(file_path, nrows=1000)

    print("Rows loaded:", len(df))
    print("Columns:", list(df.columns))

    # Try extracting heart rate
    if "itemid" in df.columns:
        hr = df[df["itemid"] == 220045]

        print("\nHeart rate sample count:", len(hr))

        if not hr.empty:
            print("Heart rate stats:")
            print(hr["valuenum"].describe())