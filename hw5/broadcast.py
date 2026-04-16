"""
Broadcast Algorithms — CS 536 Assignment 5
==========================================
Implements two Broadcast algorithms using PyTorch Gloo backend:
  - binary_tree   : Binary Tree Broadcast
  - binomial_tree : Binomial Tree Broadcast

Also benchmarks both and produces two plots:
  Plot 1 — Completion time vs message size (fixed world_size=4)
  Plot 2 — Completion time vs number of ranks (fixed message size=1MB)

Usage:
  # Run a single algorithm to verify correctness:
  python broadcast.py --algo binary_tree
  python broadcast.py --algo binomial_tree
  python broadcast.py --algo binary_tree --world_size 8 --chunk_size 256

  # Run benchmarks and generate plots:
  python broadcast.py --benchmark
"""

import argparse
import math
import time

import torch
import torch.distributed as dist
import torch.multiprocessing as mp
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# =============================================================================
# Algorithm 1: Binary Tree Broadcast
# =============================================================================

def binary_tree_broadcast(tensor: torch.Tensor, src: int = 0) -> torch.Tensor:
    """
    Binary Tree Broadcast algorithm.

    Ranks are arranged in a virtual binary tree rooted at src=0.
    Each rank, once it receives data, forwards it to up to two children.
    Runs in ceil(log2(world_size)) steps.

    Virtual tree structure (0-indexed):
      Parent of rank r  : (r - 1) // 2
      Left child        : 2*r + 1
      Right child       : 2*r + 2

    Args:
        tensor : 1D tensor. On rank `src`, this is the data to broadcast.
                 On all other ranks, content is overwritten with src's data.
        src    : root rank (default 0).

    Returns:
        tensor with broadcast data on all ranks.
    """
    rank       = dist.get_rank()
    world_size = dist.get_world_size()

    # Remap so that src acts as virtual rank 0
    vrank = (rank - src) % world_size

    if vrank > 0:
        # I am a receiver — receive from my parent
        parent_vrank = (vrank - 1) // 2
        parent_rank  = (parent_vrank + src) % world_size
        dist.recv(tensor, src=parent_rank)

    # I am a sender — send to my left child
    left_vrank = 2 * vrank + 1
    if left_vrank < world_size:
        left_rank = (left_vrank + src) % world_size
        dist.send(tensor.clone(), dst=left_rank)

    # I am a sender — send to my right child
    right_vrank = 2 * vrank + 2
    if right_vrank < world_size:
        right_rank = (right_vrank + src) % world_size
        dist.send(tensor.clone(), dst=right_rank)

    return tensor


# =============================================================================
# Algorithm 2: Binomial Tree Broadcast
# =============================================================================

def binomial_tree_broadcast(tensor: torch.Tensor, src: int = 0) -> torch.Tensor:
    """
    Binomial Tree Broadcast algorithm.

    At step k, every rank that already has the data sends it to the rank
    that is exactly 2^k away (wrapping around). This forms a binomial tree.
    Runs in ceil(log2(world_size)) steps.

    Compared to binary tree:
      - Same number of steps
      - Each rank sends exactly once (to one partner per step it participates)
      - Better for small messages due to lower latency overhead
      - More natural fit for MPI collective implementations

    Args:
        tensor : 1D tensor. On rank `src`, this is the data to broadcast.
                 On all other ranks, content is overwritten with src's data.
        src    : root rank (default 0).

    Returns:
        tensor with broadcast data on all ranks.
    """
    rank       = dist.get_rank()
    world_size = dist.get_world_size()

    # Remap so that src acts as virtual rank 0
    vrank = (rank - src) % world_size

    num_steps = math.ceil(math.log2(world_size)) if world_size > 1 else 0

    for step in range(num_steps):
        distance = 1 << step   # 2^step

        if vrank < distance:
            # I have the data — send to partner at vrank + distance
            partner_vrank = vrank + distance
            if partner_vrank < world_size:
                partner_rank = (partner_vrank + src) % world_size
                dist.send(tensor.clone(), dst=partner_rank)

        elif distance <= vrank < 2 * distance:
            # I am a receiver this step
            sender_vrank = vrank - distance
            sender_rank  = (sender_vrank + src) % world_size
            dist.recv(tensor, src=sender_rank)

        # All other ranks wait — they will participate in later steps

    return tensor


# =============================================================================
# Algorithm dispatch
# =============================================================================

ALGORITHMS = {
    "binary_tree":   binary_tree_broadcast,
    "binomial_tree": binomial_tree_broadcast,
}

ALGO_LABELS = {
    "binary_tree":   "Binary Tree",
    "binomial_tree": "Binomial Tree",
}


# =============================================================================
# Verification worker
# =============================================================================

def verify_worker(rank, world_size, algo_name):
    dist.init_process_group(
        backend="gloo",
        init_method="tcp://127.0.0.1:29500",
        world_size=world_size,
        rank=rank,
    )

    chunk_size = 8
    src = 0

    # Root holds data; others hold zeros
    if rank == src:
        tensor = torch.arange(chunk_size, dtype=torch.float32)
    else:
        tensor = torch.zeros(chunk_size, dtype=torch.float32)

    algo_fn = ALGORITHMS[algo_name]
    result  = algo_fn(tensor, src=src)

    # Ground truth via PyTorch built-in
    ref = torch.arange(chunk_size, dtype=torch.float32)
    dist.broadcast(ref, src=src)

    match = torch.allclose(result, ref)
    print(f"[Rank {rank}] result: {result.tolist()}  |  Correct: {match}")

    dist.destroy_process_group()


# =============================================================================
# Benchmark worker
# =============================================================================

N_REPEATS = 3

def benchmark_worker(rank, world_size, algo_name, chunk_size, result_list, port):
    dist.init_process_group(
        backend="gloo",
        init_method=f"tcp://127.0.0.1:{port}",
        world_size=world_size,
        rank=rank,
    )

    src = 0
    algo_fn = ALGORITHMS[algo_name]

    def make_tensor():
        if rank == src:
            return torch.ones(chunk_size, dtype=torch.float32)
        return torch.zeros(chunk_size, dtype=torch.float32)

    # Warmup
    algo_fn(make_tensor(), src=src)
    dist.barrier()

    # Timed runs
    times = []
    for _ in range(N_REPEATS):
        dist.barrier()
        t0 = time.perf_counter()
        algo_fn(make_tensor(), src=src)
        dist.barrier()
        times.append(time.perf_counter() - t0)

    if rank == 0:
        result_list[0] = min(times)

    dist.destroy_process_group()


def measure(algo_name, world_size, msg_bytes, port=29500):
    """Run benchmark for one (algo, world_size, msg_size) config."""
    chunk_size = msg_bytes // 4   # float32 = 4 bytes
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
# Benchmark configuration
# =============================================================================

MSG_SIZES_BYTES  = [2**i for i in range(10, 26)]   # 1KB → 32MB
RANK_COUNTS      = [2, 4, 8]
FIXED_WORLD_SIZE = 4
FIXED_MSG_BYTES  = 1024 * 1024   # 1MB


# =============================================================================
# Plot 1: Completion time vs message size
# =============================================================================

def plot_vs_message_size():
    print(f"\n=== Broadcast Plot 1: Time vs Message Size (world_size={FIXED_WORLD_SIZE}) ===\n")

    results = {name: [] for name in ALGORITHMS}

    for msg_bytes in MSG_SIZES_BYTES:
        mb = msg_bytes / (1024 * 1024)
        print(f"  Message size: {mb:.3f} MB")
        for algo_name in ALGORITHMS:
            t = measure(algo_name, FIXED_WORLD_SIZE, msg_bytes, port=29502)
            if t is not None:
                results[algo_name].append((msg_bytes, t * 1000))
                print(f"    {ALGO_LABELS[algo_name]:15s}: {t*1000:.2f} ms")

    fig, ax = plt.subplots(figsize=(9, 5))
    colors  = ["#5C6BC0", "#EF5350"]
    markers = ["o", "s"]

    x_ticks = []
    for algo_name, color, marker in zip(ALGORITHMS, colors, markers):
        if not results[algo_name]:
            continue
        xs, ys = zip(*results[algo_name])
        ax.plot(xs, ys, label=ALGO_LABELS[algo_name],
                color=color, marker=marker, linewidth=1.8, markersize=5)
        if not x_ticks:
            x_ticks = list(xs)

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
    ax.set_xlabel("Message size", fontsize=11)
    ax.set_ylabel("Completion time (ms, log scale)", fontsize=11)
    ax.set_title(
        f"Broadcast: completion time vs message size\n"
        f"(world_size={FIXED_WORLD_SIZE}, {N_REPEATS} runs, best time)",
        fontsize=11,
    )
    ax.legend(fontsize=10)
    ax.grid(True, which="both", linestyle="--", alpha=0.4)
    fig.tight_layout()

    path = "broadcast_vs_msgsize.png"
    fig.savefig(path, dpi=150)
    print(f"\n  Saved → {path}")
    plt.close(fig)


# =============================================================================
# Plot 2: Completion time vs number of ranks
# =============================================================================

def plot_vs_ranks():
    print(f"\n=== Broadcast Plot 2: Time vs Ranks (msg_size={FIXED_MSG_BYTES//1024}KB) ===\n")

    results = {name: [] for name in ALGORITHMS}

    for world_size in RANK_COUNTS:
        print(f"  world_size={world_size}")
        for algo_name in ALGORITHMS:
            t = measure(algo_name, world_size, FIXED_MSG_BYTES, port=29503)
            if t is not None:
                results[algo_name].append((world_size, t * 1000))
                print(f"    {ALGO_LABELS[algo_name]:15s}: {t*1000:.2f} ms")

    fig, ax = plt.subplots(figsize=(8, 5))
    colors  = ["#5C6BC0", "#EF5350"]
    markers = ["o", "s"]

    for algo_name, color, marker in zip(ALGORITHMS, colors, markers):
        if not results[algo_name]:
            continue
        xs, ys = zip(*results[algo_name])
        ax.plot(xs, ys, label=ALGO_LABELS[algo_name],
                color=color, marker=marker, linewidth=1.8, markersize=6)

    ax.set_xticks(RANK_COUNTS)
    ax.set_xlabel("Number of ranks (world size)", fontsize=11)
    ax.set_ylabel("Completion time (ms)", fontsize=11)
    ax.set_title(
        f"Broadcast: completion time vs number of ranks\n"
        f"(msg_size={FIXED_MSG_BYTES//1024}KB, {N_REPEATS} runs, best time)",
        fontsize=11,
    )
    ax.legend(fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()

    path = "broadcast_vs_ranks.png"
    fig.savefig(path, dpi=150)
    print(f"\n  Saved → {path}")
    plt.close(fig)


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)

    parser = argparse.ArgumentParser(description="Broadcast algorithm runner & benchmarker")
    parser.add_argument(
        "--algo",
        choices=list(ALGORITHMS.keys()),
        help="Run and verify a single algorithm",
    )
    parser.add_argument(
        "--world_size", type=int, default=4,
        help="Number of ranks for verification (default: 4)",
    )
    parser.add_argument(
        "--chunk_size", type=int, default=8,
        help="Number of float32 elements per rank (default: 8)",
    )
    parser.add_argument(
        "--benchmark", action="store_true",
        help="Run full benchmark and generate plots",
    )
    args = parser.parse_args()

    if args.benchmark:
        plot_vs_message_size()
        plot_vs_ranks()
        print("\nDone! Check broadcast_vs_msgsize.png and broadcast_vs_ranks.png")

    elif args.algo:
        print(f"\nVerifying [{args.algo}] with world_size={args.world_size}, chunk_size={args.chunk_size}\n")
        mp.spawn(
            verify_worker,
            args=(args.world_size, args.algo),
            nprocs=args.world_size,
            join=True,
        )

    else:
        parser.print_help()