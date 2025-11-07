"""
GPU Utilities for RAPIDS Pipeline

Helper functions for GPU operations, memory management, and performance monitoring.
"""

import time
from contextlib import contextmanager
from typing import Optional, Dict, Any
import warnings

try:
    import cupy as cp
    import cudf

    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False


class GPUMemoryManager:
    """Manages GPU memory allocation and cleanup."""

    @staticmethod
    def clear_memory():
        """Clear GPU memory cache."""
        if GPU_AVAILABLE:
            cp.get_default_memory_pool().free_all_blocks()
            cp.get_default_pinned_memory_pool().free_all_blocks()

    @staticmethod
    def get_memory_info() -> Dict[str, float]:
        """Get current GPU memory usage."""
        if not GPU_AVAILABLE:
            return {"error": "GPU not available"}

        mempool = cp.get_default_memory_pool()
        return {
            "used_bytes": mempool.used_bytes(),
            "total_bytes": mempool.total_bytes(),
            "used_gb": mempool.used_bytes() / 1e9,
            "total_gb": mempool.total_bytes() / 1e9,
        }

    @staticmethod
    def print_memory_usage():
        """Print current GPU memory usage."""
        info = GPUMemoryManager.get_memory_info()
        if "error" in info:
            print(f"  {info['error']}")
        else:
            print(f"  GPU Memory: {info['used_gb']:.2f} GB / {info['total_gb']:.2f} GB")


@contextmanager
def gpu_timer(operation_name: str, print_result: bool = True):
    """
    Context manager for timing GPU operations.

    Usage:
        with gpu_timer("Data Loading"):
            df = cudf.read_parquet('data.parquet')
    """
    if GPU_AVAILABLE:
        cp.cuda.Stream.null.synchronize()  # Ensure GPU is ready

    start = time.perf_counter()
    try:
        yield
    finally:
        if GPU_AVAILABLE:
            cp.cuda.Stream.null.synchronize()  # Wait for GPU to finish

        elapsed = time.perf_counter() - start
        if print_result:
            print(f"⏱️  {operation_name}: {elapsed:.4f} seconds")


def to_gpu(df, engine: str = "cudf"):
    """
    Convert pandas DataFrame to GPU DataFrame.

    Args:
        df: pandas DataFrame or cuDF DataFrame
        engine: 'cudf' or 'pandas' (for fallback)

    Returns:
        cuDF DataFrame if GPU available, else pandas DataFrame
    """
    if not GPU_AVAILABLE or engine == "pandas":
        return df

    try:
        if isinstance(df, cudf.DataFrame):
            return df
        return cudf.from_pandas(df)
    except Exception as e:
        warnings.warn(f"Failed to convert to GPU: {e}. Using CPU.")
        return df


def to_cpu(df):
    """
    Convert GPU DataFrame to pandas DataFrame.

    Args:
        df: cuDF DataFrame or pandas DataFrame

    Returns:
        pandas DataFrame
    """
    if GPU_AVAILABLE and isinstance(df, cudf.DataFrame):
        return df.to_pandas()
    return df


def adaptive_engine(data_size: int, threshold: int = 10_000) -> str:
    """
    Choose processing engine based on data size.

    For small datasets, CPU might be faster due to GPU transfer overhead.

    Args:
        data_size: Number of rows in dataset
        threshold: Minimum rows to use GPU (default: 10,000)

    Returns:
        'cudf' for GPU or 'pandas' for CPU
    """
    if not GPU_AVAILABLE:
        return "pandas"

    if data_size < threshold:
        print(f"ℹ️  Small dataset ({data_size:,} rows). Using CPU for efficiency.")
        return "pandas"

    print(f"ℹ️  Large dataset ({data_size:,} rows). Using GPU acceleration.")
    return "cudf"


def check_gpu_health() -> Dict[str, Any]:
    """
    Check GPU health and return diagnostic information.

    Returns:
        Dictionary with GPU status, memory, utilization, etc.
    """
    if not GPU_AVAILABLE:
        return {"available": False, "error": "GPU or RAPIDS not installed"}

    try:
        import pynvml

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)

        memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
        utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
        temperature = pynvml.nvmlDeviceGetTemperature(
            handle, pynvml.NVML_TEMPERATURE_GPU
        )

        pynvml.nvmlShutdown()

        return {
            "available": True,
            "memory_used_gb": memory.used / 1e9,
            "memory_total_gb": memory.total / 1e9,
            "memory_percent": (memory.used / memory.total) * 100,
            "gpu_utilization_percent": utilization.gpu,
            "temperature_c": temperature,
        }
    except ImportError:
        return {
            "available": True,
            "error": "pynvml not installed (pip install nvidia-ml-py3)",
            "memory_info": GPUMemoryManager.get_memory_info(),
        }
    except Exception as e:
        return {
            "available": True,
            "error": str(e),
            "memory_info": GPUMemoryManager.get_memory_info(),
        }


def optimize_dtypes(df, inplace: bool = False):
    """
    Optimize DataFrame dtypes to reduce memory usage.

    Converts:
    - float64 -> float32 where safe
    - int64 -> int32 where safe

    Args:
        df: cuDF or pandas DataFrame
        inplace: Modify DataFrame in place

    Returns:
        Optimized DataFrame
    """
    if not inplace:
        df = df.copy()

    for col in df.columns:
        col_type = df[col].dtype

        if col_type == "float64":
            df[col] = df[col].astype("float32")
        elif col_type == "int64":
            # Check if values fit in int32
            if GPU_AVAILABLE and isinstance(df, cudf.DataFrame):
                max_val = df[col].max()
                min_val = df[col].min()
            else:
                max_val = df[col].max()
                min_val = df[col].min()

            if min_val >= -2147483648 and max_val <= 2147483647:
                df[col] = df[col].astype("int32")

    return df


if __name__ == "__main__":
    # Diagnostic check
    print("\n" + "=" * 60)
    print("GPU DIAGNOSTICS")
    print("=" * 60)

    health = check_gpu_health()

    if health["available"]:
        print("✓ GPU Available")
        if "error" not in health:
            print(
                f"  Memory: {health['memory_used_gb']:.2f} GB / {health['memory_total_gb']:.2f} GB ({health['memory_percent']:.1f}%)"
            )
            print(f"  Utilization: {health['gpu_utilization_percent']}%")
            print(f"  Temperature: {health['temperature_c']}°C")
        else:
            print(f"  {health['error']}")
    else:
        print("✗ GPU Not Available")
        print(f"  {health['error']}")

    print("\nRAAPIDS Version:", cudf.__version__ if GPU_AVAILABLE else "Not installed")
    print("=" * 60)
