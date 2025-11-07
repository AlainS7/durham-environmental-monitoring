#!/bin/bash
# Run all GPU vs CPU benchmarks in sequence

set -e  # Exit on error

echo "=========================================="
echo "  GPU vs CPU Benchmark Suite"
echo "=========================================="
echo ""

# Check for GPU
if ! command -v nvidia-smi &> /dev/null; then
    echo "⚠️  WARNING: nvidia-smi not found. GPU may not be available."
    echo ""
fi

# Create results directory
mkdir -p results

# Data sizes to test
SIZES="1000,10000,100000,1000000"

echo "Running benchmarks with data sizes: $SIZES"
echo ""

# 1. Data Loading Benchmark
echo "=========================================="
echo "1. Data Loading Benchmark"
echo "=========================================="
python benchmark_data_loading.py --sizes "$SIZES" --runs 5
echo ""

# 2. Data Cleaning Benchmark (when implemented)
if [ -f "benchmark_data_cleaning.py" ]; then
    echo "=========================================="
    echo "2. Data Cleaning Benchmark"
    echo "=========================================="
    python benchmark_data_cleaning.py --sizes "$SIZES" --runs 5
    echo ""
fi

# 3. Feature Engineering Benchmark (when implemented)
if [ -f "benchmark_feature_engineering.py" ]; then
    echo "=========================================="
    echo "3. Feature Engineering Benchmark"
    echo "=========================================="
    python benchmark_feature_engineering.py --sizes "$SIZES" --runs 5
    echo ""
fi

# 4. Full Pipeline Benchmark (when implemented)
if [ -f "benchmark_full_pipeline.py" ]; then
    echo "=========================================="
    echo "4. Full Pipeline Benchmark"
    echo "=========================================="
    python benchmark_full_pipeline.py --sizes "$SIZES" --runs 5
    echo ""
fi

echo "=========================================="
echo "  All Benchmarks Complete!"
echo "=========================================="
echo ""
echo "Results saved to: results/"
echo ""
echo "Next steps:"
echo "  1. Review results: ls -lh results/"
echo "  2. Generate report: python generate_report.py"
echo "  3. View visualizations: open results/*.png"
echo ""
