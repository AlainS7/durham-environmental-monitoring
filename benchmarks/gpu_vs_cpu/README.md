# GPU vs CPU Performance Benchmarks

This directory contains benchmarking scripts to compare performance between traditional pandas (CPU) and RAPIDS cuDF (GPU) implementations.

## Setup

### Prerequisites

1. **GPU-enabled environment** with NVIDIA GPU (compute capability 6.0+)
2. **CUDA Toolkit** 11.8 or later
3. **RAPIDS** installed

### Installation Options

#### Option 1: Docker (Recommended)

```bash
docker pull rapidsai/rapidsai:23.10-cuda11.8-runtime-ubuntu22.04-py3.10
docker run --gpus all --rm -it \
  -v $(pwd):/workspace \
  -p 8888:8888 \
  rapidsai/rapidsai:23.10-cuda11.8-runtime-ubuntu22.04-py3.10
```

#### Option 2: Conda Environment

```bash
conda create -n rapids-env -c rapidsai -c conda-forge -c nvidia \
  rapids=23.10 python=3.10 cudatoolkit=11.8
conda activate rapids-env
pip install -r requirements-rapids.txt
```

#### Option 3: Cloud GPU Instance

- **AWS:** g4dn.xlarge or p3.2xlarge
- **GCP:** n1-standard-4 with NVIDIA T4
- **Paperspace:** GPU+ or higher

## Benchmark Suite

### 1. Data Loading (`benchmark_data_loading.py`)

- **Test:** Load Parquet files and basic type conversions
- **Expected Speedup:** 5-10x

### 2. Data Cleaning (`benchmark_data_cleaning.py`)

- **Test:** Null handling, type conversions, timestamp parsing
- **Expected Speedup:** 10-20x

### 3. Feature Engineering (`benchmark_feature_engineering.py`)

- **Test:** Rolling windows, aggregations, statistical computations
- **Expected Speedup:** 20-50x

### 4. End-to-End Pipeline (`benchmark_full_pipeline.py`)

- **Test:** Complete data collection workflow
- **Expected Speedup:** 15-30x overall

## Running Benchmarks

### Single Benchmark

```bash
python benchmark_data_loading.py --sizes 1000,10000,100000,1000000
```

### Full Suite

```bash
./run_all_benchmarks.sh
```

### Generate Report

```bash
python generate_report.py --output benchmark_results.html
```

## Results

Results will be saved to:

- `results/` - Raw benchmark data (JSON)
- `plots/` - Performance visualization (PNG/SVG)
- `reports/` - HTML reports

### Sample Output

```
=== Benchmark: Data Loading ===
Data Size: 100,000 rows
Pandas (CPU):  2.345 seconds
cuDF (GPU):    0.123 seconds
Speedup:       19.1x
Memory:        CPU: 45.2 MB, GPU: 38.1 MB
```

## Key Metrics

For each benchmark, we measure:

- **Execution Time:** Wall-clock time for operation
- **Memory Usage:** Peak memory consumption
- **GPU Utilization:** Average GPU usage during operation
- **Data Transfer Time:** CPU↔GPU memory transfer overhead

## Tips for Accurate Benchmarking

1. **Warm-up runs:** Run each benchmark 3x, discard first result
2. **GPU memory:** Clear GPU memory between runs
3. **CPU cores:** Set `RAPIDS_NO_INITIALIZE=1` for fair comparison
4. **Data sizes:** Test on multiple sizes to find crossover point
5. **Monitoring:** Use `nvidia-smi dmon` to monitor GPU during benchmarks

## Troubleshooting

### Out of Memory

```python
# Reduce batch size or use chunking
import cudf
cudf.set_option('default_integer_bitwidth', 32)  # Use 32-bit instead of 64-bit
```

### Slow GPU Performance

```bash
# Check GPU is being used
nvidia-smi

# Verify CUDA version
python -c "import cudf; print(cudf.__version__)"
```

### Data Transfer Overhead

For small datasets (<10K rows), CPU might be faster due to transfer overhead. Use GPU for larger datasets.

## Next Steps

After benchmarking:

1. Update main README with performance metrics
2. Create blog post with visualizations
3. Add performance regression tests to CI/CD
4. Implement adaptive GPU/CPU selection based on data size
