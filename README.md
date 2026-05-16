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
  --colors '[c1,c2,...]' \
  --xtick-step [int] \
  --ytick-step [float] \
  --xtick-as-k \
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

## Paper figure recipe

The configuration below was validated for a recent paper submission. It is the recommended starting point for two-method training-curve comparisons with small `n` (around 5 seeds per method).

```bash
python plot_wandb_runs.py \
  --entity [entity] \
  --project [project] \
  --series 'Method A::^a' \
  --series 'Method B::^b' \
  --metric '[metric]' \
  --style softgrid \
  --align-mode linear \
  --resample-points 80 \
  --error-band std \
  --smooth-window 0 \
  --colors '#d62728,#1f77b4' \
  --ylabel 'Return' \
  --xtick-step [task-specific] \
  --ytick-step [task-specific] \
  --xtick-as-k \
  --out-prefix fig/[name]/[name]
```

Key choices and why:

- **No smoothing (`--smooth-window 0`).** EMA-smoothed tails undershoot the real final values reported in `*.final.csv`. EMA also phase-shifts runs against each other, which inflates cross-run std — so the unsmoothed bands are actually *narrower* than smoothed ones. Pure raw curves match the numerical summary best.
- **`--error-band std`, not `ci95`.** At `n ≈ 5`, the `ci95` factor (`std × 2.776 / √n ≈ std × 1.24`) makes bands wider than `std` and the gap between methods harder to see. `std` is tight and self-explanatory in the caption.
- **No `--title`.** The figure title belongs in the paper caption, not on the figure.
- **`--colors '#d62728,#1f77b4'` (Tableau red + blue).** Pure `red,blue` is too saturated for a paper page; muted seaborn-deep tones (`#c44e52,#4c72b0`) are too washed out under print. Tableau is the middle ground.
- **`--xtick-as-k`.** Once x-axis values cross 1000, three trailing zeros crowd the labels at any reasonable tick density. Kilo notation (`1k`, `1.5k`, `7k`) keeps labels readable without changing the tick positions.
- **`--xtick-step` and `--ytick-step` per task.** Pick steps that give 5–8 visible labels across the axis range. As a rule of thumb: use `xtick-step` ≈ (max step) / 6, and `ytick-step` ≈ (y range) / 6, rounded to a clean number.
- **`--resample-points 80`.** Lower than the default 400, on purpose. Without smoothing, 80 keeps the curve shape readable while still showing real variation; 400 looks noisy.

Outputs:

- `*.pdf` is the camera-ready figure; `*.png` is for slides and quick previews.
- `*.runs.csv` lists the exact W&B runs used — sanity-check this before reporting seed-based statistics, since runs without a real seed in config fall back to `run_id`.
- `*.final.csv` has the final-point `mean / std / n / ci95` per series, ready to drop into a paper table.

## Outputs

- `*.pdf` and `*.png`: final figure
- `*.runs.csv`: exact W&B runs used
- `*.raw.csv`: per-run history rows
- `*.agg.csv`: resampled per-step aggregated mean and band
- `*.final.csv`: final-point summary with `mean/std/95% CI`

## Notes

- If a run does not expose a real `seed` in W&B config, the script falls back to a run identifier and warns you.
- Check `*.runs.csv` before reporting seed-based statistics in the paper.
