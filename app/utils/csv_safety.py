"""Helper CSV untuk mengurangi risiko formula injection saat dibuka di spreadsheet."""

from datetime import date, datetime
from decimal import Decimal


def nilai_csv_aman(nilai) -> str:
    """Konversi nilai untuk CSV dan netralkan teks yang bisa dianggap formula spreadsheet."""
    if nilai is None:
        return ""
    if isinstance(nilai, (date, datetime)):
        return nilai.isoformat()
    if isinstance(nilai, (int, float, Decimal)) and not isinstance(nilai, bool):
        return str(nilai)

    teks = str(nilai)
    awal = teks.lstrip(" \t\r\n")
    if awal.startswith(("=", "+", "-", "@")) or teks.startswith(("\t", "\r", "\n")):
        return "'" + teks
    return teks
