"""Unit test validasi layanan pengumuman PATCH-001A."""

import pytest

from app.services import engagement_service


def _admin_aktif(monkeypatch):
    monkeypatch.setattr(
        engagement_service,
        "_pengguna_aktif",
        lambda role: {"id": 7, "role": role, "status": "aktif"},
    )


def test_buat_pengumuman_meneruskan_target_role(monkeypatch):
    _admin_aktif(monkeypatch)
    tersimpan = {}

    def fake_buat(judul, isi, admin_id, target_roles):
        tersimpan.update(judul=judul, isi=isi, admin_id=admin_id, target_roles=target_roles)
        return {"id": 10, **tersimpan}

    monkeypatch.setattr(engagement_service.engagement_repo, "buat_pengumuman", fake_buat)
    hasil = engagement_service.buat_pengumuman("  Info kelas  ", "  Jadwal baru  ", ["siswa", "tutor"])

    assert hasil["id"] == 10
    assert tersimpan == {
        "judul": "Info kelas",
        "isi": "Jadwal baru",
        "admin_id": 7,
        "target_roles": ["siswa", "tutor"],
    }


def test_buat_pengumuman_wajib_pilih_penerima(monkeypatch):
    _admin_aktif(monkeypatch)
    with pytest.raises(ValueError, match="minimal satu penerima"):
        engagement_service.buat_pengumuman("Info", "Isi", [])


@pytest.mark.parametrize("targets", [["admin"], ["siswa", "admin"], [1], [None]])
def test_buat_pengumuman_menolak_target_tidak_valid(monkeypatch, targets):
    _admin_aktif(monkeypatch)
    with pytest.raises(ValueError, match="hanya boleh Siswa"):
        engagement_service.buat_pengumuman("Info", "Isi", targets)


def test_buat_pengumuman_menghapus_target_duplikat(monkeypatch):
    _admin_aktif(monkeypatch)
    captured = {}

    def fake_buat(judul, isi, admin_id, target_roles):
        captured["roles"] = target_roles
        return {"id": 11}

    monkeypatch.setattr(engagement_service.engagement_repo, "buat_pengumuman", fake_buat)
    engagement_service.buat_pengumuman("Info", "Isi", ["siswa", "siswa"])
    assert captured["roles"] == ["siswa"]
