"""Shared source parser, also embedded verbatim in standalone generated Python."""

import csv
import io

import pandas as pd
from pandas.api.types import is_float_dtype, is_numeric_dtype


class CSVFormatError(ValueError):
    """Safe structural validation message, containing no source values."""


def lossy_nullable_integers(series):
    """sklearn converts nullable integers to float64, potentially merging values."""
    return str(series.dtype) in {"Int64", "UInt64"} and any(
        abs(int(value)) > 2**53 - 1 for value in series.dropna().unique()
    )


def parse_csv_bytes(data: bytes) -> pd.DataFrame:
    """UTF-8/BOM, comma, header, standard quoting and pandas default NA tokens.

    Validate widths/headers before pandas can rename duplicates or infer an index.
    Blank physical lines are ignored; rows containing empty fields are retained.
    """
    try:
        with io.StringIO(data.decode("utf-8-sig"), newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next((row for row in reader if row), None)
            if not header or any(not name.strip() for name in header):
                raise CSVFormatError("CSV needs a non-empty header for every column.")
            if len(set(header)) != len(header):
                raise CSVFormatError("CSV column names must be unique.")
            if any(any(ord(char) < 32 for char in name) for name in header):
                raise CSVFormatError("CSV headers cannot contain control characters.")
            count = 0
            for row in reader:
                if not row:
                    continue
                if len(row) != len(header) or any("\x00" in value for value in row):
                    raise CSVFormatError("Malformed CSV: each row must match the header width.")
                count += 1
            if not count:
                raise CSVFormatError("CSV needs at least one data row.")
        frame = pd.read_csv(io.BytesIO(data), encoding="utf-8-sig", low_memory=False)
        if len(frame) != count or list(frame.columns) != header:
            raise CSVFormatError(
                "CSV parsing did not preserve the complete header and row structure."
            )
        # Default pandas inference promotes nullable integers to float64, which
        # can merge large target classes before JSON serialization sees them.
        # Re-read only precision-risk columns as tokens; actual floating-point
        # columns keep their usual interpretation.
        risky = [
            name
            for name in frame
            if (is_float_dtype(frame[name].dtype) and frame[name].abs().gt(2**53 - 1).any())
            or (
                not is_numeric_dtype(frame[name].dtype)
                and frame[name].astype("string").str.fullmatch(r"[+-]?\d{16,}").any()
            )
        ]
        if risky:
            tokens = pd.read_csv(
                io.BytesIO(data), encoding="utf-8-sig", usecols=risky, dtype="string"
            )
            for name in risky:
                observed = tokens[name].dropna()
                if not observed.empty and observed.str.fullmatch(r"[+-]?\d+").all():
                    values = [None if pd.isna(value) else int(value) for value in tokens[name]]
                    integers = [value for value in values if value is not None]
                    if min(integers) >= -(2**63) and max(integers) < 2**63:
                        frame[name] = pd.array(values, dtype="Int64")
                    elif min(integers) >= 0 and max(integers) < 2**64:
                        frame[name] = pd.array(values, dtype="UInt64")
                    else:
                        # Python integers remain lossless even beyond NumPy's range.
                        frame[name] = pd.Series(values, dtype=object)
        return frame
    except CSVFormatError:
        raise
    except (UnicodeError, csv.Error, pd.errors.ParserError, pd.errors.EmptyDataError, ValueError):
        raise ValueError(
            "Cannot parse CSV. Use UTF-8, comma separators, and valid CSV quoting."
        ) from None
