#!/usr/bin/env python3
import argparse
import re
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


LINE_RE = re.compile(r"\[(?:WS|MOVE) PROFILE\]\s+(.+?):\s+([0-9]*\.?[0-9]+)\s+ms")


def parse_profile_log(log_path: Path):
    timings = defaultdict(list)
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            m = LINE_RE.search(line)
            if not m:
                continue
            label = m.group(1).strip()
            ms = float(m.group(2))
            timings[label].append(ms)
    return timings


def plot_avg_and_max(timings: dict[str, list[float]], title: str, output_path: Path):
    if not timings:
        raise ValueError("No profile timing lines found in log.")

    labels = sorted(timings.keys())
    avgs = [float(np.mean(timings[k])) for k in labels]
    maxs = [float(np.max(timings[k])) for k in labels]

    x = np.arange(len(labels))
    width = 0.4

    fig, ax = plt.subplots(figsize=(max(10, len(labels) * 0.7), 6))
    ax.bar(x - width / 2, avgs, width, label="Average (ms)")
    ax.bar(x + width / 2, maxs, width, label="Max (ms)")

    ax.set_ylabel("Time (ms)")
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    print(f"Saved plot to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Plot avg and max timings from motion profile log.")
    parser.add_argument(
        "log_file",
        nargs="?",
        default="motion_profile.log",
        help="Path to the motion profile log file (default: motion_profile.log)",
    )
    parser.add_argument(
        "--out",
        default="motion_profile_summary.png",
        help="Output image filename (default: motion_profile_summary.png)",
    )
    args = parser.parse_args()

    log_path = Path(args.log_file)
    if not log_path.is_absolute():
        log_path = Path(__file__).parent / log_path
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = Path(__file__).parent / out_path

    timings = parse_profile_log(log_path)
    plot_avg_and_max(timings, f"Motion Profile Timings: {log_path.name}", out_path)


if __name__ == "__main__":
    main()
