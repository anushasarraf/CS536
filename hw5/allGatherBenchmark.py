"""
AllGather Benchmark & Plots — CS 536 Assignment 5
==================================================
Benchmarks all three AllGather algorithms and produces two plots:

  Plot 1 — Completion time vs message size (fixed world_size=4)
  Plot 2 — Completion time vs number of ranks (fixed message size=1MB)

Usage:
  python allgather_benchmark.py

Requires:
  pip install torch matplotlib
  (allgather.py must be in the same directory)
"""

import math
import time
import os
import torch
import torch.distributed as dist
import torch.multiprocessing as mp
import matplotlib
matplotlib.use("Agg")   # no display needed
import matplotlib.pyplot as plt

# Import the three algorithms from your existing file
from allGather import ring_allgather, recursive_doubling_allgather, swing_allgather

# =============================================================================
# Configuration
# =============================================================================

# Message sizes for Plot 1 (in bytes, as powers of 2 from 1KB to 32MB)
MSG_SIZES_BYTES = [2**i for i in range(10, 26)]   # 1KB → 32MB

# Number of ranks for Plot 2
RANK_COUNTS = [2, 4, 8]

# Fixed values
FIXED_WORLD_SIZE = 4          # used in Plot 1
FIXED_MSG_BYTES  = 1024*1024  # 1MB, used in Plot 2

# Repetitions per measurement (median is taken)
N_REPEATS = 3

PORT = 29500

ALGORITHMS = {
    "Ring":               ring_allgather,
    "Recursive Doubling": recursive_doubling_allgather,
    #"Swing":              swing_allgather,
}

# =============================================================================
# Worker: runs one algorithm for one (world_size, chunk_size) config
# and returns elapsed time via a shared list
# =============================================================================

def benchmark_worker(rank, world_size, algo_name, chunk_size, result_list, port):
    dist.init_process_group(
        backend="gloo",
        init_method=f"tcp://127.0.0.1:{port}",
        world_size=world_size,
        rank=rank,
    )

    algo_fn = ALGORITHMS[algo_name]
    local_tensor = torch.zeros(chunk_size, dtype=torch.float32)

    # Warmup run (not measured)
    _ = algo_fn(local_tensor.clone())
    dist.barrier()

    # Timed runs
    times = []
    for _ in range(N_REPEATS):
        dist.barrier()
        t0 = time.perf_counter()
        _ = algo_fn(local_tensor.clone())
        dist.barrier()
        times.append(time.perf_counter() - t0)

    # Only rank 0 records the result
    if rank == 0:
        result_list[0] = min(times)   # use best time across repeats

    dist.destroy_process_group()


def measure(algo_name, world_size, msg_bytes, port=PORT):
    """
    Spawn world_size processes, run the algorithm, return elapsed seconds.
    Returns None if the config is invalid (e.g. recursive doubling + non-pow2).
    """
    # Recursive doubling only works for power-of-2 world sizes
    if algo_name == "Recursive Doubling" and (world_size & (world_size - 1)) != 0:
        return None

    # chunk_size in float32 elements (4 bytes each)
    chunk_size = msg_bytes // 4
    if chunk_size == 0:
        return None

    manager = mp.Manager()
    result  = manager.list([None])

    mp.spawn(
        benchmark_worker,
        args=(world_size, algo_name, chunk_size, result, port),
        nprocs=world_size,
        join=True,
    )
    return result[0]


# =============================================================================
# Plot 1: Completion time vs message size (fixed world_size)
# =============================================================================

def plot_vs_message_size():
    print(f"\n=== Plot 1: Time vs Message Size (world_size={FIXED_WORLD_SIZE}) ===\n")

    results = {name: [] for name in ALGORITHMS}

    for msg_bytes in MSG_SIZES_BYTES:
        mb = msg_bytes / (1024 * 1024)
        print(f"  Message size: {mb:.2f} MB")
        for algo_name in ALGORITHMS:
            t = measure(algo_name, FIXED_WORLD_SIZE, msg_bytes)
            if t is not None:
                results[algo_name].append((msg_bytes, t * 1000))  # ms
                print(f"    {algo_name:22s}: {t*1000:.2f} ms")
            else:
                print(f"    {algo_name:22s}: skipped (invalid config)")

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(9, 5))

    colors    = ["#5C6BC0", "#26A69A", "#EF5350"]
    markers   = ["o", "s", "^"]
    x_labels  = []
    x_ticks   = []

    for (algo_name, color, marker) in zip(ALGORITHMS, colors, markers):
        if not results[algo_name]:
            continue
        xs, ys = zip(*results[algo_name])
        ax.plot(
            xs, ys,
            label=algo_name,
            color=color,
            marker=marker,
            linewidth=1.8,
            markersize=5,
        )
        if not x_ticks:
            x_ticks  = list(xs)

    # Format x-axis as human-readable sizes
    def fmt_bytes(b):
        if b >= 1024 * 1024:
            return f"{b//(1024*1024)}MB"
        elif b >= 1024:
            return f"{b//1024}KB"
        return f"{b}B"

    ax.set_xscale("log", base=2)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels([fmt_bytes(x) for x in x_ticks], rotation=45, ha="right", fontsize=8)
    ax.set_yscale("log")
    ax.set_xlabel("Message size (per rank)", fontsize=11)
    ax.set_ylabel("Completion time (ms, log scale)", fontsize=11)
    ax.set_title(f"AllGather: completion time vs message size\n(world_size={FIXED_WORLD_SIZE}, {N_REPEATS} runs, best time)", fontsize=11)
    ax.legend(fontsize=10)
    ax.grid(True, which="both", linestyle="--", alpha=0.4)
    fig.tight_layout()

    path = "allgather_vs_msgsize.png"
    fig.savefig(path, dpi=150)
    print(f"\n  Saved → {path}")
    plt.close(fig)


# =============================================================================
# Plot 2: Completion time vs number of ranks (fixed message size)
# =============================================================================

def plot_vs_ranks():
    print(f"\n=== Plot 2: Time vs Number of Ranks (msg_size={FIXED_MSG_BYTES//1024}KB) ===\n")

    results = {name: [] for name in ALGORITHMS}

    for world_size in RANK_COUNTS:
        print(f"  world_size={world_size}")
        for algo_name in ALGORITHMS:
            t = measure(algo_name, world_size, FIXED_MSG_BYTES, port=PORT + 1)
            if t is not None:
                results[algo_name].append((world_size, t * 1000))  # ms
                print(f"    {algo_name:22s}: {t*1000:.2f} ms")
            else:
                print(f"    {algo_name:22s}: skipped (invalid config)")

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(8, 5))

    colors  = ["#5C6BC0", "#26A69A", "#EF5350"]
    markers = ["o", "s", "^"]

    for (algo_name, color, marker) in zip(ALGORITHMS, colors, markers):
        if not results[algo_name]:
            continue
        xs, ys = zip(*results[algo_name])
        ax.plot(
            xs, ys,
            label=algo_name,
            color=color,
            marker=marker,
            linewidth=1.8,
            markersize=6,
        )

    ax.set_xticks(RANK_COUNTS)
    ax.set_xlabel("Number of ranks (world size)", fontsize=11)
    ax.set_ylabel("Completion time (ms)", fontsize=11)
    ax.set_title(
        f"AllGather: completion time vs number of ranks\n"
        f"(msg_size={FIXED_MSG_BYTES//1024}KB, {N_REPEATS} runs, best time)",
        fontsize=11,
    )
    ax.legend(fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()

    path = "allgather_vs_ranks.png"
    fig.savefig(path, dpi=150)
    print(f"\n  Saved → {path}")
    plt.close(fig)


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    # Required for mp.spawn on some platforms
    mp.set_start_method("spawn", force=True)

    plot_vs_message_size()
    plot_vs_ranks()

    print("\nDone! Check allgather_vs_msgsize.png and allgather_vs_ranks.png")