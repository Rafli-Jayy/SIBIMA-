"""Format tampilan: rupiah, tanggal, persen."""
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
         "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def rupiah(angka):
    """450000 -> 'Rp 450.000'"""
    return "Rp " + f"{int(round(angka)):,}".replace(",", ".")


def tanggal(d):
    """date/datetime -> '21 Okt 2026'"""
    return f"{d.day:02d} {BULAN[d.month - 1]} {d.year}"


def persen(nilai):
    return f"{nilai:.1f}%"
