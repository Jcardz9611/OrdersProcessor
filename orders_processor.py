from __future__ import annotations

import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

import gspread
from gspread.utils import rowcol_to_a1
from google.oauth2.service_account import Credentials

# Env vars
SHEET_ID = os.environ.get("SHEET_ID", "<PUT_YOUR_SHEET_ID_HERE>")
WORKSHEET_NAME = os.environ.get("WORKSHEET_NAME", "Orders")
CREDS_FILE = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")

# Scopes: read/write to update processed_at
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def norm_key(s: str) -> str:
    """Basic snake-ish normalization for header keys."""
    return (
        str(s)
        .strip()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("__", "_")
        .lower()
    )


def _lookup_key_searchform(k: str) -> str:
    """Remove non [a-z0-9_] for tolerant matching."""
    return re.sub(r"[^a-z0-9_]+", "", k)


def open_sheet():
    """Authorize and open worksheet."""
    if not SHEET_ID or SHEET_ID.startswith("<PUT_"):
        raise SystemExit("Configure your SHEET_ID")
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(SHEET_ID).worksheet(WORKSHEET_NAME)
    return ws


def ensure_processed_at_column(ws) -> int:
    """Ensure the 'processed_at' column exists and return its 1-based index."""
    values = ws.get_all_values()
    if not values:
        ws.update("A1", "processed_at")
        return 1
    headers = values[0]
    norm_headers = [norm_key(h) for h in headers]
    if "processed_at" in norm_headers:
        return norm_headers.index("processed_at") + 1
    new_col_index = len(headers) + 1
    ws.update(rowcol_to_a1(1, new_col_index), "processed_at")
    return new_col_index


def read_rows(ws) -> List[Dict]:
    """Read rows and attach a tolerant header map."""
    values = ws.get_all_values()
    if not values:
        return []
    headers = [norm_key(h) for h in values[0]]
    search_keys = {_lookup_key_searchform(h): h for h in headers}
    rows: List[Dict] = []
    for i, row in enumerate(values[1:], start=2):
        rec = {headers[j]: (row[j].strip() if j < len(headers) else "")
               for j in range(len(headers))}
        rec["_rownum"] = i
        rec["_search_keys"] = search_keys
        rows.append(rec)
    return rows


def get_field(rec: Dict, *logical_names: str) -> str:
    """Fetch a value trying multiple logical names with tolerant header matching."""
    search_map: Dict[str, str] = rec.get("_search_keys", {})
    for name in logical_names:
        search_name = _lookup_key_searchform(norm_key(name))
        if search_name in search_map:
            real_key = search_map[search_name]
            return str(rec.get(real_key, "")).strip()
        for skey, real_key in search_map.items():
            if skey.startswith(search_name):
                return str(rec.get(real_key, "")).strip()
    return ""


def parse_amount(s: str) -> Optional[Decimal]:
    """Parse money-like text into Decimal. Return None if invalid."""
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    cleaned = re.sub(r"[^\d.,-]", "", s)
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    else:
        if "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def is_valid_email(s: str) -> bool:
    """Very basic email format check."""
    if not s:
        return False
    return re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", s) is not None


def simulate_create_order(rec: Dict) -> Dict:
    """Mock order creation payload."""
    return {
        "id": rec.get("order_id") or f"row-{rec.get('_rownum')}",
        "customer": rec.get("customer_name", ""),
        "email": rec.get("email", ""),
        "product": rec.get("product", ""),
        "total": rec.get("total", ""),
        "source_row": rec.get("_rownum"),
        "created_at": datetime.now().replace(microsecond=0).isoformat(),
    }


def main():
    ws = open_sheet()
    processed_at_col = ensure_processed_at_column(ws)

    # US-style, human-readable local time, e.g. "09/25/2025 02:03:07 PM"
    run_ts = datetime.now().strftime("%m/%d/%Y %I:%M:%S %p")

    rows = read_rows(ws)
    mock_orders: Dict[str, Dict] = {}
    errors: List[Dict] = []

    cells_to_update = []  # batch write for processed_at

    for rec in rows:
        status = get_field(rec, "status").lower()
        customer = get_field(rec, "customer_name")
        email = get_field(rec, "email", "correo", "mail")
        total_str = get_field(rec, "total", "importe", "amount", "monto")

        missing = []
        if status == "":
            missing.append("Status")
        if customer == "":
            missing.append("Customer_name")
        if email == "":
            missing.append("Email")
        elif not is_valid_email(email):
            missing.append("Email_valid")
        if total_str == "":
            missing.append("Total")

        amount = parse_amount(total_str) if total_str else None
        if amount is None:
            missing.append("Total_parseable")
        elif amount <= 0:
            missing.append("Total_positive")

        # Always mark processed_at for the row
        cells_to_update.append({
            "range": rowcol_to_a1(rec["_rownum"], processed_at_col),
            "values": [[run_ts]],
        })

        if missing:
            errors.append({"row": rec.get("_rownum"), "missing": missing})
            print(
                f"[ERROR] Row {rec.get('_rownum')}: missing/invalid {', '.join(missing)}")
            continue

        if status == "new":
            rec_for_mock = dict(rec)
            rec_for_mock["total"] = str(amount)
            rec_for_mock["email"] = email
            payload = simulate_create_order(rec_for_mock)
            key = str(payload["id"])
            if key in mock_orders:
                print(
                    f"[SKIP] Row {rec.get('_rownum')}: order {key} already created.")
                continue
            mock_orders[key] = payload
            print(
                f"[CREATE] Row {rec.get('_rownum')}: created mock order {key} → {payload}")
        else:
            print(
                f"[SKIP] Row {rec.get('_rownum')}: status '{status}' is not 'new'.")

    # Batch update processed_at
    if cells_to_update:
        body = {
            "valueInputOption": "RAW",
            "data": [{"range": c["range"], "values": c["values"]} for c in cells_to_update],
        }
        ws.spreadsheet.values_batch_update(body)

    print("\n=== SUMMARY ===")
    print(f"Mock orders created: {len(mock_orders)}")
    print(f"Rows with errors: {len(errors)}")


if __name__ == "__main__":
    main()
