"""Regresi pemindahan program: status kelas tujuan mengikuti kewajiban bulan berjalan.

Cursor dan pool diganti fake agar transaksi SQL tidak menyentuh database pengguna.
"""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.repositories import enrollment_repo


class _Cursor:
    def __init__(self, *, invoice_status="belum_dibayar", target_fee=Decimal("175000"),
                 source_status="aktif", target_status="buka", occupied=0, quota=10,
                 previous_target=False, source_found=True):
        self.invoice_status = invoice_status
        self.target_fee = target_fee
        self.source_status = source_status
        self.target_status = target_status
        self.occupied = occupied
        self.quota = quota
        self.previous_target = previous_target
        self.source_found = source_found
        self.record = None
        self.sql = []
        self.new_status = None
        self.old_ended = False
        self.old_invoice_canceled = False
        self.payment_attempts_rejected = False
        self.log_written = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        text = " ".join(query.lower().split())
        self.sql.append((text, params))
        if "from enrollments e join programs p" in text and "for update of e" in text:
            self.record = ({"id": 9, "student_id": 22, "program_id": 3,
                            "status": self.source_status, "nama_program_asal": "Program Asal"}
                           if self.source_found else None)
        elif "from programs where id = %s for update" in text:
            self.record = {"id": 8, "kode": "TUJUAN", "nama": "Program Tujuan",
                           "status": self.target_status, "kuota": self.quota,
                           "harga_bulanan": self.target_fee}
        elif "select count(*) as jumlah from enrollments" in text:
            self.record = {"jumlah": self.occupied}
        elif "select id, status from enrollments" in text:
            self.record = {"id": 15, "status": "selesai"} if self.previous_target else None
        elif "select id, status from invoices" in text:
            self.record = ({"id": 51, "status": self.invoice_status}
                           if self.invoice_status is not None else None)
        elif text.startswith("update payments"):
            self.payment_attempts_rejected = True
        elif text.startswith("update invoices set status = 'batal'"):
            self.old_invoice_canceled = True
        elif text.startswith("insert into enrollments"):
            self.new_status = params[2]
            self.record = {"id": 99}
        elif text.startswith("update enrollments set status = 'selesai'"):
            self.old_ended = True
        elif text.startswith("insert into activity_logs"):
            self.log_written = True
        else:
            raise AssertionError(f"Query tak dikenali dalam fake cursor: {text[:120]}")

    def fetchone(self):
        return self.record


class _Connection:
    def __init__(self, cursor):
        self.cur = cursor
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self, **_kwargs):
        return self.cur

    def commit(self):
        self.commits += 1


def _run_transfer(monkeypatch, **options):
    cur = _Cursor(**options)
    conn = _Connection(cur)
    create_invoice = Mock(return_value={"id": 70, "no_invoice": "INV-TEST",
                                            "jumlah": options.get("target_fee", Decimal("175000")),
                                            "status": "belum_dibayar"})
    monkeypatch.setattr(enrollment_repo, "pool", Mock(connection=lambda: conn))
    monkeypatch.setattr(enrollment_repo, "buat_invoice_awal", create_invoice)
    # Function currently performs its own local import of this function.
    from app.repositories import billing_repo
    monkeypatch.setattr(billing_repo, "buat_invoice_awal", create_invoice)
    result = enrollment_repo.pindahkan_admin(9, 8, 5)
    return result, cur, conn, create_invoice


@pytest.mark.parametrize("invoice_status", ["belum_dibayar", None, "batal"])
def test_paid_target_without_paid_period_stays_locked(monkeypatch, invoice_status):
    result, cur, conn, make_invoice = _run_transfer(monkeypatch, invoice_status=invoice_status)
    assert result["berhasil"] is True
    assert result["status_baru"] == "menunggu_pembayaran"
    assert cur.new_status == "menunggu_pembayaran"
    assert result["invoice"]["status"] == "belum_dibayar"
    assert make_invoice.call_count == 1
    assert make_invoice.call_args.args[1] == 99
    assert cur.old_ended and cur.log_written and conn.commits == 1
    assert "menunggu pembayaran" in result["pesan"].lower()


def test_paid_source_month_does_not_double_charge(monkeypatch):
    result, cur, conn, make_invoice = _run_transfer(monkeypatch, invoice_status="lunas")
    assert result["berhasil"] is True
    assert result["status_baru"] == "aktif"
    assert cur.new_status == "aktif"
    assert result["invoice"] is None
    assert not cur.old_invoice_canceled
    assert not cur.payment_attempts_rejected
    assert make_invoice.call_count == 0
    assert conn.commits == 1


def test_target_free_is_active_without_new_invoice(monkeypatch):
    result, cur, conn, make_invoice = _run_transfer(
        monkeypatch, invoice_status="belum_dibayar", target_fee=Decimal("0"))
    assert result["berhasil"] is True
    assert result["status_baru"] == "aktif"
    assert result["invoice"] is None
    assert cur.old_invoice_canceled
    assert cur.payment_attempts_rejected
    assert make_invoice.call_count == 0
    assert conn.commits == 1


def test_unpaid_source_invoice_canceled_but_historical_paid_unchanged(monkeypatch):
    _, cur, _, _ = _run_transfer(monkeypatch, invoice_status="belum_dibayar")
    assert cur.old_invoice_canceled is True
    assert cur.payment_attempts_rejected is True
    assert any("where id = %s and status <> 'lunas'" in q for q, _ in cur.sql)


@pytest.mark.parametrize("options,expected", [
    ({"source_found": False}, "tidak ditemukan"),
    ({"source_status": "menunggu"}, "berstatus aktif"),
    ({"target_status": "tutup"}, "ditutup"),
    ({"occupied": 10, "quota": 10}, "kuota"),
    ({"previous_target": True}, "riwayat"),
])
def test_invalid_transfer_no_write(monkeypatch, options, expected):
    result, cur, conn, make_invoice = _run_transfer(monkeypatch, **options)
    assert result["berhasil"] is False
    assert expected in result["pesan"].lower()
    assert cur.new_status is None
    assert make_invoice.call_count == 0
    assert conn.commits == 0


@pytest.mark.parametrize("key", ["enrollment_id", "program_tujuan_id", "processed_by"])
def test_invalid_ids_rejected_before_transaction(monkeypatch, key):
    arguments = dict(enrollment_id=9, program_tujuan_id=8, processed_by=5)
    arguments[key] = 0
    monkeypatch.setattr(enrollment_repo, "pool", Mock(connection=Mock(side_effect=AssertionError("No DB"))))
    with pytest.raises(ValueError):
        enrollment_repo.pindahkan_admin(**arguments)


def test_failed_invoice_create_does_not_commit(monkeypatch):
    cur = _Cursor(invoice_status="belum_dibayar")
    conn = _Connection(cur)
    monkeypatch.setattr(enrollment_repo, "pool", Mock(connection=lambda: conn))
    from app.repositories import billing_repo
    monkeypatch.setattr(billing_repo, "buat_invoice_awal", Mock(side_effect=RuntimeError("Invoice gagal")))
    with pytest.raises(RuntimeError, match="Invoice gagal"):
        enrollment_repo.pindahkan_admin(9, 8, 5)
    assert conn.commits == 0


def test_missing_required_invoice_rolls_back_before_commit(monkeypatch):
    cur = _Cursor(invoice_status=None)
    conn = _Connection(cur)
    monkeypatch.setattr(enrollment_repo, "pool", Mock(connection=lambda: conn))
    from app.repositories import billing_repo
    monkeypatch.setattr(billing_repo, "buat_invoice_awal", Mock(return_value=None))
    with pytest.raises(RuntimeError, match="Tagihan program tujuan gagal dibuat"):
        enrollment_repo.pindahkan_admin(9, 8, 5)
    assert cur.new_status == "menunggu_pembayaran"
    assert conn.commits == 0
