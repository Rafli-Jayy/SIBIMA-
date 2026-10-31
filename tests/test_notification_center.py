"""Pengujian layanan pusat notifikasi PATCH-002A1."""

import pytest

from app.services import engagement_service


def _aktif(monkeypatch, role="siswa", user_id=23):
    monkeypatch.setattr(
        engagement_service, "_pengguna_aktif",
        lambda expected_role: {"id": user_id, "role": expected_role, "status": "aktif"},
    )


def test_jumlah_notifikasi_meneruskan_user_dan_role(monkeypatch):
    _aktif(monkeypatch, "siswa", 23)
    captured = {}

    def fake_count(user_id, role):
        captured.update(user_id=user_id, role=role)
        return 4

    monkeypatch.setattr(engagement_service.engagement_repo, "jumlah_notifikasi_belum_dibaca", fake_count)
    assert engagement_service.jumlah_notifikasi_belum_dibaca("siswa") == 4
    assert captured == {"user_id": 23, "role": "siswa"}


def test_daftar_notifikasi_meneruskan_user_dan_role(monkeypatch):
    _aktif(monkeypatch, "tutor", 31)
    captured = {}

    def fake_list(user_id, role, limit):
        captured.update(user_id=user_id, role=role, limit=limit)
        return [{"id": 1, "sudah_dibaca": False}]

    monkeypatch.setattr(engagement_service.engagement_repo, "daftar_notifikasi_penerima", fake_list)
    hasil = engagement_service.daftar_notifikasi("tutor", limit=25)
    assert hasil[0]["id"] == 1
    assert captured == {"user_id": 31, "role": "tutor", "limit": 25}


def test_buka_notifikasi_menolak_id_tidak_valid(monkeypatch):
    _aktif(monkeypatch)
    with pytest.raises(ValueError, match="ID notifikasi tidak valid"):
        engagement_service.buka_notifikasi("siswa", 0)
