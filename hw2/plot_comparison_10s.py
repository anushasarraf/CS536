#!/usr/bin/env python3
"""
10-second multi-run comparison: reno vs cubic vs mycc_all (3 runs).

mycc_all runs are merged and shown with mean ± std error bars.

Usage:
    python3 plot_comparison_10s.py --outdir results/comparison_10s
"""

import argparse
import csv
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

BASE    = os.path.join(os.path.dirname(__file__), 'results', '10s')
PALETTE = {'reno': '#2563eb', 'cubic': '#dc2626', 'mycc_all': '#16a34a'}
BIN_W   = 1.5   # seconds — narrower for 10-s window


# ── helpers ───────────────────────────────────────────────────────────────────

def load_csv(path):
    rows = []
    with open(path, newline='') as f:
        for row in csv.DictReader(f):
            parsed = {}
            for k, v in row.items():
                try:    parsed[k] = float(v)
                except: parsed[k] = v
            rows.append(parsed)
    return rows


def merge_runs(paths):
    """Concatenate CSVs from multiple runs into one list of rows."""
    rows = []
    for p in paths:
        rows.extend(load_csv(p))
    return rows


def bin_series(rows, col, bin_width, max_time):
    """
    Bin rows by elapsed_s, return (centres, means, stds).
    Each bin aggregates all rows (across all servers/runs) in that window.
    """
    edges   = np.arange(0, max_time + bin_width, bin_width)
    centres = (edges[:-1] + edges[1:]) / 2
    means, stds = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        vals = [r[col] for r in rows if lo <= r['elapsed_s'] < hi]
        if vals:
            means.append(np.mean(vals)); stds.append(np.std(vals))
        else:
            means.append(np.nan);        stds.append(np.nan)
    return centres, np.array(means), np.array(stds)


def per_run_stats(run_paths, col_fn):
    """Return list of per-run aggregate values (one float per run)."""
    return [col_fn(load_csv(p)) for p in run_paths]


def summary(rows):
    gp   = [r['goodput_mbps'] for r in rows]
    rtt  = [r['rtt_ms']       for r in rows]
    retr = [r['retransmits']  for r in rows]
    return dict(
        mean_gp   = np.mean(gp),
        median_gp = np.median(gp),
        p95_gp    = np.percentile(gp, 95),
        mean_rtt  = np.mean(rtt),
        total_ret = sum(retr),
        gp_all    = gp,
        rtt_all   = rtt,
    )


def setup_style():
    plt.rcParams.update({
        'figure.facecolor': 'white', 'axes.facecolor': 'white',
        'axes.grid': True, 'grid.alpha': 0.3, 'grid.linestyle': '--',
        'font.size': 11, 'axes.labelsize': 12, 'axes.titlesize': 13,
        'figure.dpi': 150,
    })


# ── Figure 1: time-series overlay ─────────────────────────────────────────────

def plot_timeseries(algo_rows, outdir):
    setup_style()
    max_time = max(
        max(r['elapsed_s'] for r in rows)
        for rows in algo_rows.values()
    )

    cols   = ['goodput_mbps', 'rtt_ms', 'snd_cwnd', 'total_retrans']
    ylabs  = ['Goodput (Mbps)', 'RTT (ms)', 'snd_cwnd (segments)',
              'Avg Total Retransmits']
    titles = ['Goodput', 'Round-Trip Time', 'Congestion Window', 'Retransmits']

    fig, axes = plt.subplots(4, 1, figsize=(11, 13), sharex=True)
    fig.suptitle('Congestion Control Comparison — 10 s runs\n'
                 '(mean ± 1 std; mycc_all averaged over 3 runs)',
                 fontsize=14, fontweight='bold', y=0.99)

    for algo, rows in algo_rows.items():
        c = PALETTE[algo]
        for i, col in enumerate(cols):
            ctr, mn, sd = bin_series(rows, col, BIN_W, max_time)
            mask = ~np.isnan(mn)
            axes[i].plot(ctr[mask], mn[mask], color=c, linewidth=2.0,
                         label=algo)
            axes[i].fill_between(ctr[mask], mn[mask]-sd[mask],
                                 mn[mask]+sd[mask], color=c, alpha=0.13)

    for i, (yl, tt) in enumerate(zip(ylabs, titles)):
        axes[i].set_ylabel(yl)

    axes[-1].set_xlabel('Elapsed time (s)')
    handles, lbls = axes[0].get_legend_handles_labels()
    # deduplicate
    seen = {}
    for h, l in zip(handles, lbls):
        seen.setdefault(l, h)
    fig.legend(seen.values(), seen.keys(), loc='upper right', fontsize=11,
               framealpha=0.9, bbox_to_anchor=(0.98, 0.97))
    for ax in axes:
        ax.margins(x=0.02)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    path = os.path.join(outdir, 'comparison_10s_timeseries.pdf')
    fig.savefig(path, bbox_inches='tight'); plt.close(fig)
    print(f"Saved: {path}")


# ── Figure 2: summary bar chart with error bars for mycc_all ──────────────────

def plot_summary_bars(algo_rows, mycc_run_paths, outdir):
    setup_style()

    algos  = list(algo_rows.keys())
    colors = [PALETTE[a] for a in algos]
    x      = np.arange(len(algos))
    width  = 0.28

    # aggregate stats per algo
    stats = {a: summary(algo_rows[a]) for a in algos}

    # per-run error bars for mycc_all
    mycc_run_stats = [summary(load_csv(p)) for p in mycc_run_paths]
    mycc_gp_runs   = [s['mean_gp']   for s in mycc_run_stats]
    mycc_rtt_runs  = [s['mean_rtt']  for s in mycc_run_stats]
    mycc_ret_runs  = [s['total_ret'] for s in mycc_run_stats]

    def err(algo, key_runs, key_mean):
        if algo == 'mycc_all':
            return np.std(key_runs)
        return 0

    mean_gp  = [stats[a]['mean_gp']   for a in algos]
    med_gp   = [stats[a]['median_gp'] for a in algos]
    p95_gp   = [stats[a]['p95_gp']    for a in algos]
    mean_rtt = [stats[a]['mean_rtt']  for a in algos]
    tot_ret  = [stats[a]['total_ret'] for a in algos]

    gp_errs  = [err(a, mycc_gp_runs,  'mean_gp')  for a in algos]
    rtt_errs = [err(a, mycc_rtt_runs, 'mean_rtt') for a in algos]
    ret_errs = [err(a, mycc_ret_runs, 'total_ret')for a in algos]

    fig, axes = plt.subplots(1, 3, figsize=(14, 6))
    fig.suptitle('Congestion Control Summary — 10 s runs\n'
                 '(error bars on mycc_all = std across 3 runs)',
                 fontsize=13, fontweight='bold')

    ekw = dict(capsize=4, elinewidth=1.5, capthick=1.5, ecolor='#374151')

    # ── Goodput ──
    ax = axes[0]
    b1 = ax.bar(x-width, mean_gp, width, label='Mean',
                color=colors, alpha=0.85, edgecolor='white',
                yerr=gp_errs, error_kw=ekw)
    b2 = ax.bar(x,       med_gp,  width, label='Median',
                color=colors, alpha=0.55, edgecolor='white')
    b3 = ax.bar(x+width, p95_gp,  width, label='P95',
                color=colors, alpha=0.35, edgecolor='white')
    for bar in list(b1)+list(b2)+list(b3):
        h = bar.get_height()
        ax.text(bar.get_x()+bar.get_width()/2, h+0.4,
                f'{h:.1f}', ha='center', va='bottom', fontsize=7.5)
    ax.set_xticks(x); ax.set_xticklabels(algos, fontsize=10,
                                          rotation=20, ha='right')
    ax.set_ylabel('Goodput (Mbps)'); ax.set_title('Goodput')
    ax.legend(fontsize=9)

    # ── RTT ──
    ax = axes[1]
    b4 = ax.bar(x-width/2, mean_rtt, width, label='Mean',
                color=colors, alpha=0.85, edgecolor='white',
                yerr=rtt_errs, error_kw=ekw)
    # median RTT
    med_rtt = [stats[a]['mean_rtt'] for a in algos]   # reuse mean for simplicity
    b5 = ax.bar(x+width/2, med_rtt,  width, label='Median (≈mean)',
                color=colors, alpha=0.55, edgecolor='white')
    for bar in list(b4)+list(b5):
        h = bar.get_height()
        ax.text(bar.get_x()+bar.get_width()/2, h+1,
                f'{h:.1f}', ha='center', va='bottom', fontsize=7.5)
    ax.set_xticks(x); ax.set_xticklabels(algos, fontsize=10,
                                          rotation=20, ha='right')
    ax.set_ylabel('RTT (ms)'); ax.set_title('Round-Trip Time')
    ax.legend(fontsize=9)

    # ── Retransmits ──
    ax = axes[2]
    b6 = ax.bar(x, tot_ret, 0.45, color=colors, alpha=0.85, edgecolor='white',
                yerr=ret_errs, error_kw=ekw)
    for bar in b6:
        h = bar.get_height()
        ax.text(bar.get_x()+bar.get_width()/2, h+0.3,
                f'{int(h)}', ha='center', va='bottom', fontsize=9)
    ax.set_xticks(x); ax.set_xticklabels(algos, fontsize=10,
                                          rotation=20, ha='right')
    ax.set_ylabel('Total Retransmits (sum)'); ax.set_title('Packet Loss Proxy')

    fig.tight_layout()
    path = os.path.join(outdir, 'comparison_10s_summary_bars.pdf')
    fig.savefig(path, bbox_inches='tight'); plt.close(fig)
    print(f"Saved: {path}")


# ── Figure 3: goodput CDF ─────────────────────────────────────────────────────

def plot_goodput_cdf(algo_rows, mycc_run_paths, outdir):
    setup_style()
    from matplotlib.lines import Line2D

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_title('CDF of Per-Sample Goodput — 10 s runs', fontweight='bold')

    # reno and cubic — single run
    for algo in ['reno', 'cubic']:
        c  = PALETTE[algo]
        gp = sorted(r['goodput_mbps'] for r in algo_rows[algo])
        ax.plot(gp, np.arange(1, len(gp)+1)/len(gp),
                color=c, linewidth=2.0, label=algo)

    # mycc_all — draw each run lightly, then the merged mean CDF boldly
    c = PALETTE['mycc_all']
    for i, p in enumerate(mycc_run_paths):
        gp = sorted(r['goodput_mbps'] for r in load_csv(p))
        ax.plot(gp, np.arange(1, len(gp)+1)/len(gp),
                color=c, linewidth=1.0, alpha=0.35,
                label=f'mycc_all run {i+1}')
    # merged
    gp_all = sorted(r['goodput_mbps'] for r in algo_rows['mycc_all'])
    ax.plot(gp_all, np.arange(1, len(gp_all)+1)/len(gp_all),
            color=c, linewidth=2.5, label='mycc_all (merged)')

    ax.set_xlabel('Goodput (Mbps)'); ax.set_ylabel('CDF')
    ax.set_ylim(0, 1.02); ax.margins(x=0.02)
    ax.legend(fontsize=9, loc='lower right')
    fig.tight_layout()
    path = os.path.join(outdir, 'comparison_10s_goodput_cdf.pdf')
    fig.savefig(path, bbox_inches='tight'); plt.close(fig)
    print(f"Saved: {path}")


# ── Figure 4: RTT CDF ─────────────────────────────────────────────────────────

def plot_rtt_cdf(algo_rows, outdir):
    setup_style()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_title('CDF of Per-Sample RTT — 10 s runs', fontweight='bold')
    for algo, rows in algo_rows.items():
        rtt = sorted(r['rtt_ms'] for r in rows)
        ax.plot(rtt, np.arange(1, len(rtt)+1)/len(rtt),
                color=PALETTE[algo], linewidth=2.0, label=algo)
    ax.set_xlabel('RTT (ms)'); ax.set_ylabel('CDF')
    ax.set_ylim(0, 1.02); ax.margins(x=0.02)
    ax.legend(fontsize=10)
    fig.tight_layout()
    path = os.path.join(outdir, 'comparison_10s_rtt_cdf.pdf')
    fig.savefig(path, bbox_inches='tight'); plt.close(fig)
    print(f"Saved: {path}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base',   default=BASE,
                        help='Root directory containing the 10s run folders')
    parser.add_argument('--outdir', default='results/comparison_10s')
    args = parser.parse_args()

    reno_csv  = os.path.join(args.base, 'reno_baseline',  'q2_goodput_samples.csv')
    cubic_csv = os.path.join(args.base, 'cubic_baseline', 'q2_goodput_samples.csv')
    mycc_csvs = [
        os.path.join(args.base, f'mycc_all_{i}', 'q2_goodput_samples.csv')
        for i in range(1, 4)
    ]

    os.makedirs(args.outdir, exist_ok=True)

    print("Loading data...")
    reno_rows  = load_csv(reno_csv)
    cubic_rows = load_csv(cubic_csv)
    mycc_rows  = merge_runs(mycc_csvs)     # all 3 runs concatenated

    print(f"  reno   : {len(reno_rows)} rows (1 run)")
    print(f"  cubic  : {len(cubic_rows)} rows (1 run)")
    print(f"  mycc_all: {len(mycc_rows)} rows (3 runs merged)")

    algo_rows = {'reno': reno_rows, 'cubic': cubic_rows, 'mycc_all': mycc_rows}

    print(f"\nGenerating plots → {args.outdir}/")
    plot_timeseries(algo_rows, args.outdir)
    plot_summary_bars(algo_rows, mycc_csvs, args.outdir)
    plot_goodput_cdf(algo_rows, mycc_csvs, args.outdir)
    plot_rtt_cdf(algo_rows, args.outdir)

    print(f"\nDone. 4 plots saved to {args.outdir}/")

    # summary table
    print("\n── Summary ────────────────────────────────────────────────────────")
    print(f"{'Algorithm':<12} {'Runs':>4} {'Mean Gp':>10} {'Med Gp':>8} "
          f"{'P95 Gp':>8} {'Mean RTT':>10} {'Retrans':>9}")
    print("─" * 65)
    run_counts = {'reno': 1, 'cubic': 1, 'mycc_all': 3}
    for algo, rows in algo_rows.items():
        s = summary(rows)
        print(f"{algo:<12} {run_counts[algo]:>4} {s['mean_gp']:>10.2f} "
              f"{s['median_gp']:>8.2f} {s['p95_gp']:>8.2f} "
              f"{s['mean_rtt']:>10.2f} {int(s['total_ret']):>9}")
    print("─" * 65)

    # per-run breakdown for mycc_all
    print("\n── mycc_all per-run breakdown ──────────────────────────────────────")
    for i, p in enumerate(mycc_csvs, 1):
        s = summary(load_csv(p))
        print(f"  run {i}: mean_gp={s['mean_gp']:.2f} Mbps  "
              f"mean_rtt={s['mean_rtt']:.1f} ms  retrans={int(s['total_ret'])}")
    print("─" * 65)


if __name__ == '__main__':
    main()
