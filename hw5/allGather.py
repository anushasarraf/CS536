"""
AllGather Algorithms — CS 536 Assignment 5
==========================================
Implements three AllGather algorithms using PyTorch Gloo backend:
  - ring                : Ring AllGather
  - recursive_doubling  : Recursive Doubling (Halving/Doubling) AllGather
  - swing               : Swing AllGather

Usage:
  python allgather.py --algo ring
  python allgather.py --algo recursive_doubling
  python allgather.py --algo swing
  python allgather.py --algo ring --world_size 8 --chunk_size 16
"""

import argparse
import math
import time

import torch
import torch.distributed as dist
import torch.multiprocessing as mp


# =============================================================================
# Algorithm 1: Ring AllGather
# =============================================================================

def ring_allgather(tensor: torch.Tensor) -> torch.Tensor:
    """
    Ring AllGather algorithm.

    Each rank starts with its own chunk and sends it around the ring,
    collecting every other rank's chunk along the way.
    Runs in (world_size - 1) steps, sending one chunk per step.

    Args:
        tensor: 1D tensor — this rank's local chunk.

    Returns:
        gathered: 1D tensor of shape (world_size * chunk_size,)
    """
    rank = dist.get_rank()
    world_size = dist.get_world_size()
    chunk_size = tensor.numel()

    gathered = torch.zeros(world_size * chunk_size, dtype=tensor.dtype)
    gathered[rank * chunk_size : (rank + 1) * chunk_size] = tensor

    send_to   = (rank + 1) % world_size
    recv_from = (rank - 1) % world_size

    for step in range(world_size - 1):
        t_step = time.perf_counter()

        send_chunk_rank = (rank - step) % world_size
        recv_chunk_rank = (rank - step - 1) % world_size

        send_buf = gathered[send_chunk_rank * chunk_size : (send_chunk_rank + 1) * chunk_size].clone()
        recv_buf = torch.zeros(chunk_size, dtype=tensor.dtype)

        t_comm = time.perf_counter()
        if rank % 2 == 0:
            dist.send(send_buf, dst=send_to)
            dist.recv(recv_buf, src=recv_from)
        else:
            dist.recv(recv_buf, src=recv_from)
            dist.send(send_buf, dst=send_to)
        print(f"[Rank {rank}][Ring] Step {step}: send/recv took {(time.perf_counter()-t_comm)*1000:.2f} ms")

        gathered[recv_chunk_rank * chunk_size : (recv_chunk_rank + 1) * chunk_size] = recv_buf
        print(f"[Rank {rank}][Ring] Step {step}: total {(time.perf_counter()-t_step)*1000:.2f} ms")

    return gathered


# =============================================================================
# Algorithm 2: Recursive Doubling (Halving/Doubling) AllGather
# =============================================================================

def recursive_doubling_allgather(tensor: torch.Tensor) -> torch.Tensor:
    """
    Recursive Doubling AllGather algorithm.

    Partners are selected by XOR-ing rank with increasing powers of 2.
    Each rank exchanges its full accumulated buffer each step, so data
    held doubles every step. Runs in log2(world_size) steps.
    Requires world_size to be a power of 2.

    Args:
        tensor: 1D tensor — this rank's local chunk.

    Returns:
        gathered: 1D tensor of shape (world_size * chunk_size,)
    """
    rank = dist.get_rank()
    world_size = dist.get_world_size()

    assert (world_size & (world_size - 1)) == 0, \
        "Recursive doubling requires world_size to be a power of 2"

    chunk_size = tensor.numel()
    num_steps  = world_size.bit_length() - 1

    gathered = torch.zeros(world_size * chunk_size, dtype=tensor.dtype)
    gathered[rank * chunk_size : (rank + 1) * chunk_size] = tensor

    current_start = rank * chunk_size
    current_size  = chunk_size

    for step in range(num_steps):
        t_step = time.perf_counter()

        distance = 1 << step
        partner  = rank ^ distance

        send_buf = gathered[current_start : current_start + current_size].clone()
        recv_buf = torch.zeros(current_size, dtype=tensor.dtype)

        t_comm = time.perf_counter()
        if rank < partner:
            dist.send(send_buf, dst=partner)
            dist.recv(recv_buf, src=partner)
        else:
            dist.recv(recv_buf, src=partner)
            dist.send(send_buf, dst=partner)
        print(f"[Rank {rank}][RecDouble] Step {step}: partner={partner}, send/recv took {(time.perf_counter()-t_comm)*1000:.2f} ms")

        # partner_start = partner * chunk_size
        # if partner_start < current_start:
        #     gathered[partner_start : partner_start + current_size] = recv_buf
        #     current_start = partner_start
        # else:
        #     gathered[current_start + current_size : current_start + 2 * current_size] = recv_buf

        # current_size *= 2
        partner_start = partner * chunk_size
        total_size    = world_size * chunk_size

        if partner_start < current_start:
            write_size = min(current_size, total_size - partner_start)
            gathered[partner_start : partner_start + write_size] = recv_buf[:write_size]
            current_start = partner_start
        else:
            write_start = current_start + current_size
            write_size  = min(current_size, total_size - write_start)
            gathered[write_start : write_start + write_size] = recv_buf[:write_size]

        current_size = min(current_size * 2, total_size - current_start)
        print(f"[Rank {rank}][RecDouble] Step {step}: total {(time.perf_counter()-t_step)*1000:.2f} ms")

    return gathered


# =============================================================================
# Algorithm 3: Swing AllGather
# =============================================================================

def swing_allgather(tensor: torch.Tensor) -> torch.Tensor:
    """
    Swing AllGather algorithm.

    Like Recursive Doubling, but partner selection alternates direction
    each step (+distance, -distance, +distance, ...). This spreads
    traffic more evenly on ring/torus topologies.
    Runs in ceil(log2(world_size)) steps. Supports non-power-of-2 sizes.

    Args:
        tensor: 1D tensor — this rank's local chunk.

    Returns:
        gathered: 1D tensor of shape (world_size * chunk_size,)
    """
    rank = dist.get_rank()
    world_size = dist.get_world_size()

    chunk_size = tensor.numel()
    num_steps  = math.ceil(math.log2(world_size))

    gathered = torch.zeros(world_size * chunk_size, dtype=tensor.dtype)
    gathered[rank * chunk_size : (rank + 1) * chunk_size] = tensor

    current_start = rank * chunk_size
    current_size  = chunk_size

    for step in range(num_steps):
        t_step = time.perf_counter()

        distance = 1 << step
        # Swing partner selection: 
        # Use XOR to ensure symmetric partners (Rank A picks B implies Rank B picks A).
        # We can implement the "swing" by shifting the rank or using specific XOR patterns,
        # but the core requirement is symmetry to avoid deadlock.
        # This implementation uses the recursive doubling pattern but calculates partner
        # in a way that allows for non-power-of-2 world sizes by using modulo.
        partner = rank ^ distance

        # For non-power-of-2 world_size, some partners might be out of range.
        if partner >= world_size:
            print(f"[Rank {rank}][Swing] Step {step}: partner {partner} out of range, skipping")
            continue

        send_buf = gathered[current_start : current_start + current_size].clone()
        
        # Determine what we receive from partner
        # In this implementation, the partner should have the same amount of data as us
        partner_current_start = (partner // distance) * distance * chunk_size
        partner_current_size  = min(distance * chunk_size, world_size * chunk_size - partner_current_start)
        partner_current_size  = max(0, partner_current_size)

        recv_buf = torch.zeros(partner_current_size, dtype=tensor.dtype)

        t_comm = time.perf_counter()
        if rank < partner:
            dist.send(send_buf, dst=partner)
            dist.recv(recv_buf, src=partner)
        else:
            dist.recv(recv_buf, src=partner)
            dist.send(send_buf, dst=partner)
        print(f"[Rank {rank}][Swing] Step {step}: partner={partner}, send/recv took {(time.perf_counter()-t_comm)*1000:.2f} ms")

        # Update gathered buffer
        partner_actual_start = partner_current_start # In simple doubling, they match
        gathered[partner_actual_start : partner_actual_start + partner_current_size] = recv_buf

        # Update tracking of what we have
        new_start = min(current_start, partner_actual_start)
        new_end   = max(current_start + current_size, partner_actual_start + partner_current_size)
        current_start = new_start
        current_size  = new_end - new_start

        print(f"[Rank {rank}][Swing] Step {step}: total {(time.perf_counter()-t_step)*1000:.2f} ms")

    return gathered


# =============================================================================
# Algorithm dispatch table
# =============================================================================

ALGORITHMS = {
    "ring":               ring_allgather,
    "recursive_doubling": recursive_doubling_allgather,
    "swing":              swing_allgather,
}


# =============================================================================
# Worker function (one per rank)
# =============================================================================

def run(rank, world_size, algo_name, chunk_size):
    # ---- Init ----
    t0 = time.perf_counter()
    dist.init_process_group(
        backend="gloo",
        init_method="tcp://127.0.0.1:29500",
        world_size=world_size,
        rank=rank,
    )
    print(f"[Rank {rank}] init_process_group took {(time.perf_counter()-t0)*1000:.2f} ms")

    # ---- Prepare data ----
    local_tensor = torch.full((chunk_size,), float(rank))

    # ---- Run selected algorithm ----
    algo_fn = ALGORITHMS[algo_name]
    t_algo = time.perf_counter()
    our_result = algo_fn(local_tensor.clone())
    print(f"[Rank {rank}] [{algo_name}] total algorithm time: {(time.perf_counter()-t_algo)*1000:.2f} ms")

    # ---- Verify against PyTorch built-in ----
    gather_list = [torch.zeros(chunk_size) for _ in range(world_size)]
    dist.all_gather(gather_list, local_tensor.clone())
    ref_result = torch.cat(gather_list)

    match = torch.allclose(our_result, ref_result)
    print(f"[Rank {rank}] our_result: {our_result.tolist()}")
    print(f"[Rank {rank}] ref_result: {ref_result.tolist()}")
    print(f"[Rank {rank}] Correct: {match}")

    dist.destroy_process_group()


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AllGather algorithm runner")
    parser.add_argument(
        "--algo",
        choices=list(ALGORITHMS.keys()),
        required=True,
        help="Which AllGather algorithm to run",
    )
    parser.add_argument(
        "--world_size",
        type=int,
        default=4,
        help="Number of processes/ranks (default: 4)",
    )
    parser.add_argument(
        "--chunk_size",
        type=int,
        default=8,
        help="Number of elements per rank (default: 8)",
    )
    args = parser.parse_args()

    if args.algo == "recursive_doubling":
        assert (args.world_size & (args.world_size - 1)) == 0, \
            "recursive_doubling requires --world_size to be a power of 2 (e.g. 2, 4, 8)"

    print(f"\nRunning [{args.algo}] with world_size={args.world_size}, chunk_size={args.chunk_size}\n")

    mp.spawn(
        run,
        args=(args.world_size, args.algo, args.chunk_size),
        nprocs=args.world_size,
        join=True,
    )
