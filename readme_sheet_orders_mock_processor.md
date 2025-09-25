# Orders Mock Processor

Python script to read orders from a Google Sheet and **simulate** order creation, validating required fields and reporting errors clearly.

---

## ✨ Features
- Reads Google Sheets via `gspread` with service account credentials.
- Tolerant header normalization (accepts variants like `Total ($)`, `correo`, etc.).
- Business validations:
  - `status` required (only processes `new`).
  - `customer_name` required.
  - `email` required and must be a valid format.
  - `total` required, parseable as amount, and **> 0**.
- Output with `[CREATE]`, `[SKIP]`, `[ERROR]` lines and a final **summary**.

---

## 📦 Requirements
- Python 3.10+
- Dependencies:
  - `gspread`
  - `google-auth`

Install:
```bash
pip install gspread google-auth
```

> Recommended: use a virtual environment.

---

## 🔐 Google Credentials
1. Create a **Service Account** in Google Cloud and download the JSON credentials.
2. Share your spreadsheet with the Service Account email (at least **Viewer** permission).
3. Save the file as `credentials.json` (or point to its path with env var).

Scopes used (read-only):
- `https://www.googleapis.com/auth/spreadsheets.readonly`
- `https://www.googleapis.com/auth/drive.readonly`

---

## ⚙️ Environment Variables
| Variable | Required | Default | Description |
|---|---|---|---|
| `SHEET_ID` | ✅ | `<PUT_YOUR_SHEET_ID_HERE>` | Google Sheet ID (between `/d/` and `/edit`). |
| `WORKSHEET_NAME` | ✅ | `Orders` | Name of the worksheet/tab. |
| `GOOGLE_APPLICATION_CREDENTIALS` | ✅ | `credentials.json` | Path to service account JSON file. |

Example:
```bash
export SHEET_ID="1AbC...xyz"
export WORKSHEET_NAME="Orders"
export GOOGLE_APPLICATION_CREDENTIALS="./credentials.json"
```

---

## 📑 Expected Sheet Structure
- Row 1: **headers**.
- Following rows: data.

### Header normalization
The script normalizes headers to lowercase with underscores. It also uses tolerant matching for aliases.

Aliases recognized:
- **status** → `status`
- **customer_name** → `customer_name`
- **email** → `email`, `correo`, `mail`
- **total** → `total`, `importe`, `amount`, `monto`, `Total ($)`

---

## ✅ Validation Rules
Each row must satisfy:
- `status` not empty (only `new` is confirmed).
- `customer_name` not empty.
- `email` not empty and must match `local@domain.tld`.
- `total` not empty, parseable, and greater than 0.

Rows failing validation are marked as **ERROR** and skipped.

---

## 🧠 Processing Flow
1. Read headers and rows via `gspread`.
2. Build tolerant header map.
3. For each row, extract fields with `get_field(...)`.
4. Validate email and total (`parse_amount`).
5. If valid and `status == "new"`, create mock payload and log `[CREATE]`.
6. If status is not `new`, log `[SKIP]`.
7. Print **SUMMARY** with created orders and errors.

---

## ▶️ Run
```bash
python orders_processor.py
```

Example output:
```
[ERROR] Row 2: missing/invalid Email, Total_parseable
[CREATE] Row 3: created mock order 123 → { ... }
[SKIP] Row 4: status 'confirmed' is not 'new'.

=== SUMMARY ===
Mock orders created: 1
Rows with errors: 1
```

---

## 🧩 Customization
- **Column aliases**: extend the aliases in `get_field(...)`.
- **Additional rules**: add new checks in the validation block.
- **Output**: replace `print(...)` with logging if needed.

---

## 🛡️ Security
- Do not commit `credentials.json` to version control.
- Keep permissions minimal (read-only).
- Rotate credentials if compromised.

---

## 🔧 Troubleshooting
- **`Configure your SHEET_ID`** → set the env var correctly.
- **Module not found** → install `gspread` and `google-auth`.
- **No access** → share the sheet with the service account.
- **Empty total** → check header aliases.
- **Invalid email** → must match `user@domain.tld`.

---

## 🧪 Quick Test Sheet
Example minimal worksheet:

| Status | Customer Name | Email | Total |
|---|---|---|---|
| new | Jane Doe | jane@example.com | 120.00 |
| new |  | bad@example | 0 |
| confirmed | John | john@example.com | 50 |

Expected result:
- Row 2 → **CREATE**
- Row 3 → **ERROR** (empty name, invalid email, total not positive)
- Row 4 → **SKIP**

---


