from datetime import date, datetime

import pytest

from app.services import billing_receipt_service


def sample_detail():
    return {
        "payment_id": 42,
        "kode_bayar": "VA00000042ABCD1234",
        "payment_status": "lunas",
        "payment_jumlah": 450000,
        "invoice_id": 9,
        "no_invoice": "INV-TEST-0009",
        "periode": date(2026, 10, 1),
        "invoice_jumlah": 450000,
        "jatuh_tempo": date(2026, 10, 31),
        "nama_siswa": "Rafli Wijaya",
        "nis": "S-0001",
        "nama_program": "IPA SMA",
        "kode_program": "IPA-SMA",
        "email_siswa": "rafli@example.com",
        "paid_at": datetime(2026, 10, 26, 10, 0),
        "processed_at": datetime(2026, 10, 26, 10, 30),
    }


def test_buat_pdf_bukti_lunas(tmp_path, monkeypatch):
    monkeypatch.setattr(billing_receipt_service, "BUKTI_DIR", tmp_path)
    path = billing_receipt_service.buat_pdf_bukti(sample_detail())
    assert path.exists()
    assert path.suffix == ".pdf"
    assert path.read_bytes().startswith(b"%PDF-")
    assert path.stat().st_size > 1000


def test_bukti_pdf_ditolak_jika_belum_lunas(tmp_path, monkeypatch):
    monkeypatch.setattr(billing_receipt_service, "BUKTI_DIR", tmp_path)
    detail = sample_detail()
    detail["payment_status"] = "menunggu_konfirmasi"
    with pytest.raises(ValueError, match="LUNAS"):
        billing_receipt_service.buat_pdf_bukti(detail)
    assert list(tmp_path.iterdir()) == []


def test_email_bukti_ditolak_jika_status_bukan_lunas(tmp_path):
    detail = sample_detail()
    detail["payment_status"] = "ditolak"
    ok, pesan = billing_receipt_service.kirim_pdf_via_email(detail, tmp_path / "tidak-ada.pdf")
    assert not ok
    assert "LUNAS" in pesan


def test_email_melampirkan_pdf_tanpa_koneksi_smtp_nyata(tmp_path, monkeypatch):
    monkeypatch.setattr(billing_receipt_service, "BUKTI_DIR", tmp_path)
    monkeypatch.setattr(billing_receipt_service, "SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr(billing_receipt_service, "SMTP_PORT", 587)
    monkeypatch.setattr(billing_receipt_service, "SMTP_USER", "no-reply@example.test")
    monkeypatch.setattr(billing_receipt_service, "SMTP_PASSWORD", "dummy-test-password")
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            assert host == "smtp.example.test"
            assert port == 587

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            return None

        def starttls(self, context=None):
            return None

        def login(self, username, password):
            assert username == "no-reply@example.test"
            assert password == "dummy-test-password"

        def send_message(self, message):
            sent["message"] = message
            return {}

    monkeypatch.setattr(billing_receipt_service.smtplib, "SMTP", FakeSMTP)
    detail = sample_detail()
    pdf_path = billing_receipt_service.buat_pdf_bukti(detail)
    ok, pesan = billing_receipt_service.kirim_pdf_via_email(detail, pdf_path)

    assert ok, pesan
    assert sent["message"]["To"] == "rafli@example.com"
    attachments = list(sent["message"].iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/pdf"
    assert attachments[0].get_filename().endswith(".pdf")
