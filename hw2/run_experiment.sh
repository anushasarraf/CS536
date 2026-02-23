#!/usr/bin/env bash
# run_experiment.sh
# Full experiment pipeline for CS 536 Assignment 2, Part 1.
# Usage: ./run_experiment.sh [--n N] [--duration D] [--servers FILE]
# All arguments are forwarded to iperf3_client.py

set -e

OUTDIR="${OUTDIR:-/app/results}"
mkdir -p "$OUTDIR"

echo "========================================"
echo " CS 536 Assignment 2 - Part 1"
echo " iPerf Throughput Experiment"
echo "========================================"
echo ""

python3 /app/iperf3_client.py \
    --outdir "$OUTDIR" \
    "$@"

echo ""
echo "Experiment complete. Results in $OUTDIR/"
ls -lh "$OUTDIR/"
