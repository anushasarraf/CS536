# HW4 Topology Solver

This folder contains the Gurobi-based LP for **CS536 HW4 Part 2: Best Topology for an Arbitrary Traffic Matrix**.

The solver fixes:

- `n = 8` nodes
- `d = 4` incoming links per node
- `d = 4` outgoing links per node
- unit-capacity directed links

Given a traffic matrix `T`, it jointly chooses:

- the topology `X = [x_ij]`, where `x_ij` is the number of directed links from node `i` to node `j`
- the routing variables `f`
- the maximum concurrent flow scaling factor `theta`

## Files

- `topology.py` - Gurobi implementation of the joint topology-routing optimization

## Prerequisites

You need:

- Python 3.10+
- `numpy`
- `gurobipy`
- a valid Gurobi license file (`gurobi.lic`)

## Install

### 1. Create and activate a virtual environment (optional)

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Python dependencies

```bash
pip install numpy gurobipy
```

### 3. Install or retrieve your Gurobi license

You must have a valid Gurobi license before solving the larger scenarios.

If `grbgetkey` is already installed on your machine, run:

```bash
grbgetkey YOUR-LICENSE-KEY
```

If `grbgetkey` is not installed, download the official Gurobi optimizer package, extract it, and run the bundled tool:

```bash
curl -fL -o gurobi13.0.1_linux64.tar.gz https://packages.gurobi.com/13.0/gurobi13.0.1_linux64.tar.gz
tar -xzf gurobi13.0.1_linux64.tar.gz
./gurobi1301/linux64/bin/grbgetkey YOUR-LICENSE-KEY
```

When prompted for the license file location, press Enter to store it in your home directory:

```text
/home/<your-username>
```

This writes:

```text
~/gurobi.lic
```

Gurobi automatically checks your home directory for that file.

## Run

```bash
python3 hw4/topology.py --scenario all
```

This solves:

- concentrated traffic
- uniform traffic
- skewed traffic
- random hose-model traffic

### Run one scenario

```bash
python3 hw4/topology.py --scenario concentrated
python3 hw4/topology.py --scenario uniform
python3 hw4/topology.py --scenario skewed
python3 hw4/topology.py --scenario random
```

To change the random scenario seed:

```bash
python3 hw4/topology.py --scenario random --seed 7
```

### Show detailed Gurobi solver logs

```bash
python3 hw4/topology.py --scenario uniform --verbose
```

### Solve a custom traffic matrix

You can provide your own `8 x 8` matrix file:

```bash
python3 hw4/topology.py --matrix-file ./matrix.csv
```

## Custom Matrix Requirements

Your matrix must satisfy the hose-model constraints:

- `T[i][i] = 0` for all `i`
- `T[i][j] >= 0` for all `i, j`
- each row sum is at most `4`
- each column sum is at most `4`
- shape must be exactly `8 x 8`

Example CSV:

```csv
0,4,0,0,0,0,0,0
0,0,0,0,0,0,0,0
0,0,0,0,0,0,0,0
0,0,0,0,0,0,0,0
0,0,0,0,0,0,0,0
0,0,0,0,0,0,0,0
0,0,0,0,0,0,0,0
0,0,0,0,0,0,0,0
```

## Output Format

For each scenario, the script prints:

1. the problem size `n = 8`, `d = 4`
2. the given traffic matrix `T`
3. the number of active commodities and model variables
4. the optimal concurrent flow `theta*`
5. the optimal topology matrix `X = [x_ij]`
6. the same topology in adjacency-list form

Interpretation:

- `T[i][j]` is the demand from source `i` to destination `j`
- `x_ij` is the number of directed links from `i` to `j`
- each row sum of `X` is `4`
- each column sum of `X` is `4`

## Troubleshooting

### `Model too large for size-limited license`

Gurobi is still using the bundled restricted pip license instead of your academic/commercial license.

Check that:

- `~/gurobi.lic` exists
- the license file belongs to this machine
- you are running from your normal shell, not a restricted environment

### `HostID mismatch`

Your named-user license was generated for a different machine. Request a new academic named-user license for the current computer, or use the correct machine.

### `grbgetkey: command not found`

You have the Python package but not the Gurobi license tools. Use the full Gurobi download shown above, then run:

```bash
./gurobi1301/linux64/bin/grbgetkey YOUR-LICENSE-KEY
```