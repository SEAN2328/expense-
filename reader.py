"""Input reading module.

Responsible for loading raw expense/invoice records from a CSV file and
performing light validation/normalisation before analysis.
"""

from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {"date", "vendor", "description", "amount"}


class InputError(Exception):
    """Raised when the input data cannot be read or is invalid."""


def read_expenses(source) -> pd.DataFrame:
    """Read a CSV of expenses and return a normalised DataFrame.

    `source` may be a file path (str/PathLike) or any file-like object that
    pandas can read (e.g. a Streamlit UploadedFile).

    Expected columns: date, vendor, description, amount
    Additional columns (e.g. category hints, employee) are allowed.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise InputError(f"Input file not found: {source}")
        csv_args = (path,)
    else:
        csv_args = (source,)

    try:
        df = pd.read_csv(*csv_args)
    except Exception as exc:  # pragma: no cover - defensive
        raise InputError(f"Could not parse CSV: {exc}") from exc

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise InputError(f"Missing required columns: {sorted(missing)}")

    df = df.copy()
    # Normalise text fields.
    for col in ["vendor", "description"]:
        df[col] = df[col].astype(str).str.strip()

    # Parse dates flexibly; invalid dates become NaT and are flagged later.
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    return df
