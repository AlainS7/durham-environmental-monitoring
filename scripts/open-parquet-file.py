import pandas as pd

# Specify the path to your Parquet file
parquet_file_path = "raw_source=TSI_agg=raw_dt=2025-08-15_TSI-2025-08-15.parquet"

# Read the Parquet file into a DataFrame
df = pd.read_parquet(parquet_file_path)

# Now you can work with the DataFrame
df["hour"] = df["ts"].dt.hour
df["minute"] = df["ts"].dt.minute


# Group by sensor and show time differences between consecutive rows for each sensor
df = df.sort_values(["native_sensor_id", "ts"])
df["time_diff_minutes"] = (
    df.groupby("native_sensor_id")["ts"].diff().dt.total_seconds() / 60
)

# Show sensor, timestamp, hour, minute, and time difference
print(df[["native_sensor_id", "timestamp", "hour", "minute", "time_diff_minutes"]])

# Print all hours and minutes for all rows
print(df[["timestamp", "hour", "minute"]])

# Show only rows where the interval is not close to 15 minutes (tolerance of 0.1 min)
irregular = df[(df["time_diff_minutes"].notnull()) & (df["time_diff_minutes"].abs() - 15 > 0.1)]
print("Rows with intervals NOT close to 15 minutes:")
print(irregular[["native_sensor_id", "timestamp", "hour", "minute", "time_diff_minutes"]])