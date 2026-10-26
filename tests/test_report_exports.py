from csv import DictReader
from datetime import date
from decimal import Decimal

from openpyxl import load_workbook

from app.services import report_service


def _pasang_data_uji(monkeypatch, tmp_path):
    data = [
        {"bulan": date(2026, 9, 1), "jumlah_transaksi": 3, "total_pemasukan": Decimal("1250000")},
        {"bulan": date(2026, 10, 1), "jumlah_transaksi": 2, "total_pemasukan": Decimal("850000")},
    ]
    definisi = {
        "judul": "Pemasukan per Bulan",
        "kolom": [
            ("bulan", "Bulan"),
            ("jumlah_transaksi", "Jumlah transaksi lunas"),
            ("total_pemasukan", "Total pemasukan (Rp)"),
        ],
        "ambil": lambda: data,
    }
    monkeypatch.setattr(report_service, "BASE_DIR", tmp_path)
    monkeypatch.setattr(report_service, "_admin_aktif", lambda: {"id": 1, "nama_lengkap": "Admin"})
    monkeypatch.setattr(report_service.log_repo, "catat", lambda *args, **kwargs: None)
    monkeypatch.setitem(report_service.LAPORAN, "pemasukan", definisi)


def test_ekspor_csv_memakai_pemisah_semikolon_dan_utf8_bom(monkeypatch, tmp_path):
    _pasang_data_uji(monkeypatch, tmp_path)

    path = report_service.ekspor_csv("pemasukan")

    assert path.exists()
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        rows = list(DictReader(file, delimiter=";"))
    assert len(rows) == 2
    assert rows[0]["Bulan"] == "2026-09-01"
    assert rows[0]["Total pemasukan (Rp)"] == "1250000"


def test_ekspor_excel_memiliki_format_filter_dan_total(monkeypatch, tmp_path):
    _pasang_data_uji(monkeypatch, tmp_path)

    path = report_service.ekspor_excel("pemasukan")

    assert path.exists()
    workbook = load_workbook(path, data_only=False)
    sheet = workbook.active
    assert sheet["A1"].value == "SIBIMA  |  PEMASUKAN PER BULAN"
    assert sheet["A4"].value == "Bulan"
    assert sheet.freeze_panes == "A5"
    assert sheet.auto_filter.ref == "A4:C6"
    assert sheet["C5"].number_format.startswith('"Rp"')
    # Total berada tepat setelah dua baris data (row 7), di luar autofilter data.
    assert sheet["A7"].value == "TOTAL PADA DATA YANG DITAMPILKAN"
    assert sheet["B7"].value == 5
    assert sheet["C7"].value == 2100000
