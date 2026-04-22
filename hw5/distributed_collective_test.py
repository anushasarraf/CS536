#!/usr/bin/env python3
"""
Multi-node collective tester for CS536 HW5.

Run with torchrun across machines (gloo backend), for example:
  torchrun --nnodes=3 --nproc_per_node=1 --node_rank=0 \
    --master_addr=10.0.0.1 --master_port=29500 \
    distributed_collective_test.py --collective allgather --algo ring
"""

import argparse
import os
import time

import torch
import torch.distributed as dist

from allGather import ring_allgather, recursive_doubling_allgather, swing_allgather
from broadcast import binary_tree_broadcast, binomial_tree_broadcast


ALLGATHER_ALGOS = {
    "ring": ring_allgather,
    "recursive_doubling": recursive_doubling_allgather,
    "swing": swing_allgather,
}

BROADCAST_ALGOS = {
    "binary_tree": binary_tree_broadcast,
    "binomial_tree": binomial_tree_broadcast,
}


def world_info() -> tuple[int, int]:
    rank = dist.get_rank()
    world_size = dist.get_world_size()
    return rank, world_size


def run_allgather(algo_name: str, chunk_size: int, warmup: int, iters: int, verify: bool) -> bool:
    rank, world_size = world_info()
    algo_fn = ALLGATHER_ALGOS[algo_name]

    local_tensor = torch.full((chunk_size,), float(rank), dtype=torch.float32)
    ok = True

    if verify:
        our_result = algo_fn(local_tensor.clone())
        gather_list = [torch.zeros(chunk_size, dtype=torch.float32) for _ in range(world_size)]
        dist.all_gather(gather_list, local_tensor.clone())
        ref_result = torch.cat(gather_list)

        local_ok = torch.tensor(1 if torch.allclose(our_result, ref_result) else 0, dtype=torch.int32)
        dist.all_reduce(local_ok, op=dist.ReduceOp.MIN)
        ok = bool(local_ok.item())

    for _ in range(warmup):
        dist.barrier()
        _ = algo_fn(local_tensor.clone())

    times = []
    for _ in range(iters):
        dist.barrier()
        t0 = time.perf_counter()
        _ = algo_fn(local_tensor.clone())
        elapsed = torch.tensor(time.perf_counter() - t0, dtype=torch.float64)
        dist.all_reduce(elapsed, op=dist.ReduceOp.MAX)
        times.append(elapsed.item())

    if rank == 0:
        avg_ms = 1000.0 * sum(times) / len(times)
        min_ms = 1000.0 * min(times)
        max_ms = 1000.0 * max(times)
        payload_bytes = chunk_size * 4
        print(
            f"RESULT collective=allgather algo={algo_name} world_size={world_size} "
            f"chunk_size={chunk_size} payload_bytes={payload_bytes} "
            f"verify={ok} min_ms={min_ms:.3f} avg_ms={avg_ms:.3f} max_ms={max_ms:.3f}"
        )

    return ok


def run_broadcast(algo_name: str, chunk_size: int, warmup: int, iters: int, src: int, verify: bool) -> bool:
    rank, world_size = world_info()
    algo_fn = BROADCAST_ALGOS[algo_name]

    ok = True

    def make_tensor() -> torch.Tensor:
        if rank == src:
            return torch.arange(chunk_size, dtype=torch.float32)
        return torch.zeros(chunk_size, dtype=torch.float32)

    if verify:
        out = algo_fn(make_tensor(), src=src)
        ref = make_tensor()
        dist.broadcast(ref, src=src)

        local_ok = torch.tensor(1 if torch.allclose(out, ref) else 0, dtype=torch.int32)
        dist.all_reduce(local_ok, op=dist.ReduceOp.MIN)
        ok = bool(local_ok.item())

    for _ in range(warmup):
        dist.barrier()
        _ = algo_fn(make_tensor(), src=src)

    times = []
    for _ in range(iters):
        dist.barrier()
        t0 = time.perf_counter()
        _ = algo_fn(make_tensor(), src=src)
        elapsed = torch.tensor(time.perf_counter() - t0, dtype=torch.float64)
        dist.all_reduce(elapsed, op=dist.ReduceOp.MAX)
        times.append(elapsed.item())

    if rank == 0:
        avg_ms = 1000.0 * sum(times) / len(times)
        min_ms = 1000.0 * min(times)
        max_ms = 1000.0 * max(times)
        payload_bytes = chunk_size * 4
        print(
            f"RESULT collective=broadcast algo={algo_name} world_size={world_size} "
            f"chunk_size={chunk_size} payload_bytes={payload_bytes} src={src} "
            f"verify={ok} min_ms={min_ms:.3f} avg_ms={avg_ms:.3f} max_ms={max_ms:.3f}"
        )

    return ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-node tester for HW5 collectives")
    parser.add_argument("--collective", choices=["allgather", "broadcast"], required=True)
    parser.add_argument("--algo", required=True, help="Algorithm name for selected collective")
    parser.add_argument("--chunk_size", type=int, default=262144, help="float32 elements per rank (default: 262144 = 1MB)")
    parser.add_argument("--warmup", type=int, default=1, help="Warmup iterations (default: 1)")
    parser.add_argument("--iters", type=int, default=5, help="Measured iterations (default: 5)")
    parser.add_argument("--src", type=int, default=0, help="Broadcast source rank (default: 0)")
    parser.add_argument("--no_verify", action="store_true", help="Skip correctness check")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    dist.init_process_group(backend="gloo", init_method="env://")
    rank, world_size = world_info()

    if rank == 0:
        print(
            "INIT "
            f"master_addr={os.environ.get('MASTER_ADDR')} "
            f"master_port={os.environ.get('MASTER_PORT')} "
            f"world_size={world_size}"
        )

    verify = not args.no_verify

    try:
        if args.collective == "allgather":
            if args.algo not in ALLGATHER_ALGOS:
                if rank == 0:
                    print(f"ERROR invalid allgather algo '{args.algo}'. choices={list(ALLGATHER_ALGOS.keys())}")
                return 2
            if args.algo == "recursive_doubling" and (world_size & (world_size - 1)) != 0:
                if rank == 0:
                    print("ERROR recursive_doubling requires power-of-2 world_size (2,4,8,...)")
                return 2
            ok = run_allgather(args.algo, args.chunk_size, args.warmup, args.iters, verify)

        else:
            if args.algo not in BROADCAST_ALGOS:
                if rank == 0:
                    print(f"ERROR invalid broadcast algo '{args.algo}'. choices={list(BROADCAST_ALGOS.keys())}")
                return 2
            if not (0 <= args.src < world_size):
                if rank == 0:
                    print(f"ERROR src must be in [0, {world_size - 1}]")
                return 2
            ok = run_broadcast(args.algo, args.chunk_size, args.warmup, args.iters, args.src, verify)

        status = torch.tensor(1 if ok else 0, dtype=torch.int32)
        dist.all_reduce(status, op=dist.ReduceOp.MIN)

        if rank == 0 and status.item() == 0:
            print("ERROR verification failed on at least one rank")

        return 0 if status.item() == 1 else 1

    finally:
        dist.destroy_process_group()


if __name__ == "__main__":
    raise SystemExit(main())
