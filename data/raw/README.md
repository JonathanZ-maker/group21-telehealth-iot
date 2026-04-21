# Raw datasets

Put the **unmodified** downloaded dataset here (e.g. the Kaggle CSV).

**Do not commit large files** (see `.gitignore`). If the file is > 10 MB, upload it to Google Drive / OneDrive and link the URL from this README instead.

## Expected file

LKK to fill in once the dataset is chosen:

- **Name:** Heart rate time series
- **URL:** https://www.kaggle.com/datasets/ahmadsaeed1007/heart-rate-time-series-mitbih-database
- **Access date:** 2026-4-19
- **Licence:** MIT
- **Description:** 4 series contains 1800 evenly-spaced measurements of instantaneous heart rate from a single subject

## Reproducibility note

All derived files in `data/processed/` can be regenerated from this raw input by running:

```bash
python scripts/clean_data.py
```
