# Bank-statement-PDF-to-csv-html-onenote

Local-first Python CLI (`bs2o`) to process bank statement outputs from MinerU into:
- monthly CSV files
- combined CSV
- monthly pie + daily stacked bar charts
- monthly summary metrics
- OneNote preview HTML and optional live OneNote sync via Microsoft Graph

## Benefits
- No manual copy/paste of statement tables.
- Re-runnable monthly reporting workflow.
- Local parsing/export by default; cloud only when OneNote live sync is enabled.
- Beginner-friendly `init` and config-based runs.

## Pre-requirements
- Python 3.10+
- MinerU installed (used to generate markdown from PDF)
- For live OneNote sync:
  - Azure App Registration with delegated Graph permissions:
    - `Notes.ReadWrite`
    - `offline_access`
    - `User.Read`
  - App `client_id`

## Install
```powershell
python -m pip install -e .
```

Optional:
```powershell
python -m pip install matplotlib openpyxl
```

## Typical workflow
1. Export from existing MinerU markdown:
```powershell
bs2o export --config "D:\bs2o_test\config.yaml"
```

2. Generate OneNote preview HTML:
```powershell
bs2o sync-onenote --config "D:\bs2o_test\config.yaml"
```

3. Preview + live OneNote sync:
```powershell
bs2o sync-onenote --config "D:\bs2o_test\config.yaml" --onenote-live
```

## Example config
```yaml
paths:
  input_pdf_dir: "D:/pdf_report"
  mineru_output_dir: "D:/bs2o_test/pdf_convert"
  export_dir: "D:/bs2o_test/export"

mineru:
  command: "mineru"
  args:
    - "-p"
    - "{input}"
    - "-o"
    - "{output}"

onenote:
  enabled: true
  graph_enabled: true
  notebook_name: "My Notebook"
  section_name: "bank-data"
  page_title: "PTSB-estatement"
  tenant: "common"
  client_id: "YOUR_CLIENT_ID"
  scopes:
    - "Notes.ReadWrite"
    - "offline_access"
    - "User.Read"
  token_cache_file: "D:/bs2o_test/.bs2o_graph_token.json"

reports:
  charts_enabled: true
  monthly_table_enabled: true
```

## Output files
Under `paths.export_dir`:
- `YYYY.MM.csv`
- `all_transactions.csv`
- `charts/YYYY.MM_income_vs_spending.png`
- `charts/YYYY.MM_daily_income_spending.png`
- `onenote_sync_preview.html`

## Notes
- `--config` works before or after subcommand.
- If config file does not exist, `bs2o` can prompt first-run setup in interactive terminal.
