import io
import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd
from google.cloud import storage

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except Exception:  # pragma: no cover - import-time guard
    pa = None
    pq = None

log = logging.getLogger(__name__)


# Numeric fields we always coerce to float64 for stable parquet schemas
TSI_NUMERIC_COLS = {
    "pm1_0",
    "pm2_5",
    "pm4_0",
    "pm10",
    "pm2_5_aqi",
    "pm10_aqi",
    "ncpm0_5",
    "ncpm1_0",
    "ncpm2_5",
    "ncpm4_0",
    "ncpm10",
    "temperature",
    "humidity",
    "tpsize",
    "co2_ppm",
    "co_ppm",
    "baro_inhg",
    "o3_ppb",
    "no2_ppb",
    "so2_ppb",
    "ch2o_ppb",
    "voc_mgm3",
    "latitude",
    "longitude",
    "latitude_f",
    "longitude_f",
}
WU_NUMERIC_COLS = {
    "temperature",
    "temperature_high",
    "temperature_low",
    "humidity",
    "humidity_high",
    "humidity_low",
    "precip_rate",
    "precip_total",
    "wind_speed_avg",
    "wind_speed_high",
    "wind_speed_low",
    "wind_gust_avg",
    "wind_gust_high",
    "wind_gust_low",
    "wind_direction_avg",
    "pressure_max",
    "pressure_min",
    "pressure_trend",
    "solar_radiation",
    "uv_high",
    "wind_chill_avg",
    "wind_chill_high",
    "wind_chill_low",
    "heat_index_avg",
    "heat_index_high",
    "heat_index_low",
    "dew_point_avg",
    "dew_point_high",
    "dew_point_low",
    "qc_status",
}


def coerce_numeric_columns(df: pd.DataFrame, columns: set[str]) -> pd.DataFrame:
    """Return a copy with listed columns coerced to float64 when present."""
    if df.empty:
        return df
    coerced = df.copy()
    for col in columns:
        if col in coerced.columns:
            coerced[col] = pd.to_numeric(coerced[col], errors="coerce").astype(
                "float64"
            )
    return coerced


@dataclass(slots=True)
class UploadSpec:
    source: str
    aggregated: bool = False
    interval: str = "h"
    ts_column: str = "timestamp"
    extra_suffix: Optional[str] = None


class GCSUploader:
    """Uploads pandas DataFrames to Google Cloud Storage as Parquet files.

    Refactored to use an UploadSpec dataclass instead of a long argument list
    (reduces CodeScene argument-count flags and clarifies intent).
    Paths are partitioned by date for efficient BigQuery batch loads.
    Legacy method signature is still supported for backward compatibility.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "sensor_readings",
        client: Optional[storage.Client] = None,
    ):
        if not bucket:
            raise ValueError("GCS bucket must be provided")
        self.bucket_name = bucket
        self.prefix = prefix.strip("/")
        self.client = client or storage.Client()
        self.bucket = self.client.bucket(self.bucket_name)

    def _build_blob_path(self, df: pd.DataFrame, spec: UploadSpec) -> str:
        if df.empty:
            raise ValueError("Cannot build path for empty DataFrame")
        ts = pd.to_datetime(df[spec.ts_column]).sort_values().iloc[0]
        date_str = ts.strftime("%Y-%m-%d")
        agg_part = f"agg={spec.interval}" if spec.aggregated else "agg=raw"
        suffix = f"-{spec.extra_suffix}" if spec.extra_suffix else ""
        filename = f"{spec.source}-{date_str}{suffix}.parquet"
        path = f"{self.prefix}/source={spec.source}/{agg_part}/dt={date_str}/{filename}"
        return path

    # Backward-compatible private method kept for tests invoking old signature
    def _make_blob_path_legacy(
        self,
        source: str,
        df: pd.DataFrame,
        aggregated: bool,
        interval: str,
        ts_column: str,
        extra_suffix: Optional[str] = None,
    ) -> str:  # pragma: no cover - thin wrapper
        spec = UploadSpec(
            source=source,
            aggregated=aggregated,
            interval=interval,
            ts_column=ts_column,
            extra_suffix=extra_suffix,
        )
        return self._build_blob_path(df, spec)

    # Provide original name accepting legacy kwargs for existing tests
    def _make_blob_path(self, *args, **kwargs):  # legacy public name retained
        """Support both legacy and new calling conventions.

        Legacy: _make_blob_path(source, df, aggregated=..., interval=..., ts_column=..., extra_suffix=...)
        New (internal use): _make_blob_path(df=df, spec=UploadSpec(...))
        """
        # New style
        if "spec" in kwargs and isinstance(kwargs.get("spec"), UploadSpec):
            return self._build_blob_path(kwargs["df"], kwargs["spec"])  # type: ignore[index]
        # Legacy positional style
        if args and isinstance(args[0], str):
            source = args[0]
            df = args[1]
            spec = UploadSpec(
                source=source,
                aggregated=kwargs.get("aggregated", False),
                interval=kwargs.get("interval", "h"),
                ts_column=kwargs.get("ts_column", "timestamp"),
                extra_suffix=kwargs.get("extra_suffix"),
            )
            return self._build_blob_path(df, spec)
        raise TypeError("Unsupported _make_blob_path invocation pattern")

    def upload_parquet(
        self, df: pd.DataFrame, source: Optional[str] = None, **legacy_kwargs
    ) -> str:
        """Write DataFrame as Parquet to GCS. Returns the GCS path.

            Preferred use: pass an UploadSpec via spec=...
            Backward-compatible legacy usage: positional/keyword args (source, aggregated, interval, ts_column, extra_suffix)
        Idempotency: by default, skips uploading if the exact blob path already exists. Override with force=True.
        """
        # Backward compatibility path detection
        spec: UploadSpec
        if "spec" in legacy_kwargs and isinstance(legacy_kwargs["spec"], UploadSpec):
            spec = legacy_kwargs["spec"]
        else:
            # Legacy signature mapping
            spec = UploadSpec(
                source=source
                or legacy_kwargs.get("source")
                or legacy_kwargs.get("src", "unknown"),
                aggregated=legacy_kwargs.get("aggregated", False),
                interval=legacy_kwargs.get("interval", "h"),
                ts_column=legacy_kwargs.get("ts_column", "timestamp"),
                extra_suffix=legacy_kwargs.get("extra_suffix"),
            )
        if df.empty:
            log.info("Skipping upload: DataFrame is empty.")
            return ""
        # Ensure timestamp column exists and is datetime
        if spec.ts_column not in df.columns:
            raise ValueError(
                f"DataFrame missing required timestamp column '{spec.ts_column}'"
            )
        df = df.copy()
        # Stabilize parquet schema: coerce numeric columns to float64 per source
        source_upper = (spec.source or "").upper()
        if source_upper == "TSI":
            df = coerce_numeric_columns(df, TSI_NUMERIC_COLS)
        elif source_upper == "WU":
            df = coerce_numeric_columns(df, WU_NUMERIC_COLS)
        # Cope with duplicate column names which cause pyarrow.Table.from_pandas to fail.
        # Keep the first occurrence for each duplicate column name and warn.
        if df.columns.duplicated().any():
            dup_names = df.columns[df.columns.duplicated()].unique().tolist()
            log.warning(
                f"Duplicate column names found: {dup_names}. Keeping first occurrence of each and dropping duplicates."
            )
            df = df.loc[:, ~df.columns.duplicated()]
        df[spec.ts_column] = pd.to_datetime(
            df[spec.ts_column], utc=True, errors="coerce"
        )
        df = df.dropna(subset=[spec.ts_column])
        if df.empty:
            log.info("Skipping upload: DataFrame empty after timestamp coercion.")
            return ""

        blob_path = self._build_blob_path(df, spec)
        blob = self.bucket.blob(blob_path)

        force = legacy_kwargs.get("force", False)
        blob_exists = False
        try:
            # Some test dummies may not implement exists(); treat as non-existent.
            exists_method = getattr(blob, "exists", None)
            if callable(exists_method):
                blob_exists = bool(exists_method())
        except Exception:  # pragma: no cover - defensive
            blob_exists = False
        if not force and blob_exists:  # Skip if already present
            log.info(f"Skip upload (exists): gs://{self.bucket_name}/{blob_path}")
            return f"gs://{self.bucket_name}/{blob_path}"

        log.info(
            f"Uploading Parquet to gs://{self.bucket_name}/{blob_path}... (force={force})"
        )

        # Write to in-memory buffer as parquet
        if pa is None or pq is None:
            raise RuntimeError(
                "pyarrow is required for Parquet uploads. Please install pyarrow."
            )

        table = pa.Table.from_pandas(df)
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="snappy")
        buf.seek(0)

        blob.upload_from_file(buf, content_type="application/octet-stream")
        log.info("Upload complete.")
        return f"gs://{self.bucket_name}/{blob_path}"
