# wandb2fig

Pull curves from W&B, aggregate repeated runs yourself, and export paper-ready figures plus CSV tables.

## What It Does

- fetches `step + metric` directly from W&B history
- groups runs by regex on `run.name`
- smooths each run first, resamples onto a dense shared grid, then computes `mean ± std` or `mean ± 95% CI`
- uses `SciencePlots` when available and falls back cleanly if not
- saves both figures and intermediate tables for paper reporting

## Install

```bash
pip install -r requirements.txt
```
This installs the core plotting stack plus `SciencePlots`.

## Usage

```bash
python plot_wandb_runs.py \
  --entity [entity] \
  --project [project] \
  --series '[label_1]::[run_name_regex_1]' \
  --series '[label_2]::[run_name_regex_2]' \
  --series-runs '[label_3]::[run_id_or_url_1],[run_id_or_url_2]' \
  --metric '[metric]' \
  --style [science|softgrid|fallback] \
  --align-mode [exact|linear] \
  --linear-support [overlap|truncate-aware] \
  --resample-points [400] \
  --error-band [std|ci95] \
  --smooth-method [ema|rolling] \
  --smooth-window [0|5|9|...] \
  --ylabel '[y_label]' \
  --title '[figure_title]' \
  --out-prefix fig/[name]/[name]
```

This layout keeps every figure bundle under its own directory, for example `fig/[name]/[name].pdf` and `fig/[name]/[name].final.csv`.
Use `--style softgrid` for a softer RL-curve look similar to the screenshot style you shared.
Use `--series-runs` when you want to specify exact W&B run ids or full run URLs instead of matching by run name regex.
Use `--align-mode linear` for the W&B-like default path: each run is smoothed first, then all runs in a series are resampled onto a dense shared grid before aggregation.
Use `--linear-support truncate-aware` when some runs are truncated earlier and you want to keep the available longer tail; the aggregate will continue with smaller `n` after shorter runs end. The old `union` spelling is still accepted for compatibility.
Use `--smooth-method ema` for exponential moving average smoothing; this is the default.
Use `--smooth-window` to control the rolling window or EMA span applied to each run before aggregation.
By default, plotted series are clipped to the shortest finished curve. Pass `--no-clip-to-shortest-series` if you want to keep longer tails.

### W&B Smoothing ↔ EMA Span

`--smooth-window` sets the pandas `ewm(span=...)` when `--smooth-method ema`. The conversion to W&B's smoothing weight is `w = (span − 1) / (span + 1)`.

| W&B weight | `--smooth-window` (span) |
|------------|--------------------------|
| 0.8        | 9                        |
| 0.9        | 19                       |
| 0.95       | 39                       |
| 0.96       | 49                       |
| 0.97       | 66                       |
| 0.98       | 99                       |
| 0.99       | 199                      |

## Outputs

- `*.pdf` and `*.png`: final figure
- `*.runs.csv`: exact W&B runs used
- `*.raw.csv`: per-run history rows
- `*.agg.csv`: resampled per-step aggregated mean and band
- `*.final.csv`: final-point summary with `mean/std/95% CI`

## Notes

- If a run does not expose a real `seed` in W&B config, the script falls back to a run identifier and warns you.
- Check `*.runs.csv` before reporting seed-based statistics in the paper.
