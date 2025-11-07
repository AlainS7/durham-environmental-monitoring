#!/usr/bin/env python3
"""
Benchmark: Data Loading Performance (pandas vs cuDF)

Tests the performance of loading Parquet files and basic data operations.
"""

import time
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any
import sys

# Check if GPU is available
try:
    import cudf
    import cupy as cp

    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False
    print("WARNING: cuDF not available. Install RAPIDS to run GPU benchmarks.")

import pandas as pd
import numpy as np


class BenchmarkRunner:
    """Handles benchmark execution and result collection."""

    def __init__(self, warmup_runs: int = 2, benchmark_runs: int = 5):
        self.warmup_runs = warmup_runs
        self.benchmark_runs = benchmark_runs
        self.results: List[Dict[str, Any]] = []

    def generate_test_data(self, n_rows: int, output_path: Path) -> None:
        """Generate synthetic environmental data for benchmarking."""
        print(f"Generating test data with {n_rows:,} rows...")

        timestamps = pd.date_range("2024-01-01", periods=n_rows, freq="15min")

        data = {
            "timestamp": timestamps,
            "sensor_id": np.random.choice(
                ["sensor_001", "sensor_002", "sensor_003"], n_rows
            ),
            "temperature_f": np.random.uniform(30, 100, n_rows),
            "humidity_pct": np.random.uniform(20, 90, n_rows),
            "pm25": np.random.uniform(0, 150, n_rows),
            "pm10": np.random.uniform(0, 200, n_rows),
            "pressure": np.random.uniform(28, 31, n_rows),
            "wind_speed": np.random.uniform(0, 30, n_rows),
            "wind_direction": np.random.randint(0, 360, n_rows),
        }

        # Add some nulls (10% of data)
        for col in ["temperature_f", "humidity_pct", "pm25"]:
            null_indices = np.random.choice(
                n_rows, size=int(n_rows * 0.1), replace=False
            )
            data[col][null_indices] = np.nan

        df = pd.DataFrame(data)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(output_path, engine="pyarrow", compression="snappy")
        print(f"✓ Test data saved to {output_path}")

    def benchmark_pandas(self, parquet_path: Path) -> Dict[str, float]:
        """Benchmark pandas data loading and operations."""
        times = []

        # Warmup
        for _ in range(self.warmup_runs):
            df = pd.read_parquet(parquet_path)
            _ = df["temperature_f"].mean()

        # Actual benchmark
        for _ in range(self.benchmark_runs):
            start = time.perf_counter()

            # Load data
            df = pd.read_parquet(parquet_path)

            # Basic operations
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["temperature_c"] = (df["temperature_f"] - 32) * 5 / 9
            df["pm25_filled"] = df["pm25"].fillna(df["pm25"].median())

            # Aggregation
            result = df.groupby("sensor_id")["temperature_f"].mean()

            elapsed = time.perf_counter() - start
            times.append(elapsed)

        return {
            "mean": np.mean(times),
            "std": np.std(times),
            "min": np.min(times),
            "max": np.max(times),
            "rows": len(df),
            "memory_mb": df.memory_usage(deep=True).sum() / 1e6,
        }

    def benchmark_cudf(self, parquet_path: Path) -> Dict[str, float]:
        """Benchmark cuDF (GPU) data loading and operations."""
        if not GPU_AVAILABLE:
            return {"error": "GPU not available"}

        times = []

        # Warmup
        for _ in range(self.warmup_runs):
            df = cudf.read_parquet(parquet_path)
            _ = df["temperature_f"].mean()

        # Actual benchmark
        for _ in range(self.benchmark_runs):
            # Clear GPU memory
            cp.get_default_memory_pool().free_all_blocks()

            start = time.perf_counter()

            # Load data
            df = cudf.read_parquet(parquet_path)

            # Basic operations
            df["timestamp"] = cudf.to_datetime(df["timestamp"])
            df["temperature_c"] = (df["temperature_f"] - 32) * 5 / 9
            df["pm25_filled"] = df["pm25"].fillna(df["pm25"].median())

            # Aggregation
            result = df.groupby("sensor_id")["temperature_f"].mean()

            # Force computation (cuDF is lazy)
            _ = result.to_pandas()

            elapsed = time.perf_counter() - start
            times.append(elapsed)

        return {
            "mean": np.mean(times),
            "std": np.std(times),
            "min": np.min(times),
            "max": np.max(times),
            "rows": len(df),
            "memory_mb": df.memory_usage(deep=True).sum() / 1e6,
        }

    def run_comparison(self, data_sizes: List[int], output_dir: Path) -> None:
        """Run benchmarks for all data sizes."""
        output_dir.mkdir(parents=True, exist_ok=True)

        for size in data_sizes:
            print(f"\n{'=' * 60}")
            print(f"Benchmarking with {size:,} rows")
            print("=" * 60)

            # Generate test data
            test_file = output_dir / f"test_data_{size}.parquet"
            if not test_file.exists():
                self.generate_test_data(size, test_file)

            # Run pandas benchmark
            print("\nRunning pandas (CPU) benchmark...")
            pandas_result = self.benchmark_pandas(test_file)
            print(
                f"  Mean time: {pandas_result['mean']:.4f}s ± {pandas_result['std']:.4f}s"
            )
            print(f"  Memory: {pandas_result['memory_mb']:.2f} MB")

            # Run cuDF benchmark
            if GPU_AVAILABLE:
                print("\nRunning cuDF (GPU) benchmark...")
                cudf_result = self.benchmark_cudf(test_file)
                if "error" not in cudf_result:
                    print(
                        f"  Mean time: {cudf_result['mean']:.4f}s ± {cudf_result['std']:.4f}s"
                    )
                    print(f"  Memory: {cudf_result['memory_mb']:.2f} MB")

                    speedup = pandas_result["mean"] / cudf_result["mean"]
                    print(f"\n🚀 GPU Speedup: {speedup:.2f}x")
                else:
                    print(f"  Error: {cudf_result['error']}")
                    cudf_result = None
            else:
                cudf_result = None

            # Store results
            self.results.append(
                {
                    "size": size,
                    "pandas": pandas_result,
                    "cudf": cudf_result,
                    "speedup": pandas_result["mean"] / cudf_result["mean"]
                    if cudf_result and "mean" in cudf_result
                    else None,
                }
            )

        # Save results
        results_file = output_dir / "results" / "data_loading_results.json"
        results_file.parent.mkdir(parents=True, exist_ok=True)
        with open(results_file, "w") as f:
            json.dump(self.results, f, indent=2)
        print(f"\n✓ Results saved to {results_file}")

    def print_summary(self) -> None:
        """Print summary of all benchmark results."""
        print("\n" + "=" * 60)
        print("BENCHMARK SUMMARY")
        print("=" * 60)
        print(f"{'Size':<15} {'Pandas (s)':<15} {'cuDF (s)':<15} {'Speedup':<10}")
        print("-" * 60)

        for result in self.results:
            size = f"{result['size']:,}"
            pandas_time = f"{result['pandas']['mean']:.4f}"
            cudf_time = f"{result['cudf']['mean']:.4f}" if result["cudf"] else "N/A"
            speedup = f"{result['speedup']:.2f}x" if result["speedup"] else "N/A"
            print(f"{size:<15} {pandas_time:<15} {cudf_time:<15} {speedup:<10}")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark data loading: pandas vs cuDF"
    )
    parser.add_argument(
        "--sizes",
        type=str,
        default="1000,10000,100000,1000000",
        help="Comma-separated list of data sizes to test",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent,
        help="Output directory for test data and results",
    )
    parser.add_argument("--warmup", type=int, default=2, help="Number of warmup runs")
    parser.add_argument("--runs", type=int, default=5, help="Number of benchmark runs")

    args = parser.parse_args()

    # Parse sizes
    sizes = [int(s.strip()) for s in args.sizes.split(",")]

    # Check GPU availability
    if not GPU_AVAILABLE:
        print("\n⚠️  WARNING: RAPIDS cuDF not available!")
        print("Only pandas benchmarks will run.")
        print("\nTo install RAPIDS:")
        print(
            "  conda install -c rapidsai -c conda-forge -c nvidia rapids=23.10 python=3.10 cudatoolkit=11.8"
        )
        print("\nOr use Docker:")
        print(
            "  docker run --gpus all rapidsai/rapidsai:23.10-cuda11.8-runtime-ubuntu22.04-py3.10"
        )
        print()

    # Run benchmarks
    runner = BenchmarkRunner(warmup_runs=args.warmup, benchmark_runs=args.runs)
    runner.run_comparison(sizes, args.output_dir)
    runner.print_summary()

    print("\n✓ Benchmarking complete!")


if __name__ == "__main__":
    main()
