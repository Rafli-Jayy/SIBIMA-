"""Otorisasi dan validasi pengumuman SIBIMA."""

from app import session
from app.repositories import engagement_repo, user_repo


_ROLE_PENERIMA = {"siswa", "tutor"}


def _pengguna_aktif(role: str) -> dict:
    pengguna = session.get_user() or {}
    if pengguna.get("role") != role or type(pengguna.get("id")) is not int:
        raise PermissionError(f"Fitur ini hanya untuk {role} aktif.")
    aktual = user_repo.cari_by_id(pengguna["id"])
    if not aktual or aktual.get("role") != role or aktual.get("status") != "aktif":
        raise PermissionError(f"Akun {role} tidak aktif atau sesi tidak valid.")
    return aktual


def buat_pengumuman(judul: str, isi: str, target_roles: list[str]) -> dict:
    admin = _pengguna_aktif("admin")
    if not isinstance(judul, str):
        raise ValueError("Judul pengumuman harus berupa teks.")
    if not isinstance(isi, str):
        raise ValueError("Isi pengumuman harus berupa teks.")
    judul = judul.strip()
    isi = isi.strip()
    if not judul:
        raise ValueError("Judul pengumuman wajib diisi.")
    if len(judul) > 150:
        raise ValueError("Judul maksimal 150 karakter.")
    if not isi:
        raise ValueError("Isi pengumuman wajib diisi.")
    if len(isi) > 10000:
        raise ValueError("Isi pengumuman maksimal 10.000 karakter.")
    if not isinstance(target_roles, (list, tuple, set)):
        raise ValueError("Penerima pengumuman tidak valid.")
    if any(not isinstance(role, str) or role not in _ROLE_PENERIMA for role in target_roles):
        raise ValueError("Penerima hanya boleh Siswa dan/atau Tutor.")
    roles = list(dict.fromkeys(target_roles))
    if not roles:
        raise ValueError("Pilih minimal satu penerima: Siswa atau Tutor.")
    return engagement_repo.buat_pengumuman(judul, isi, admin["id"], roles)


def daftar_pengumuman_admin(status: str = "aktif", limit: int = 100) -> list[dict]:
    _pengguna_aktif("admin")
    if status not in {"aktif", "arsip"}:
        raise ValueError("Status daftar pengumuman tidak valid.")
    return engagement_repo.daftar_pengumuman_admin(status=status, limit=limit)


def detail_pengumuman_admin(announcement_id: int) -> dict | None:
    _pengguna_aktif("admin")
    return engagement_repo.detail_pengumuman_admin(announcement_id)


def arsipkan_pengumuman_admin(announcement_id: int) -> None:
    admin = _pengguna_aktif("admin")
    if type(announcement_id) is not int or announcement_id < 1:
        raise ValueError("ID pengumuman tidak valid.")
    if not engagement_repo.arsipkan_pengumuman(announcement_id, admin["id"]):
        raise ValueError("Pengumuman tidak ditemukan atau sudah diarsipkan.")


def pengumuman_terbaru_siswa(limit: int = 3) -> list[dict]:
    _pengguna_aktif("siswa")
    return engagement_repo.pengumuman_terbaru_siswa(limit)


def daftar_notifikasi(role: str, limit: int = 200) -> list[dict]:
    """Daftar notifikasi aktif untuk akun siswa/tutor yang sedang login."""
    pengguna = _pengguna_aktif(role)
    if type(limit) is not int or limit < 1:
        raise ValueError("Batas notifikasi tidak valid.")
    return engagement_repo.daftar_notifikasi_penerima(pengguna["id"], role, limit)


def buka_notifikasi(role: str, announcement_id: int) -> dict:
    """Buka notifikasi milik peran ini dan catat status baca secara individual."""
    pengguna = _pengguna_aktif(role)
    if type(announcement_id) is not int or announcement_id < 1:
        raise ValueError("ID notifikasi tidak valid.")
    item = engagement_repo.detail_notifikasi_penerima(
        pengguna["id"], role, announcement_id
    )
    if item is None:
        raise ValueError("Notifikasi tidak ditemukan atau bukan untuk akun ini.")
    return item
