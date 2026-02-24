#!/usr/bin/env python3
"""
CS 536 Assignment 2 - Part 2(b): TCP Stats Visualization

Reads goodput_samples.csv produced by iperf3_client.py and generates:
  - 4 time-series plots (snd_cwnd, RTT, loss proxy, goodput)
  - 3 scatter plots (snd_cwnd vs goodput, RTT vs goodput, loss vs goodput)
All for a single representative destination.

Usage:
    python3 plot_tcp_stats.py --csv results/goodput_samples.csv --outdir results/
    python3 plot_tcp_stats.py --csv results/goodput_samples.csv --server "lg.vie.alwyzon.net:5203"
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


def load_csv(filepath):
    """Load CSV and return list of dicts with numeric conversion."""
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


def pick_representative(rows):
    """Pick the server with the most samples as representative."""
    counts = {}
    for r in rows:
        srv = r['server']
        counts[srv] = counts.get(srv, 0) + 1
    best = max(counts, key=counts.get)
    print(f"Representative server: {best} ({counts[best]} samples)")
    return best


def filter_server(rows, server):
    return [r for r in rows if r['server'] == server]


def setup_style():
    """Common plot style."""
    plt.rcParams.update({
        'figure.facecolor': 'white',
        'axes.facecolor': 'white',
        'axes.grid': True,
        'grid.alpha': 0.3,
        'grid.linestyle': '--',
        'font.size': 11,
        'axes.labelsize': 12,
        'axes.titlesize': 13,
        'figure.dpi': 150,
    })


def plot_timeseries(data, server, outdir):
    """Generate 4 time-series subplots in a single PDF."""
    t = [d['elapsed_s'] for d in data]
    cwnd = [d['snd_cwnd'] for d in data]
    rtt = [d['rtt_ms'] for d in data]
    retrans = [d['total_retrans'] for d in data]
    goodput = [d['goodput_mbps'] for d in data]

    fig, axes = plt.subplots(4, 1, figsize=(10, 12), sharex=True)
    fig.suptitle(f'TCP Stats Time Series — {server}',
                 fontsize=14, fontweight='bold', y=0.98)

    # cwnd
    axes[0].plot(t, cwnd, color='#2563eb', linewidth=1.5)
    axes[0].set_ylabel('snd_cwnd\n(segments)')
    axes[0].fill_between(t, cwnd, alpha=0.1, color='#2563eb')

    # RTT
    axes[1].plot(t, rtt, color='#dc2626', linewidth=1.5)
    axes[1].set_ylabel('RTT (ms)')
    axes[1].fill_between(t, rtt, alpha=0.1, color='#dc2626')

    # Loss proxy (total retransmissions)
    axes[2].plot(t, retrans, color='#ea580c',
                 linewidth=1.5, marker='o', markersize=3)
    axes[2].set_ylabel('Total\nRetransmits')
    axes[2].fill_between(t, retrans, alpha=0.1, color='#ea580c')

    # Goodput
    axes[3].plot(t, goodput, color='#16a34a', linewidth=1.5)
    axes[3].set_ylabel('Goodput\n(Mbps)')
    axes[3].set_xlabel('Time (s)')
    axes[3].fill_between(t, goodput, alpha=0.1, color='#16a34a')

    for ax in axes:
        ax.margins(x=0.02)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    path = os.path.join(outdir, 'q2_timeseries.pdf')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {path}")


def plot_scatter_cwnd_vs_goodput(data, server, outdir):
    """Scatter: snd_cwnd vs goodput."""
    cwnd = [d['snd_cwnd'] for d in data]
    goodput = [d['goodput_mbps'] for d in data]

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(cwnd, goodput, c='#2563eb', alpha=0.7,
               edgecolors='white', linewidth=0.5, s=50)
    ax.set_xlabel('snd_cwnd (segments)')
    ax.set_ylabel('Goodput (Mbps)')
    ax.set_title(f'snd_cwnd vs Goodput — {server}')

    # Trend line
    if len(cwnd) > 2:
        z = np.polyfit(cwnd, goodput, 1)
        p = np.poly1d(z)
        x_line = np.linspace(min(cwnd), max(cwnd), 100)
        ax.plot(x_line, p(x_line), '--', color='#1e40af',
                alpha=0.6, label=f'Linear fit')
        ax.legend(fontsize=9)

    fig.tight_layout()
    path = os.path.join(outdir, 'q2_scatter_cwnd_goodput.pdf')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {path}")


def plot_scatter_rtt_vs_goodput(data, server, outdir):
    """Scatter: RTT vs goodput."""
    rtt = [d['rtt_ms'] for d in data]
    goodput = [d['goodput_mbps'] for d in data]

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(rtt, goodput, c='#dc2626', alpha=0.7,
               edgecolors='white', linewidth=0.5, s=50)
    ax.set_xlabel('RTT (ms)')
    ax.set_ylabel('Goodput (Mbps)')
    ax.set_title(f'RTT vs Goodput — {server}')

    if len(rtt) > 2:
        z = np.polyfit(rtt, goodput, 1)
        p = np.poly1d(z)
        x_line = np.linspace(min(rtt), max(rtt), 100)
        ax.plot(x_line, p(x_line), '--', color='#991b1b',
                alpha=0.6, label='Linear fit')
        ax.legend(fontsize=9)

    fig.tight_layout()
    path = os.path.join(outdir, 'q2_scatter_rtt_goodput.pdf')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {path}")


def plot_scatter_loss_vs_goodput(data, server, outdir):
    """Scatter: loss signal (total retransmissions) vs goodput."""
    retrans = [d['total_retrans'] for d in data]
    goodput = [d['goodput_mbps'] for d in data]

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(retrans, goodput, c='#ea580c', alpha=0.7,
               edgecolors='white', linewidth=0.5, s=50)
    ax.set_xlabel('Total Retransmissions')
    ax.set_ylabel('Goodput (Mbps)')
    ax.set_title(
        f'Loss (Retransmissions) vs Goodput — {server}')

    if len(set(retrans)) > 2:
        z = np.polyfit(retrans, goodput, 1)
        p = np.poly1d(z)
        x_line = np.linspace(min(retrans), max(retrans), 100)
        ax.plot(x_line, p(x_line), '--', color='#9a3412',
                alpha=0.6, label='Linear fit')
        ax.legend(fontsize=9)

    fig.tight_layout()
    path = os.path.join(outdir, 'q2_scatter_loss_goodput.pdf')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {path}")


def main():
    parser = argparse.ArgumentParser(
        description='CS 536 Q2(b): TCP stats visualization')
    parser.add_argument('--csv', type=str, required=True,
                        help='Path to goodput_samples.csv')
    parser.add_argument('--outdir', type=str, default=None,
                        help='Output directory for plots')
    parser.add_argument('--server', type=str, default=None,
                        help='Server label to use as representative '
                             '(default: server with most samples)')
    args = parser.parse_args()

    if args.outdir is None:
        args.outdir = os.path.dirname(args.csv) or '.'
    os.makedirs(args.outdir, exist_ok=True)

    # Load data
    rows = load_csv(args.csv)
    if not rows:
        print("ERROR: CSV is empty"); sys.exit(1)

    # Pick representative server
    if args.server:
        server = args.server
    else:
        server = pick_representative(rows)

    data = filter_server(rows, server)
    if not data:
        print(f"ERROR: No data for server '{server}'")
        print("Available servers:",
              set(r['server'] for r in rows))
        sys.exit(1)

    print(f"\nGenerating Q2(b) plots for: {server}")
    print(f"  Samples: {len(data)}")
    print(f"  Output:  {args.outdir}/\n")

    setup_style()

    # (i) Time-series plots
    plot_timeseries(data, server, args.outdir)

    # (ii) Scatter plots
    plot_scatter_cwnd_vs_goodput(data, server, args.outdir)
    plot_scatter_rtt_vs_goodput(data, server, args.outdir)
    plot_scatter_loss_vs_goodput(data, server, args.outdir)

    print(f"\nDone. All Q2(b) plots saved to {args.outdir}/")


if __name__ == '__main__':
    main()