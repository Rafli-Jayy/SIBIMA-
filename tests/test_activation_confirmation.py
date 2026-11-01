"""PATCH-005A: PDF/email activation confirmation, no live DB or SMTP."""
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.services import activation_confirmation_service as confirmation
from app.services import approval_service as approval


def sample_detail(**changes):
    value = {
        "enrollment_id": 17,
        "status": "aktif",
        "nama_siswa": "Siswa Penguji",
        "email_siswa": "siswa@example.test",
        "nis": "SIB-2026-001",
        "nama_program": "Matematika Reguler",
        "processed_at": datetime(2026, 11, 1, 9, 30),
    }
    value.update(changes)
    return value


def setup_approval(monkeypatch, detail=None):
    detail = detail or sample_detail()
    monkeypatch.setattr(approval, "_admin_aktif", lambda: {"id": 5})
    decide = Mock(return_value={
        "berhasil": True, "student_id": 31, "nama_program": "Matematika Reguler"
    })
    monkeypatch.setattr(approval.enrollment_repo, "proses_keputusan_admin", decide)
    monkeypatch.setattr(approval.enrollment_repo, "detail_admin", Mock(return_value=detail))
    monkeypatch.setattr(approval.user_repo, "cari_by_id", Mock(return_value={
        "nama_lengkap": "Siswa Penguji", "email": "siswa@example.test"
    }))
    return decide


def test_pdf_is_generated_in_dedicated_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(confirmation, "BUKTI_DIR", tmp_path)
    pdf = confirmation.buat_pdf_konfirmasi_aktivasi(sample_detail())
    assert pdf.parent == tmp_path / "aktivasi"
    assert pdf.name == "Konfirmasi_Aktivasi_17.pdf"
    assert pdf.read_bytes().startswith(b"%PDF-")
    assert pdf.stat().st_size > 1000


@pytest.mark.parametrize("bad", [
    {"status": "menunggu"}, {"status": "batal"}, {"enrollment_id": -1},
    {"enrollment_id": True}, {"enrollment_id": "17"},
    {"processed_at": None}, {"nis": ""}, {"nama_siswa": ""},
    {"nama_program": ""},
])
def test_pdf_rejects_invalid_activation(tmp_path, monkeypatch, bad):
    monkeypatch.setattr(confirmation, "BUKTI_DIR", tmp_path)
    with pytest.raises(ValueError):
        confirmation.buat_pdf_konfirmasi_aktivasi(sample_detail(**bad))
    assert not (tmp_path / "aktivasi").exists()


def test_pdf_escapes_untrusted_student_and_program(tmp_path, monkeypatch):
    monkeypatch.setattr(confirmation, "BUKTI_DIR", tmp_path)
    pdf = confirmation.buat_pdf_konfirmasi_aktivasi(sample_detail(
        nama_siswa="<b>COBA</b>& Nama", nama_program="<font color='red'>Bahaya</font>"
    ))
    assert pdf.read_bytes().startswith(b"%PDF-")


def test_pdf_generation_error_does_not_change_db_state(monkeypatch):
    setup_approval(monkeypatch)
    monkeypatch.setattr(confirmation, "buat_pdf_konfirmasi_aktivasi", Mock(side_effect=OSError("disk full")))
    ok, message = approval.setujui_enrollment(17)
    assert ok and "tetap aktif" in message and "OSError" in message


def test_success_sends_one_attachment_not_plain_notification(monkeypatch):
    decide = setup_approval(monkeypatch)
    generator = Mock(return_value=Path("/tmp/confirm.pdf"))
    send = Mock(return_value=(True, "sent"))
    monkeypatch.setattr(confirmation, "buat_pdf_konfirmasi_aktivasi", generator)
    monkeypatch.setattr(confirmation, "kirim_pdf_konfirmasi_aktivasi", send)
    plain = Mock(side_effect=AssertionError("old plain email should not run"))
    monkeypatch.setattr(approval.email_service, "kirim_notifikasi_status", plain)
    ok, message = approval.setujui_enrollment(17)
    assert ok and "PDF konfirmasi aktivasi dikirim" in message
    data = generator.call_args.args[0]
    assert data["nis"] == "SIB-2026-001"
    assert data["processed_at"] == datetime(2026, 11, 1, 9, 30)
    assert send.call_args.args[1] == Path("/tmp/confirm.pdf")
    assert decide.call_count == 1
    assert not plain.called


def test_email_failed_still_active_and_pdf_saved(monkeypatch):
    setup_approval(monkeypatch)
    monkeypatch.setattr(confirmation, "buat_pdf_konfirmasi_aktivasi", Mock(return_value=Path("/tmp/confirm.pdf")))
    monkeypatch.setattr(confirmation, "kirim_pdf_konfirmasi_aktivasi", Mock(return_value=(False, "SMTP ditolak")))
    ok, message = approval.setujui_enrollment(17)
    assert ok and "PDF tersimpan" in message and "SMTP ditolak" in message


def test_missing_email_user_does_not_fail_approval(monkeypatch):
    setup_approval(monkeypatch)
    monkeypatch.setattr(approval.user_repo, "cari_by_id", lambda _: None)
    ok, message = approval.setujui_enrollment(17)
    assert ok and "Data email siswa tidak ditemukan" in message


def test_detail_lookup_failed_does_not_fail_approval(monkeypatch):
    setup_approval(monkeypatch)
    monkeypatch.setattr(approval.enrollment_repo, "detail_admin", Mock(side_effect=RuntimeError("connection")))
    ok, message = approval.setujui_enrollment(17)
    assert ok and "tetap aktif" in message


def test_detail_status_changed_does_not_send_activation(monkeypatch):
    setup_approval(monkeypatch, sample_detail(status="batal"))
    send = Mock(side_effect=AssertionError("not allowed"))
    monkeypatch.setattr(confirmation, "kirim_pdf_konfirmasi_aktivasi", send)
    ok, message = approval.setujui_enrollment(17)
    assert ok and "Detail aktivasi tidak tersedia" in message
    assert not send.called


def test_approval_refused_does_not_generate_documents(monkeypatch):
    monkeypatch.setattr(approval, "_admin_aktif", lambda: {"id": 5})
    monkeypatch.setattr(approval.enrollment_repo, "proses_keputusan_admin", Mock(return_value={"berhasil": False, "pesan": "belum lunas"}))
    generator = Mock(side_effect=AssertionError("not allowed"))
    monkeypatch.setattr(confirmation, "buat_pdf_konfirmasi_aktivasi", generator)
    ok, message = approval.setujui_enrollment(17)
    assert not ok and "belum lunas" in message and not generator.called


def test_invalid_admin_denied_before_db(monkeypatch):
    monkeypatch.setattr(approval, "_admin_aktif", lambda: None)
    called = Mock(side_effect=AssertionError("DB should not be called"))
    monkeypatch.setattr(approval.enrollment_repo, "proses_keputusan_admin", called)
    ok, message = approval.setujui_enrollment(17)
    assert not ok and "Akses ditolak" in message and not called.called


def test_email_smtp_with_pdf_attachment(tmp_path, monkeypatch):
    path = tmp_path / "confirm.pdf"
    path.write_bytes(b"%PDF-1.4\nFAKE PDF bytes\n")
    monkeypatch.setattr(confirmation, "SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr(confirmation, "SMTP_PORT", 587)
    monkeypatch.setattr(confirmation, "SMTP_USER", "test@example.test")
    monkeypatch.setattr(confirmation, "SMTP_PASSWORD", "secret")
    captured = {}
    class FakeSMTP:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def ehlo(self): pass
        def starttls(self, **kw): pass
        def login(self, *args): pass
        def send_message(self, message):
            captured["message"] = message
            return {}
    monkeypatch.setattr(confirmation.smtplib, "SMTP", FakeSMTP)
    ok, message = confirmation.kirim_pdf_konfirmasi_aktivasi(sample_detail(), path)
    assert ok, message
    mail = captured["message"]
    assert mail["To"] == "siswa@example.test"
    assert "Aktivasi" in mail["Subject"]
    assert len(list(mail.iter_attachments())) == 1
    attached = next(mail.iter_attachments())
    assert attached.get_content_type() == "application/pdf"
    assert attached.get_filename() == "confirm.pdf"
    assert "Matematika Reguler" in mail.get_body(preferencelist=("plain",)).get_content()
    assert "KELAS AKTIF" in mail.get_body(preferencelist=("html",)).get_content()


@pytest.mark.parametrize("email", ["", "a\r\nb@example.test", "not-an-email", "someone@example.test,other@example.test"])
def test_email_rejects_bad_addresses(tmp_path, monkeypatch, email):
    path = tmp_path / "confirm.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    ok, message = confirmation.kirim_pdf_konfirmasi_aktivasi(sample_detail(email_siswa=email), path)
    assert not ok and "email" in message.lower()


def test_email_missing_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(confirmation, "SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr(confirmation, "SMTP_PORT", 587)
    monkeypatch.setattr(confirmation, "SMTP_USER", "test@example.test")
    monkeypatch.setattr(confirmation, "SMTP_PASSWORD", "secret")
    ok, message = confirmation.kirim_pdf_konfirmasi_aktivasi(sample_detail(), tmp_path / "missing.pdf")
    assert not ok and "tidak ditemukan" in message


def test_email_smtp_error_returns_false(tmp_path, monkeypatch):
    path = tmp_path / "confirm.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    for key, val in {"SMTP_HOST":"smtp.example.test", "SMTP_PORT":587, "SMTP_USER":"test@example.test", "SMTP_PASSWORD":"secret"}.items():
        monkeypatch.setattr(confirmation, key, val)
    class FakeSMTP:
        def __init__(self, *a, **kw): raise OSError("offline")
    monkeypatch.setattr(confirmation.smtplib, "SMTP", FakeSMTP)
    ok, message = confirmation.kirim_pdf_konfirmasi_aktivasi(sample_detail(), path)
    assert not ok and "PDF tetap tersimpan" in message
