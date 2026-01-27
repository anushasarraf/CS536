#!/usr/bin/env bash

echo "Running Question 1 (Ping + Distance vs RTT)..."
python3 question1.py

echo
echo "Running Question 2 (Traceroute + Latency Breakdown)..."
python3 question2.py

echo
echo "All experiments completed."
echo "Generated files:"
echo "  distance_vs_rtt.pdf"
echo "  q2_stacked_latency.pdf"
echo "  q2_hopcount_vs_rtt.pdf"
