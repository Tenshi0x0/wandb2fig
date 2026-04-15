#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd
import wandb


@dataclass(frozen=True)
class SeriesSpec:
    label: str
    pattern: re.Pattern[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pull curves from Weights & Biases, aggregate across seeds/runs, and make paper-style plots."
    )
    parser.add_argument("--entity", required=True, help="W&B entity, e.g. OpenMLRL")
    parser.add_argument("--project", required=True, help="W&B project, e.g. multi-source-gathering-tianle")
    parser.add_argument(
        "--series",
        action="append",
        required=True,
        help='Series spec in the form "label::regex", matched against run.name. Repeat for multiple methods.',
    )
    parser.add_argument("--metric", required=True, help='Metric key, e.g. "eval/answer_score"')
    parser.add_argument("--step-key", default="_step", help='Step key, default "_step"')
    parser.add_argument(
        "--error-band",
        choices=("std", "ci95"),
        default="ci95",
        help="Uncertainty band to draw around the mean.",
    )
    parser.add_argument(
        "--seed-key",
        default="seed",
        help='Config key used to recover the seed. Falls back to run id if unavailable. Default: "seed"',
    )
    parser.add_argument(
        "--seed-fallback",
        choices=("run_id", "index", "none"),
        default="run_id",
        help="How to identify repeated runs when no seed is logged.",
    )
    parser.add_argument(
        "--states",
        default="*",
        help='Comma-separated run states to keep. Use "*" to keep all. Default: "*"',
    )
    parser.add_argument("--max-runs", type=int, default=500, help="Maximum runs to scan from the project.")
    parser.add_argument("--title", default=None, help="Optional plot title.")
    parser.add_argument("--xlabel", default="Training Step", help="X-axis label.")
    parser.add_argument("--ylabel", default=None, help="Y-axis label. Defaults to metric name.")
    parser.add_argument("--legend-loc", default="best", help="Matplotlib legend location.")
    parser.add_argument(
        "--figsize",
        default="3.6,2.6",
        help='Figure size in inches as "width,height". Good single-column default: 3.6,2.6',
    )
    parser.add_argument("--dpi", type=int, default=300, help="PNG DPI. PDF is always vector.")
    parser.add_argument(
        "--formats",
        default="pdf,png",
        help='Comma-separated output formats. Common: "pdf,png"',
    )
    parser.add_argument(
        "--style",
        choices=("science", "fallback"),
        default="science",
        help="Plot style preset. 'science' tries SciencePlots first and falls back automatically.",
    )
    parser.add_argument(
        "--out-prefix",
        required=True,
        help="Output path prefix, e.g. figures/msg_108_eval_answer_score",
    )
    return parser.parse_args()


def parse_series_specs(values: Sequence[str]) -> List[SeriesSpec]:
    specs: List[SeriesSpec] = []
    for value in values:
        if "::" not in value:
            raise ValueError(f'Invalid --series value "{value}". Expected "label::regex".')
        label, regex = value.split("::", 1)
        label = label.strip()
        regex = regex.strip()
        if not label or not regex:
            raise ValueError(f'Invalid --series value "{value}". Label and regex must both be non-empty.')
        specs.append(SeriesSpec(label=label, pattern=re.compile(regex)))
    return specs


def parse_figsize(value: str) -> Tuple[float, float]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2:
        raise ValueError(f'Invalid --figsize "{value}". Expected "width,height".')
    return float(parts[0]), float(parts[1])


def parse_csv_list(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def setup_plot_style(style: str) -> None:
    used_scienceplots = False
    if style == "science":
        try:
            import scienceplots  # noqa: F401

            plt.style.use(["science", "no-latex"])
            used_scienceplots = True
        except ImportError:
            warnings.warn(
                "SciencePlots is not installed; falling back to a clean matplotlib style. "
                "Install with `pip install SciencePlots` for the intended paper look.",
                stacklevel=2,
            )

    if not used_scienceplots:
        plt.style.use("default")

    mpl.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.grid": True,
            "grid.alpha": 0.25,
            "grid.linestyle": "--",
            "grid.linewidth": 0.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "axes.titlesize": 11,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.frameon": True,
            "legend.fancybox": False,
            "legend.framealpha": 0.95,
            "legend.edgecolor": "#cccccc",
            "lines.linewidth": 2.0,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.03,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def parse_jsonish_mapping(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def unwrap_wandb_value(value: Any) -> Any:
    if isinstance(value, dict) and set(value.keys()) == {"value"}:
        return value["value"]
    return value


def find_config_value(config: Dict[str, Any], target_key: str) -> Any:
    target = target_key.lower()
    queue: List[Any] = [config]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for key, value in current.items():
                if str(key).lower() == target:
                    return unwrap_wandb_value(value)
                queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)
    return None


def choose_series(run_name: str, specs: Sequence[SeriesSpec]) -> Optional[str]:
    matches = [spec.label for spec in specs if spec.pattern.search(run_name)]
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(f'Run "{run_name}" matches multiple series: {matches}')
    return matches[0]


def recover_seed(
    config: Dict[str, Any],
    run_id: str,
    fallback_mode: str,
    fallback_index: int,
    seed_key: str,
) -> Tuple[Optional[str], str]:
    seed_value = find_config_value(config, seed_key)
    if seed_value is not None:
        return str(seed_value), "config"

    for alt_key in ("random_seed", "rng_seed"):
        alt_value = find_config_value(config, alt_key)
        if alt_value is not None:
            return str(alt_value), f"config:{alt_key}"

    if fallback_mode == "run_id":
        return run_id, "fallback:run_id"
    if fallback_mode == "index":
        return f"replicate_{fallback_index}", "fallback:index"
    return None, "missing"


def fetch_history_rows(run: wandb.apis.public.Run, step_key: str, metric: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in run.scan_history(keys=[step_key, metric]):
        if step_key not in row or metric not in row:
            continue
        step_value = row.get(step_key)
        metric_value = row.get(metric)
        if step_value is None or metric_value is None:
            continue
        rows.append({step_key: step_value, metric: metric_value})
    return rows


def build_dataframes(
    api: wandb.Api,
    entity: str,
    project: str,
    series_specs: Sequence[SeriesSpec],
    metric: str,
    step_key: str,
    states: Sequence[str],
    max_runs: int,
    seed_key: str,
    seed_fallback: str,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    project_path = f"{entity}/{project}"
    series_order = [spec.label for spec in series_specs]
    normalized_states = {state.strip().lower() for state in states if state.strip() and state.strip() != "*"}
    runs = list(api.runs(project_path, per_page=max_runs))
    selected_runs: List[Dict[str, Any]] = []
    raw_rows: List[Dict[str, Any]] = []
    fallback_counts: Dict[str, int] = {}

    for run in runs:
        run_name = getattr(run, "name", "") or ""
        run_state = str(getattr(run, "state", "") or "").strip().lower()
        if normalized_states and run_state not in normalized_states:
            continue
        series_label = choose_series(run_name, series_specs)
        if series_label is None:
            continue

        config = parse_jsonish_mapping(getattr(run, "config", None))
        fallback_counts[series_label] = fallback_counts.get(series_label, 0) + 1
        seed, seed_source = recover_seed(
            config=config,
            run_id=str(run.id),
            fallback_mode=seed_fallback,
            fallback_index=fallback_counts[series_label],
            seed_key=seed_key,
        )

        selected_runs.append(
            {
                "series": series_label,
                "run_id": str(run.id),
                "run_name": run_name,
                "state": run_state,
                "created_at": getattr(run, "created_at", None),
                "seed": seed,
                "seed_source": seed_source,
                "url": getattr(run, "url", None),
            }
        )

        history_rows = fetch_history_rows(run, step_key=step_key, metric=metric)
        for row in history_rows:
            raw_rows.append(
                {
                    "series": series_label,
                    "run_id": str(run.id),
                    "run_name": run_name,
                    "seed": seed,
                    "seed_source": seed_source,
                    step_key: row[step_key],
                    metric: row[metric],
                }
            )

    runs_df = pd.DataFrame(selected_runs)
    raw_df = pd.DataFrame(raw_rows)

    if runs_df.empty:
        raise RuntimeError("No runs matched the requested --series filters.")
    if raw_df.empty:
        raise RuntimeError(f'Runs matched, but no history rows were found for metric "{metric}".')

    runs_df["series"] = pd.Categorical(runs_df["series"], categories=series_order, ordered=True)
    raw_df["series"] = pd.Categorical(raw_df["series"], categories=series_order, ordered=True)
    raw_df[step_key] = pd.to_numeric(raw_df[step_key], errors="coerce")
    raw_df[metric] = pd.to_numeric(raw_df[metric], errors="coerce")
    raw_df = raw_df.dropna(subset=[step_key, metric]).sort_values(["series", "run_id", step_key])
    raw_df = raw_df.drop_duplicates(subset=["series", "run_id", step_key], keep="last")
    raw_df[step_key] = raw_df[step_key].astype(int)

    return runs_df, raw_df


def aggregate_curves(raw_df: pd.DataFrame, metric: str, step_key: str, error_band: str) -> pd.DataFrame:
    grouped = (
        raw_df.groupby(["series", step_key], as_index=False, observed=True)
        .agg(
            mean=(metric, "mean"),
            std=(metric, "std"),
            n=(metric, "count"),
        )
        .sort_values(["series", step_key])
    )

    grouped["std"] = grouped["std"].fillna(0.0)
    if error_band == "std":
        grouped["band"] = grouped["std"]
    else:
        grouped["band"] = grouped.apply(
            lambda row: 0.0 if row["n"] <= 1 else 1.96 * row["std"] / math.sqrt(row["n"]),
            axis=1,
        )
    grouped["lower"] = grouped["mean"] - grouped["band"]
    grouped["upper"] = grouped["mean"] + grouped["band"]
    return grouped


def summarize_final_points(raw_df: pd.DataFrame, metric: str, step_key: str) -> pd.DataFrame:
    final_points = (
        raw_df.sort_values(["series", "run_id", step_key])
        .groupby(["series", "run_id"], as_index=False, observed=True)
        .tail(1)
        .sort_values(["series", "run_id"])
    )

    summary = (
        final_points.groupby("series", as_index=False, observed=True)
        .agg(
            final_step_min=(step_key, "min"),
            final_step_max=(step_key, "max"),
            mean=(metric, "mean"),
            std=(metric, "std"),
            n=(metric, "count"),
        )
        .sort_values("series")
    )
    summary["std"] = summary["std"].fillna(0.0)
    summary["ci95"] = summary.apply(
        lambda row: 0.0 if row["n"] <= 1 else 1.96 * row["std"] / math.sqrt(row["n"]),
        axis=1,
    )
    return summary


def plot_curves(
    agg_df: pd.DataFrame,
    runs_df: pd.DataFrame,
    metric: str,
    step_key: str,
    title: Optional[str],
    xlabel: str,
    ylabel: Optional[str],
    legend_loc: str,
    figsize: Tuple[float, float],
) -> plt.Figure:
    fig, ax = plt.subplots(figsize=figsize)
    color_cycle = plt.get_cmap("tab10").colors
    n_runs_map = runs_df.groupby("series", observed=True)["run_id"].nunique().to_dict()

    for idx, (series, group_df) in enumerate(agg_df.groupby("series", sort=False, observed=True)):
        color = color_cycle[idx % len(color_cycle)]
        group_df = group_df.sort_values(step_key)
        x = group_df[step_key].to_numpy()
        y = group_df["mean"].to_numpy()
        lower = group_df["lower"].to_numpy()
        upper = group_df["upper"].to_numpy()

        markevery = max(1, len(group_df) // 8) if len(group_df) > 0 else 1
        ax.plot(x, y, label=f"{series} (n={n_runs_map.get(series, 0)})", color=color, marker="o", ms=3, markevery=markevery)
        ax.fill_between(x, lower, upper, color=color, alpha=0.18, linewidth=0)

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel or metric)
    if title:
        ax.set_title(title)
    ax.legend(loc=legend_loc)
    ax.margins(x=0.02)
    return fig


def save_outputs(
    fig: plt.Figure,
    out_prefix: Path,
    formats: Sequence[str],
    dpi: int,
    step_key: str,
    runs_df: pd.DataFrame,
    raw_df: pd.DataFrame,
    agg_df: pd.DataFrame,
    final_df: pd.DataFrame,
) -> None:
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    for fmt in formats:
        fig.savefig(out_prefix.with_suffix(f".{fmt}"), dpi=dpi)

    runs_df.sort_values(["series", "created_at", "run_id"]).to_csv(out_prefix.with_suffix(".runs.csv"), index=False)
    raw_df.sort_values(["series", "run_id", step_key]).to_csv(out_prefix.with_suffix(".raw.csv"), index=False)
    agg_df.to_csv(out_prefix.with_suffix(".agg.csv"), index=False)
    final_df.to_csv(out_prefix.with_suffix(".final.csv"), index=False)


def print_final_summary(final_df: pd.DataFrame) -> None:
    print("\nFinal-point summary")
    for row in final_df.itertuples(index=False):
        print(
            f"- {row.series}: mean={row.mean:.4f}, std={row.std:.4f}, ci95={row.ci95:.4f}, "
            f"n={int(row.n)}, final_step_range=[{int(row.final_step_min)}, {int(row.final_step_max)}]"
        )


def main() -> int:
    args = parse_args()
    series_specs = parse_series_specs(args.series)
    figsize = parse_figsize(args.figsize)
    formats = parse_csv_list(args.formats)
    states = parse_csv_list(args.states)

    setup_plot_style(args.style)

    api = wandb.Api(timeout=60)
    runs_df, raw_df = build_dataframes(
        api=api,
        entity=args.entity,
        project=args.project,
        series_specs=series_specs,
        metric=args.metric,
        step_key=args.step_key,
        states=states,
        max_runs=args.max_runs,
        seed_key=args.seed_key,
        seed_fallback=args.seed_fallback,
    )

    if (runs_df["seed_source"] != "config").any():
        missing = runs_df[runs_df["seed_source"] != "config"][["series", "run_id", "run_name", "seed_source"]]
        warnings.warn(
            "Some runs did not expose a real seed in W&B config; inspect the generated .runs.csv before "
            "reporting seed-based statistics.\n"
            f"{missing.to_string(index=False)}",
            stacklevel=2,
        )

    agg_df = aggregate_curves(raw_df=raw_df, metric=args.metric, step_key=args.step_key, error_band=args.error_band)
    final_df = summarize_final_points(raw_df=raw_df, metric=args.metric, step_key=args.step_key)

    fig = plot_curves(
        agg_df=agg_df,
        runs_df=runs_df,
        metric=args.metric,
        step_key=args.step_key,
        title=args.title,
        xlabel=args.xlabel,
        ylabel=args.ylabel,
        legend_loc=args.legend_loc,
        figsize=figsize,
    )
    out_prefix = Path(args.out_prefix)
    save_outputs(
        fig=fig,
        out_prefix=out_prefix,
        formats=formats,
        dpi=args.dpi,
        step_key=args.step_key,
        runs_df=runs_df,
        raw_df=raw_df,
        agg_df=agg_df,
        final_df=final_df,
    )
    print_final_summary(final_df)
    print(f"\nSaved plot and tables with prefix: {out_prefix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
