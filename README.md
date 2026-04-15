# wandb2fig

Pull curves from W&B, aggregate repeated runs yourself, and export paper-ready figures plus CSV tables.

## What It Does

- fetches `step + metric` directly from W&B history
- groups runs by regex on `run.name`
- computes `mean ± std` or `mean ± 95% CI`
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
  --error-band [std|ci95] \
  --smooth-method [rolling|ema] \
  --smooth-window [0|5|9|...] \
  --ylabel '[y_label]' \
  --title '[figure_title]' \
  --out-prefix fig/[name]/[name]
```

This layout keeps every figure bundle under its own directory, for example `fig/[name]/[name].pdf` and `fig/[name]/[name].final.csv`.
Use `--style softgrid` for a softer RL-curve look similar to the screenshot style you shared.
Use `--series-runs` when you want to specify exact W&B run ids or full run URLs instead of matching by run name regex.
Use `--align-mode linear` when different runs log at slightly different steps and you still want a visible aggregate band.
Use `--smooth-method ema` for exponential moving average smoothing.
Use `--smooth-window` to control the rolling window or EMA span after alignment.

### W&B Smoothing ↔ EMA Span

`--smooth-window` sets the pandas `ewm(span=...)`. The conversion to W&B's smoothing weight is `w = (span − 1) / (span + 1)`.

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
- `*.agg.csv`: per-step aggregated mean and band
- `*.final.csv`: final-point summary with `mean/std/95% CI`

## Notes

- If a run does not expose a real `seed` in W&B config, the script falls back to a run identifier and warns you.
- Check `*.runs.csv` before reporting seed-based statistics in the paper.
