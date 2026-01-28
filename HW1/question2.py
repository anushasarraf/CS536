#!/usr/bin/env python3

import subprocess
import random
import re
import matplotlib.pyplot as plt
import os
import warnings
from question1 import load_ips

# -------------------------
# CONFIG
# -------------------------

N_TARGETS = 5
MAX_HOPS = 30

os.makedirs("plots", exist_ok=True)

# Suppress non-critical matplotlib warnings
warnings.filterwarnings("ignore", category=UserWarning)

# -------------------------
# TRACEROUTE
# -------------------------

def run_traceroute(ip):
    print(f" Running traceroute to destination: {ip}")
    cmd = ["traceroute", "-m", str(MAX_HOPS), ip]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def parse_traceroute(output):
    hops = []
    for line in output.splitlines():
        rtts = re.findall(r"([\d\.]+)\s+ms", line)
        if rtts:
            avg_rtt = sum(map(float, rtts)) / len(rtts)
            hops.append(avg_rtt)
    print(f" Extracted {len(hops)} hops with RTT measurements")
    return hops

# -------------------------
# MAIN
# -------------------------

def main():
    print(" Loading IP address list")
    ips = load_ips()

    print(f" Randomly selecting {N_TARGETS} target destinations")
    targets = random.sample(ips, N_TARGETS)

    hop_data = {}
    hop_counts = []
    final_rtts = []

    print(" Starting traceroute measurements\n")

    for ip in targets:
        out = run_traceroute(ip)
        hops = parse_traceroute(out)

        hop_data[ip] = hops
        hop_counts.append(len(hops))
        final_rtts.append(hops[-1] if hops else None)
        print(" Per-hop RTTs (average per hop):")
        for i, rtt in enumerate(hops, start=1):
            print(f"   Hop {i:2d}: {rtt:.2f} ms")

        # print(f" Final RTT for {ip}: {hops[-1] if hops else 'N/A'} ms\n")

    # -------------------------
    # STACKED BAR PLOT
    # -------------------------

    print(" Computing per-hop incremental latency values")

    max_len = max(len(h) for h in hop_data.values())
    padded = []

    for hops in hop_data.values():
        single_hop_times = []
        prev = 0
        for rtt in hops:
            single_hop_times.append(max(0, rtt - prev))
            prev = rtt

        single_hop_times += [0] * (max_len - len(single_hop_times))
        padded.append(single_hop_times)

    bottoms = [0] * N_TARGETS
    labels = list(hop_data.keys())

    print(" Generating stacked bar plot for hop-by-hop latency breakdown")

    plt.figure(figsize=(10, 5))

    for i in range(max_len):
        vals = [padded[j][i] for j in range(N_TARGETS)]
        plt.bar(labels, vals, bottom=bottoms)
        bottoms = [bottoms[j] + vals[j] for j in range(N_TARGETS)]

    plt.ylim(top=max(bottoms) * 1.1)
    plt.xticks(rotation=30)
    plt.xlabel("IP Addresses")
    plt.ylabel("Incremental RTT (ms)")
    plt.title("Latency Breakdown by Hop")
    plt.tight_layout()
    plt.savefig("plots/q2_stacked_latency.pdf")
    plt.close()

    # -------------------------
    # SCATTER PLOT
    # -------------------------

    print(" Generating scatter plot: hop count vs final RTT")

    plt.figure()
    plt.scatter(hop_counts, final_rtts)
    plt.xlabel("Hop count")
    plt.ylabel("Final RTT (ms)")
    plt.title("Hop Count vs RTT")
    plt.tight_layout()
    plt.savefig("plots/q2_hopcount_vs_rtt.pdf")
    plt.close()

    print("\n Saved output plots:")
    print("  - plots/q2_stacked_latency.pdf")
    print("  - plots/q2_hopcount_vs_rtt.pdf")
    print(" Question 2 execution completed successfully")

if __name__ == "__main__":
    main()
