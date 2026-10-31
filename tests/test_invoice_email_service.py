from datetime import date
from decimal import Decimal

import pytest

from app.services import invoice_email_service


@pytest.fixture
def invoice_data():
    return {
        "id": 99,
        "no_invoice": "INV-TEST-0099",
        "periode": date(2026, 10, 1),
        "jumlah": Decimal("450000.00"),
        "jatuh_tempo": date(2026, 11, 2),
        "status": "belum_dibayar",
    }


def test_pdf_invoice_dibuat_dan_bukan_bukti_lunas(tmp_path, monkeypatch, invoice_data):
    monkeypatch.setattr(invoice_email_service, "INVOICE_DIR", tmp_path)
    path = invoice_email_service.buat_pdf_invoice_pendaftaran(
        invoice_data, "Rafli Wijaya", "rafli@example.test", "IPA SMA"
    )
    assert path.exists()
    assert path.name == "INV-TEST-0099.pdf"
    assert path.read_bytes().startswith(b"%PDF-")
    assert path.stat().st_size > 1000


def test_email_invoice_menolak_status_lunas(tmp_path, monkeypatch, invoice_data):
    monkeypatch.setattr(invoice_email_service, "INVOICE_DIR", tmp_path)
    invoice_data["status"] = "lunas"
    ok, message = invoice_email_service.kirim_email_invoice_pendaftaran(
        "rafli@example.test", "Rafli", "IPA SMA", invoice_data
    )
    assert not ok
    assert "belum dibayar" in message.lower()
    assert list(tmp_path.glob("*.pdf")) == []


def test_email_invoice_html_dan_pdf_lampiran(tmp_path, monkeypatch, invoice_data):
    monkeypatch.setattr(invoice_email_service, "INVOICE_DIR", tmp_path)
    monkeypatch.setattr(invoice_email_service, "SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr(invoice_email_service, "SMTP_PORT", 587)
    monkeypatch.setattr(invoice_email_service, "SMTP_USER", "no-reply@example.test")
    monkeypatch.setattr(invoice_email_service, "SMTP_PASSWORD", "dummy-secret")
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
            assert password == "dummy-secret"

        def send_message(self, message):
            sent["message"] = message
            return {}

    monkeypatch.setattr(invoice_email_service.smtplib, "SMTP", FakeSMTP)
    ok, message = invoice_email_service.kirim_email_invoice_pendaftaran(
        "rafli@example.test", "Rafli Wijaya", "IPA SMA", invoice_data
    )

    assert ok, message
    email = sent["message"]
    assert email["To"] == "rafli@example.test"
    assert "INV-TEST-0099" in email["Subject"]
    html_part = email.get_body(preferencelist=("html",))
    assert html_part is not None
    html_content = html_part.get_content()
    assert "IPA SMA" in html_content
    assert "Rp 450.000" in html_content
    assert "MENUNGGU PEMBAYARAN" in html_content
    attachments = list(email.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/pdf"
    assert attachments[0].get_filename() == "INV-TEST-0099.pdf"
    assert attachments[0].get_payload(decode=True).startswith(b"%PDF-")


def test_email_invoice_menolak_alamat_tidak_valid(tmp_path, monkeypatch, invoice_data):
    monkeypatch.setattr(invoice_email_service, "INVOICE_DIR", tmp_path)
    ok, message = invoice_email_service.kirim_email_invoice_pendaftaran(
        "invalid-address", "Rafli", "IPA SMA", invoice_data
    )
    assert not ok
    assert "email" in message.lower()
    assert len(list(tmp_path.glob("*.pdf"))) == 1


def test_pdf_invoice_escape_html_dan_nama_file(tmp_path, monkeypatch, invoice_data):
    monkeypatch.setattr(invoice_email_service, "INVOICE_DIR", tmp_path)
    invoice_data["no_invoice"] = "INV/TEST:<099>"
    path = invoice_email_service.buat_pdf_invoice_pendaftaran(
        invoice_data, "Nama <script>alert(1)</script>", "rafli@example.test", "IPA <SMA>"
    )
    assert path.parent == tmp_path
    assert "/" not in path.name
    assert path.read_bytes().startswith(b"%PDF-")


def test_email_tagihan_bulanan_html_dan_pdf(tmp_path, monkeypatch, invoice_data):
    monkeypatch.setattr(invoice_email_service, "INVOICE_DIR", tmp_path)
    monkeypatch.setattr(invoice_email_service, "SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr(invoice_email_service, "SMTP_PORT", 587)
    monkeypatch.setattr(invoice_email_service, "SMTP_USER", "no-reply@example.test")
    monkeypatch.setattr(invoice_email_service, "SMTP_PASSWORD", "dummy-secret")
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            assert host == "smtp.example.test"
            assert port == 587
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def ehlo(self): return None
        def starttls(self, context=None): return None
        def login(self, username, password):
            assert username == "no-reply@example.test"
        def send_message(self, message):
            sent["message"] = message
            return {}

    monkeypatch.setattr(invoice_email_service.smtplib, "SMTP", FakeSMTP)
    ok, message = invoice_email_service.kirim_email_tagihan_bulanan(
        "rafli@example.test", "Rafli Wijaya", "IPA SMA", invoice_data
    )
    assert ok, message
    email = sent["message"]
    assert "Tagihan Bulanan" in email["Subject"]
    html_part = email.get_body(preferencelist=("html",))
    assert html_part is not None
    assert "TAGIHAN BULANAN BARU" in html_part.get_content()
    assert "simulasi internal" in html_part.get_content().lower()
    attachments = list(email.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/pdf"
