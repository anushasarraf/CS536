"""
CS536 HW4 - Part 2: Best Topology for Arbitrary Traffic Matrix
n = 8, d = 4. Jointly optimize topology x and routing f to maximize
concurrent flow theta for a given hose-model traffic matrix T.

Formulation (matches the report exactly):

    max   theta
    s.t.  sum_{j != i} x_ij = d           forall i     (out-degree)
          sum_{i != j} x_ij = d           forall j     (in-degree)
          sum_{(s,t)} f^st_ij <= x_ij     forall (i,j) (capacity + existence)
          sum_{j!=v} f^st_vj - sum_{j!=v} f^st_jv
              =  theta * T_st   if v = s
              = -theta * T_st   if v = t                (flow conservation)
              =  0              otherwise
          x_ij in {0, 1, ..., d}
          f^st_ij >= 0,  theta >= 0

x_ij counts parallel links of capacity 1 between i and j. f^st_ij is the
amount of (s,t) commodity flow carried on the link bundle (i,j).
"""

import argparse
from collections import defaultdict
from pathlib import Path

import gurobipy as gp
from gurobipy import GRB
import numpy as np

N = 8
D = 4
NODES = list(range(N))
EDGES = [(i, j) for i in NODES for j in NODES if i != j]
PAIRS = [(s, t) for s in NODES for t in NODES if s != t]


def solve_topology(T, verbose=False):
    """Solve the joint topology+routing MIP. Returns (theta, x_vals, f_vals)."""
    ACTIVE = [(s, t) for (s, t) in PAIRS if T[s, t] > 1e-12]

    m = gp.Model("best_topology")
    m.setParam("OutputFlag", int(verbose))

    x = m.addVars(EDGES, vtype=GRB.INTEGER, lb=0, ub=D, name="x")
    f = m.addVars(ACTIVE, EDGES, lb=0.0, name="f")
    theta = m.addVar(lb=0.0, name="theta")

    m.setObjective(theta, GRB.MAXIMIZE)

    for i in NODES:
        m.addConstr(gp.quicksum(x[i, j] for j in NODES if j != i) == D,
                    name=f"out_deg[{i}]")
        m.addConstr(gp.quicksum(x[j, i] for j in NODES if j != i) == D,
                    name=f"in_deg[{i}]")

    for (i, j) in EDGES:
        m.addConstr(gp.quicksum(f[s, t, i, j] for (s, t) in ACTIVE) <= x[i, j],
                    name=f"cap[{i},{j}]")

    for (s, t) in ACTIVE:
        demand = float(T[s, t])
        for v in NODES:
            out_v = gp.quicksum(f[s, t, v, j] for j in NODES if j != v)
            in_v  = gp.quicksum(f[s, t, j, v] for j in NODES if j != v)
            if   v == s: rhs =  theta * demand
            elif v == t: rhs = -theta * demand
            else:        rhs = 0
            m.addConstr(out_v - in_v == rhs, name=f"fc[{s},{t},{v}]")

    m.optimize()

    if m.Status != GRB.OPTIMAL:
        return None, None, None

    x_vals = {(i, j): int(round(x[i, j].X)) for (i, j) in EDGES}
    f_vals = {(s, t, i, j): f[s, t, i, j].X
              for (s, t) in ACTIVE for (i, j) in EDGES}
    return theta.X, x_vals, f_vals


def x_dict_to_matrix(x_vals):
    X = np.zeros((N, N), dtype=int)
    for (i, j), count in x_vals.items():
        X[i, j] = count
    return X


def format_matrix(M, precision=3):
    return np.array2string(
        np.asarray(M),
        precision=precision,
        suppress_small=True,
        floatmode="fixed",
    )


def print_problem_instance(T):
    print(f"Given traffic-demand matrix T for n = {N}, d = {D}:")
    print(format_matrix(T))


def print_topology(x_vals):
    print("  Topology (node -> {neighbor: link_count}):")
    for i in NODES:
        out = {j: x_vals[(i, j)] for j in NODES if j != i and x_vals[(i, j)] > 0}
        print(f"    {i} -> {out}")


def print_solution(theta_val, x_vals):
    X = x_dict_to_matrix(x_vals)
    print("Best topology X = [x_ij]:")
    print(format_matrix(X, precision=0))
    print_topology(x_vals)
    print(f"Maximum concurrent flow theta* = {theta_val:.6f}")


def collect_edge_usage(f_vals, tol=1e-9):
    edge_usage = defaultdict(list)
    for (s, t, i, j), flow in f_vals.items():
        if flow > tol:
            edge_usage[(i, j)].append(((s, t), flow))
    return edge_usage


def print_routing_answer(theta_val, T, x_vals, f_vals, max_examples=3):
    print("Routing answer:")
    print(f"- Scale the given traffic-demand matrix by theta*: theta*T with theta = {theta_val:.6f}.")
    print("- Route the commodities using flow variables f^(s,t) over the chosen topology X.")

    edge_usage = collect_edge_usage(f_vals)
    shared_edges = []
    for (i, j), uses in edge_usage.items():
        if len(uses) >= 2:
            total = sum(flow for _, flow in uses)
            shared_edges.append((len(uses), total, i, j, uses))
    shared_edges.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))

    if shared_edges:
        print("- Example physical links shared by multiple traffic commodities:")
        for _, total, i, j, uses in shared_edges[:max_examples]:
            capacity = x_vals[(i, j)]
            print(f"  Link {i} -> {j}: x[{i},{j}] = {capacity}, total routed flow = {total:.3f}")
            for (s, t), flow in uses:
                print(f"    f^({s},{t})[{i},{j}] = {flow:.3f}")
            print(f"    Sum of flows on link {i} -> {j} = {total:.3f} <= x[{i},{j}] = {capacity}")
    else:
        print("- No physical link is shared by two positive-flow commodities in this solution.")

    commodity_usage = defaultdict(list)
    for (s, t, i, j), flow in f_vals.items():
        if flow > 1e-9:
            commodity_usage[(s, t)].append(((i, j), flow))

    if commodity_usage:
        commodity, uses = min(
            commodity_usage.items(),
            key=lambda item: (len(item[1]), item[0][0], item[0][1])
        )
        s, t = commodity
        scaled_demand = theta_val * float(T[s, t])
        print("- Example commodity interpretation:")
        print(
            f"  Commodity ({s},{t}) has scaled demand theta*T[{s},{t}] = "
            f"{theta_val:.6f} * {float(T[s, t]):.6f} = {scaled_demand:.3f}"
        )
        for (i, j), flow in uses:
            print(f"  Nonzero routed flow: f^({s},{t})[{i},{j}] = {flow:.3f}")


def validate_hose(T):
    assert np.allclose(np.diag(T), 0)
    assert np.all(T >= -1e-9)
    assert np.all(T.sum(axis=1) <= D + 1e-9), "row sum exceeds d"
    assert np.all(T.sum(axis=0) <= D + 1e-9), "col sum exceeds d"


def concentrated_traffic(src=0, dst=1):
    T = np.zeros((N, N)); T[src, dst] = float(D); return T

def uniform_traffic():
    T = np.full((N, N), D / (N - 1)); np.fill_diagonal(T, 0.0); return T

def skewed_traffic():
    T = np.zeros((N, N))
    T[0, 1] = 2.0; T[0, 2] = 2.0
    T[3, 4] = 2.0; T[3, 5] = 2.0
    T[6, 7] = 4.0
    return T

def random_hose_traffic(seed=42):
    rng = np.random.default_rng(seed)
    raw = rng.random((N, N)); np.fill_diagonal(raw, 0.0)
    for _ in range(500):
        rs = raw.sum(axis=1, keepdims=True); raw = np.where(rs > D, raw * D / rs, raw)
        cs = raw.sum(axis=0, keepdims=True); raw = np.where(cs > D, raw * D / cs, raw)
        np.fill_diagonal(raw, 0.0)
    return raw


def load_matrix(path):
    path = Path(path)
    for delimiter in (",", None):
        try:
            T = np.loadtxt(path, delimiter=delimiter, dtype=float)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"Could not parse matrix file: {path}")

    if T.shape != (N, N):
        raise ValueError(f"Expected an {N}x{N} traffic matrix, got {T.shape}")
    return T


def get_scenarios(args):
    builtins = {
        "concentrated": ("Scenario A - Concentrated (T[0,1] = 4)",
                         concentrated_traffic(0, 1)),
        "uniform": ("Scenario B - Uniform (T[i,j] = 4/7)",
                    uniform_traffic()),
        "skewed": ("Scenario C - Skewed",
                   skewed_traffic()),
        "random": (f"Scenario D - Random hose-model traffic (seed={args.seed})",
                   random_hose_traffic(args.seed)),
    }

    if args.matrix_file:
        T = load_matrix(args.matrix_file)
        return [(f"Custom matrix from {args.matrix_file}", T)]

    if args.scenario == "all":
        return [builtins[key] for key in ("concentrated", "uniform", "skewed", "random")]

    return [builtins[args.scenario]]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Solve the CS536 HW4 joint topology-routing problem."
    )
    parser.add_argument(
        "--scenario",
        choices=["concentrated", "uniform", "skewed", "random", "all"],
        default="all",
        help="Built-in hose-model traffic matrix to solve.",
    )
    parser.add_argument(
        "--matrix-file",
        help="Optional 8x8 traffic matrix file (.csv or whitespace-delimited).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed used when --scenario random is selected.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show Gurobi solver output.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    for name, T in get_scenarios(args):
        print("=" * 72)
        print(name)
        validate_hose(T)
        print_problem_instance(T)

        theta_val, x_vals, f_vals = solve_topology(T, verbose=args.verbose)

        if theta_val is None:
            print("Solver did not return an optimal solution.")
            print()
            continue

        print_solution(theta_val, x_vals)
        print_routing_answer(theta_val, T, x_vals, f_vals)
        print()
