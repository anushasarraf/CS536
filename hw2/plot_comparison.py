#!/usr/bin/env python3
"""
Comparison plots across multiple congestion control algorithms.

Loads one CSV per algorithm and generates:
  1. Aggregated time-series overlay (goodput, RTT, cwnd, retransmits)
  2. Summary bar charts (mean goodput, mean RTT, total retransmits)
  3. CDF of per-sample goodput

Usage:
    python3 plot_comparison.py \
        --datasets reno:results/reno_baseline/q2_goodput_samples.csv \
                   cubic:results/cubic_baseline/q2_goodput_samples.csv \
                   "mycc (R1):results/mycc_loss_hold/q2_goodput_samples.csv" \
        --outdir results/comparison/
"""

import argparse
import csv
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np


# ── Colours assigned per algorithm ────────────────────────────────────────────
PALETTE = ['#2563eb', '#dc2626', '#16a34a', '#9333ea', '#ea580c', '#0891b2']


# ── I/O helpers ───────────────────────────────────────────────────────────────

def load_csv(filepath):
    rows = []
    with open(filepath, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed = {}
            for k, v in row.items():
                try:
                    parsed[k] = float(v)
                except (ValueError, TypeError):
                    parsed[k] = v
            rows.append(parsed)
    return rows


def parse_datasets(specs):
    """
    Parse list of "label:path" strings.
    Returns list of (label, rows) tuples.
    """
    datasets = []
    for spec in specs:
        if ':' not in spec:
            sys.exit(f"ERROR: dataset spec must be 'label:path', got: {spec!r}")
        label, path = spec.split(':', 1)
        if not os.path.exists(path):
            sys.exit(f"ERROR: file not found: {path}")
        rows = load_csv(path)
        print(f"  Loaded {len(rows):>5} rows  ← {label}  ({path})")
        datasets.append((label, rows))
    return datasets


# ── Aggregation ───────────────────────────────────────────────────────────────

def bin_timeseries(rows, bin_width=2.0, max_time=None):
    """
    Aggregate all servers' samples into time bins.
    Returns (bin_centres, mean_goodput, mean_rtt, mean_cwnd, mean_retrans,
             std_goodput, std_rtt).
    """
    if max_time is None:
        max_time = max(r['elapsed_s'] for r in rows)

    edges = np.arange(0, max_time + bin_width, bin_width)
    centres = (edges[:-1] + edges[1:]) / 2

    gp, rtt, cwnd, retr = [], [], [], []
    gp_std, rtt_std = [], []

    for lo, hi in zip(edges[:-1], edges[1:]):
        bucket = [r for r in rows if lo <= r['elapsed_s'] < hi]
        if bucket:
            g = [r['goodput_mbps'] for r in bucket]
            r = [r['rtt_ms']       for r in bucket]
            c = [r['snd_cwnd']     for r in bucket]
            t = [r['total_retrans']for r in bucket]
            gp.append(np.mean(g));      gp_std.append(np.std(g))
            rtt.append(np.mean(r));     rtt_std.append(np.std(r))
            cwnd.append(np.mean(c))
            retr.append(np.mean(t))
        else:
            gp.append(np.nan);  gp_std.append(np.nan)
            rtt.append(np.nan); rtt_std.append(np.nan)
            cwnd.append(np.nan)
            retr.append(np.nan)

    return (centres,
            np.array(gp),   np.array(gp_std),
            np.array(rtt),  np.array(rtt_std),
            np.array(cwnd),
            np.array(retr))


def summary_stats(rows):
    gp    = [r['goodput_mbps']  for r in rows]
    rtt   = [r['rtt_ms']        for r in rows]
    retr  = [r['retransmits']   for r in rows]   # per-interval retransmits
    return {
        'mean_goodput':  np.mean(gp),
        'median_goodput':np.median(gp),
        'p95_goodput':   np.percentile(gp, 95),
        'mean_rtt':      np.mean(rtt),
        'median_rtt':    np.median(rtt),
        'total_retrans': sum(retr),
        'goodput_all':   gp,
        'rtt_all':       rtt,
    }


# ── Plot helpers ──────────────────────────────────────────────────────────────

def setup_style():
    plt.rcParams.update({
        'figure.facecolor': 'white',
        'axes.facecolor':   'white',
        'axes.grid':        True,
        'grid.alpha':       0.3,
        'grid.linestyle':   '--',
        'font.size':        11,
        'axes.labelsize':   12,
        'axes.titlesize':   13,
        'figure.dpi':       150,
    })


# ── Figure 1: overlaid time-series ────────────────────────────────────────────

def plot_timeseries_overlay(datasets, outdir, bin_width=2.0):
    setup_style()

    # Find common max time across all datasets
    max_time = max(
        max(r['elapsed_s'] for r in rows)
        for _, rows in datasets
    )

    fig, axes = plt.subplots(4, 1, figsize=(11, 13), sharex=True)
    fig.suptitle('Congestion Control Comparison — Time Series\n'
                 '(mean ± 1 std across all servers)',
                 fontsize=14, fontweight='bold', y=0.99)

    labels_shown = []

    for idx, (label, rows) in enumerate(datasets):
        colour = PALETTE[idx % len(PALETTE)]
        (centres, gp, gp_std,
         rtt, rtt_std,
         cwnd, retr) = bin_timeseries(rows, bin_width, max_time)

        mask = ~np.isnan(gp)

        kw = dict(color=colour, linewidth=2.0, label=label)

        # Goodput
        axes[0].plot(centres[mask], gp[mask], **kw)
        axes[0].fill_between(centres[mask],
                             gp[mask] - gp_std[mask],
                             gp[mask] + gp_std[mask],
                             color=colour, alpha=0.12)

        # RTT
        axes[1].plot(centres[mask], rtt[mask], **kw)
        axes[1].fill_between(centres[mask],
                             rtt[mask] - rtt_std[mask],
                             rtt[mask] + rtt_std[mask],
                             color=colour, alpha=0.12)

        # cwnd
        axes[2].plot(centres[mask], cwnd[mask], **kw)

        # retransmits
        axes[3].plot(centres[mask], retr[mask], **kw)

        labels_shown.append(label)

    axes[0].set_ylabel('Goodput (Mbps)')
    axes[1].set_ylabel('RTT (ms)')
    axes[2].set_ylabel('snd_cwnd\n(segments)')
    axes[3].set_ylabel('Avg Total\nRetransmits')
    axes[3].set_xlabel('Elapsed time (s)')

    # Single shared legend at top
    handles, lbls = axes[0].get_legend_handles_labels()
    fig.legend(handles, lbls, loc='upper right', fontsize=11,
               framealpha=0.9, bbox_to_anchor=(0.98, 0.97))

    for ax in axes:
        ax.margins(x=0.02)

    fig.tight_layout(rect=[0, 0, 1, 0.97])
    path = os.path.join(outdir, 'comparison_timeseries.pdf')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {path}")


# ── Figure 2: summary bar charts ──────────────────────────────────────────────

def plot_summary_bars(datasets, outdir):
    setup_style()

    stats = [(label, summary_stats(rows)) for label, rows in datasets]
    labels   = [s[0] for s in stats]
    colours  = [PALETTE[i % len(PALETTE)] for i in range(len(stats))]

    mean_gp  = [s[1]['mean_goodput']  for s in stats]
    med_gp   = [s[1]['median_goodput']for s in stats]
    p95_gp   = [s[1]['p95_goodput']   for s in stats]
    mean_rtt = [s[1]['mean_rtt']      for s in stats]
    med_rtt  = [s[1]['median_rtt']    for s in stats]
    tot_ret  = [s[1]['total_retrans'] for s in stats]

    x = np.arange(len(labels))
    width = 0.28

    fig, axes = plt.subplots(1, 3, figsize=(14, 6))
    fig.suptitle('Congestion Control Summary Statistics',
                 fontsize=14, fontweight='bold')

    # ── Goodput ──
    ax = axes[0]
    bars_mean = ax.bar(x - width, mean_gp, width, label='Mean',
                       color=colours, alpha=0.85, edgecolor='white')
    bars_med  = ax.bar(x,          med_gp,  width, label='Median',
                       color=colours, alpha=0.55, edgecolor='white')
    bars_p95  = ax.bar(x + width,  p95_gp,  width, label='P95',
                       color=colours, alpha=0.35, edgecolor='white')
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9, rotation=30, ha='right')
    ax.set_ylabel('Goodput (Mbps)')
    ax.set_title('Goodput')
    # value labels
    for bar in list(bars_mean) + list(bars_med) + list(bars_p95):
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 0.3,
                f'{h:.1f}', ha='center', va='bottom', fontsize=8)
    ax.legend(fontsize=9)

    # ── RTT ──
    ax = axes[1]
    bars_mr = ax.bar(x - width/2, mean_rtt, width, label='Mean',
                     color=colours, alpha=0.85, edgecolor='white')
    bars_mdr= ax.bar(x + width/2, med_rtt,  width, label='Median',
                     color=colours, alpha=0.55, edgecolor='white')
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9, rotation=30, ha='right')
    ax.set_ylabel('RTT (ms)')
    ax.set_title('Round-Trip Time')
    for bar in list(bars_mr) + list(bars_mdr):
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 0.5,
                f'{h:.1f}', ha='center', va='bottom', fontsize=8)
    ax.legend(fontsize=9)

    # ── Retransmits ──
    ax = axes[2]
    bars_r = ax.bar(x, tot_ret, 0.45, color=colours,
                    alpha=0.85, edgecolor='white')
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9, rotation=30, ha='right')
    ax.set_ylabel('Total Retransmits (sum)')
    ax.set_title('Packet Loss Proxy')
    for bar in bars_r:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 0.2,
                f'{int(h)}', ha='center', va='bottom', fontsize=9)

    fig.tight_layout()
    path = os.path.join(outdir, 'comparison_summary_bars.pdf')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {path}")


# ── Figure 3: CDF of goodput ──────────────────────────────────────────────────

def plot_goodput_cdf(datasets, outdir):
    setup_style()

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_title('CDF of Per-Sample Goodput', fontweight='bold')

    for idx, (label, rows) in enumerate(datasets):
        colour = PALETTE[idx % len(PALETTE)]
        gp = sorted(r['goodput_mbps'] for r in rows)
        cdf = np.arange(1, len(gp) + 1) / len(gp)
        ax.plot(gp, cdf, color=colour, linewidth=2.0, label=label)

        # mark median and p95
        med = np.percentile(gp, 50)
        p95 = np.percentile(gp, 95)
        ax.axvline(med, color=colour, linestyle=':', linewidth=1.2, alpha=0.7)
        ax.axvline(p95, color=colour, linestyle='--', linewidth=1.2, alpha=0.7)

    # dummy legend entries for line styles
    from matplotlib.lines import Line2D
    extra = [
        Line2D([0], [0], color='grey', linestyle=':', linewidth=1.2,
               label='median (per algo)'),
        Line2D([0], [0], color='grey', linestyle='--', linewidth=1.2,
               label='P95 (per algo)'),
    ]
    handles, lbls = ax.get_legend_handles_labels()
    ax.legend(handles + extra, lbls + [e.get_label() for e in extra],
              fontsize=10, loc='lower right')

    ax.set_xlabel('Goodput (Mbps)')
    ax.set_ylabel('CDF')
    ax.set_ylim(0, 1.02)
    ax.margins(x=0.02)

    fig.tight_layout()
    path = os.path.join(outdir, 'comparison_goodput_cdf.pdf')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {path}")


# ── Figure 4: RTT CDF ─────────────────────────────────────────────────────────

def plot_rtt_cdf(datasets, outdir):
    setup_style()

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_title('CDF of Per-Sample RTT', fontweight='bold')

    for idx, (label, rows) in enumerate(datasets):
        colour = PALETTE[idx % len(PALETTE)]
        rtt = sorted(r['rtt_ms'] for r in rows)
        cdf = np.arange(1, len(rtt) + 1) / len(rtt)
        ax.plot(rtt, cdf, color=colour, linewidth=2.0, label=label)

    ax.set_xlabel('RTT (ms)')
    ax.set_ylabel('CDF')
    ax.set_ylim(0, 1.02)
    ax.margins(x=0.02)
    ax.legend(fontsize=10)

    fig.tight_layout()
    path = os.path.join(outdir, 'comparison_rtt_cdf.pdf')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {path}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Compare multiple CC algorithms from CSV data')
    parser.add_argument('--datasets', nargs='+', required=True,
                        metavar='LABEL:PATH',
                        help='One or more "label:path" pairs')
    parser.add_argument('--outdir', default='results/comparison',
                        help='Output directory for plots (default: results/comparison)')
    parser.add_argument('--bin', type=float, default=2.0,
                        help='Time-bin width in seconds for time-series (default: 2.0)')
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    print(f"\nLoading datasets:")
    datasets = parse_datasets(args.datasets)

    print(f"\nGenerating comparison plots → {args.outdir}/")
    plot_timeseries_overlay(datasets, args.outdir, bin_width=args.bin)
    plot_summary_bars(datasets, args.outdir)
    plot_goodput_cdf(datasets, args.outdir)
    plot_rtt_cdf(datasets, args.outdir)

    print(f"\nDone. 4 plots saved to {args.outdir}/")

    # Print a quick summary table
    print("\n── Summary ─────────────────────────────────────────────────────")
    print(f"{'Algorithm':<20} {'Mean Gp (Mbps)':>14} {'Med Gp':>8} "
          f"{'P95 Gp':>8} {'Mean RTT':>10} {'Retrans':>9}")
    print("─" * 73)
    for label, rows in datasets:
        s = summary_stats(rows)
        print(f"{label:<20} {s['mean_goodput']:>14.2f} {s['median_goodput']:>8.2f} "
              f"{s['p95_goodput']:>8.2f} {s['mean_rtt']:>10.2f} "
              f"{int(s['total_retrans']):>9}")
    print("─" * 73)


if __name__ == '__main__':
    main()
