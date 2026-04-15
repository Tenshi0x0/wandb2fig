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
  --entity OpenMLRL \
  --project multi-source-gathering-tianle \
  --series 'baseline::^dt-baseline_msg_108_4B4B4B_singlegpu$' \
  --series 'meta::^dt-meta_msg_108_4B4B4B_singlegpu$' \
  --metric 'eval/answer_score' \
  --error-band ci95 \
  --ylabel 'Validation Answer Score' \
  --title 'HybridQA Multi-Source 108' \
  --out-prefix figures/hybridqa_108_eval_answer_score
```

## Outputs

- `*.pdf` and `*.png`: final figure
- `*.runs.csv`: exact W&B runs used
- `*.raw.csv`: per-run history rows
- `*.agg.csv`: per-step aggregated mean and band
- `*.final.csv`: final-point summary with `mean/std/95% CI`

## Notes

- If a run does not expose a real `seed` in W&B config, the script falls back to a run identifier and warns you.
- Check `*.runs.csv` before reporting seed-based statistics in the paper.
- The current example output lives under [figures](/u/tchen19/wandb2fig/figures).
