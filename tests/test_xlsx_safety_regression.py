"""Regresi keamanan ekspor XLSX: teks pengguna tidak boleh menjadi formula Excel.

Pengujian ini memakai data in-memory dan tidak memerlukan koneksi database.
"""

from datetime import date
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from app.services import report_service


def _pasang_laporan(monkeypatch, tmp_path, kode, kolom, baris):
    monkeypatch.setattr(report_service, "BASE_DIR", tmp_path)
    monkeypatch.setattr(report_service, "_admin_aktif", lambda: {"id": 1})
    monkeypatch.setattr(report_service.log_repo, "catat", lambda *args, **kwargs: None)
    monkeypatch.setitem(report_service.LAPORAN, kode, {
        "judul": "Laporan Uji XLSX",
        "kolom": kolom,
        "ambil": lambda: baris,
    })


@pytest.mark.parametrize("teks", [
    "=1+1",
    '=HYPERLINK("https://example.invalid", "Buka")',
    "=SUM(A1:A2)",
    "+SUM(1,2)",
    "-1+2",
    "@SUM(1,2)",
    "  =1+1",
    "\t=1+1",
    "\n=1+1",
])
def test_nama_dari_database_tetap_teks_lengkap(monkeypatch, tmp_path, teks):
    _pasang_laporan(
        monkeypatch, tmp_path, "siswa_program",
        [("nama_program", "Nama program")],
        [{"nama_program": teks}],
    )

    path = report_service.ekspor_excel("siswa_program")
    sheet = load_workbook(path, data_only=False).active

    assert sheet["A5"].value == teks
    assert sheet["A5"].data_type == "s", "Nilai teks tidak boleh dieksekusi sebagai formula"


def test_tipe_angka_tanggal_dan_format_tetap_dipertahankan(monkeypatch, tmp_path):
    _pasang_laporan(
        monkeypatch, tmp_path, "pemasukan",
        [("bulan", "Bulan"), ("jumlah_transaksi", "Transaksi"), ("total_pemasukan", "Total")],
        [{"bulan": date(2026, 11, 1), "jumlah_transaksi": 2,
          "total_pemasukan": Decimal("125000.50")}],
    )

    path = report_service.ekspor_excel("pemasukan")
    sheet = load_workbook(path, data_only=False).active

    assert sheet["A5"].value.date() == date(2026, 11, 1)
    assert sheet["A5"].data_type == "d"
    assert sheet["B5"].value == 2
    assert sheet["B5"].data_type == "n"
    assert sheet["C5"].value == 125000.5
    assert sheet["C5"].data_type == "n"
    assert sheet["C5"].number_format.startswith('"Rp"')
    assert sheet["B6"].value == 2
    assert sheet["C6"].value == 125000.5


def test_teks_biasa_dan_kosong_tetap_seperti_semula(monkeypatch, tmp_path):
    _pasang_laporan(
        monkeypatch, tmp_path, "siswa_program",
        [("kode_program", "Kode"), ("nama_program", "Nama"), ("jenjang", "Jenjang")],
        [{"kode_program": "IPA-01", "nama_program": "Kelas Matematika", "jenjang": None}],
    )

    path = report_service.ekspor_excel("siswa_program")
    sheet = load_workbook(path, data_only=False).active

    assert sheet["A5"].value == "IPA-01"
    assert sheet["A5"].data_type == "s"
    assert sheet["B5"].value == "Kelas Matematika"
    assert sheet["B5"].data_type == "s"
    assert sheet["C5"].value is None
    assert sheet.freeze_panes == "A5"
    assert sheet.auto_filter.ref == "A4:C5"
