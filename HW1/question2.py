#!/usr/bin/env python3

import subprocess
import random
import re
import matplotlib.pyplot as plt
import os
from question1 import load_ips

# -------------------------
# CONFIG
# -------------------------

N_TARGETS = 5
MAX_HOPS = 30

os.makedirs("plots", exist_ok=True)

# -------------------------
# TRACEROUTE
# -------------------------

def run_traceroute(ip):
    cmd = ["traceroute", "-I", "-m", str(MAX_HOPS), ip]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def parse_traceroute(output):
    hops = []
    for line in output.splitlines():
        # Example line:
        #  3  10.10.0.1  12.1 ms  12.3 ms  12.2 ms
        rtts = re.findall(r"([\d\.]+)\s+ms", line)
        if rtts:
            # use average RTT for this hop
            avg_rtt = sum(map(float, rtts)) / len(rtts)
            hops.append(avg_rtt)
    return hops

# -------------------------
# MAIN
# -------------------------

def main():
    ips = load_ips()
    targets = random.sample(ips, N_TARGETS)

    hop_data = {}
    hop_counts = []
    final_rtts = []

    for ip in targets:
        print(f"Tracing {ip}")
        out = run_traceroute(ip)
        # hops is a list for hop times from source to destination
        hops = parse_traceroute(out)

        hop_data[ip] = hops
        hop_counts.append(len(hops))
        final_rtts.append(hops[-1] if hops else None)

    # print("hop counts:", hop_counts)

    # -------------------------
    # STACKED BAR PLOT
    # -------------------------

    # hop numbers can be different for different destinations
    max_len = max(len(h) for h in hop_data.values())
    padded = []

    for hops in hop_data.values():
        single_hop_times = []
        prev = 0
        for rtt in hops:
            single_hop_times.append(max(0, rtt - prev)) # hop time cannot be negative
            prev = rtt

        # to make the list lengths same for plotting, we pad the remaining elements with 0
        single_hop_times += [0] * (max_len - len(single_hop_times))
        padded.append(single_hop_times)

    bottoms = [0] * N_TARGETS
    labels = list(hop_data.keys()) # IP addresses

    plt.figure(figsize=(10, 5))

    for i in range(max_len):
        vals = [padded[j][i] for j in range(N_TARGETS)]

        plt.bar(labels, vals, bottom=bottoms)

        # for stacking the values vertically, we update the bottoms by adding the previous hop times
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

    plt.figure()
    plt.scatter(hop_counts, final_rtts)
    plt.xlabel("Hop count")
    plt.ylabel("Final RTT (ms)")
    plt.title("Hop Count vs RTT")
    plt.tight_layout()
    plt.savefig("plots/q2_hopcount_vs_rtt.pdf")
    plt.close()

    print("Saved q2_stacked_latency.pdf and q2_hopcount_vs_rtt.pdf")

if __name__ == "__main__":
    main()
