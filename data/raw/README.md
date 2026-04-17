# Raw datasets

Put the **unmodified** downloaded dataset here (e.g. the Kaggle CSV).

**Do not commit large files** (see `.gitignore`). If the file is > 10 MB, upload it to Google Drive / OneDrive and link the URL from this README instead.

## Expected file

LKK to fill in once the dataset is chosen:

- **Name:** <e.g. PPG-DaLiA — PPG-based Heart-Rate Dataset>
- **URL:** <https://...>
- **Access date:** <YYYY-MM-DD>
- **Licence:** <CC-BY-4.0 / MIT / ...>
- **Citation:** <BibTeX or plain text>
- **Description:** n subjects, sampling rate, total records, any known limitations

## Reproducibility note

All derived files in `data/processed/` can be regenerated from this raw input by running:

```bash
python scripts/clean_data.py
```
