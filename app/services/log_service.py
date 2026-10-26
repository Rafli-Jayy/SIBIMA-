"""Otorisasi admin untuk membaca log aktivitas."""

from app import session
from app.repositories import log_repo, user_repo


def _admin_aktif() -> dict:
    pengguna = session.get_user() or {}
    if pengguna.get("role") != "admin" or type(pengguna.get("id")) is not int:
        raise PermissionError("Log aktivitas hanya dapat dilihat admin aktif.")
    admin = user_repo.cari_by_id(pengguna["id"])
    if not admin or admin.get("role") != "admin" or admin.get("status") != "aktif":
        raise PermissionError("Akun admin tidak aktif atau sesi tidak valid.")
    return admin


def aktivitas_terbaru(limit: int = 100) -> list[dict]:
    _admin_aktif()
    return log_repo.daftar_terbaru(limit=limit)


def filter_aktivitas(pengguna: str | None = None, aksi: str | None = None,
                     limit: int = 200) -> list[dict]:
    _admin_aktif()
    if pengguna is not None and not isinstance(pengguna, str):
        raise ValueError("Filter pengguna harus berupa teks.")
    if aksi is not None and not isinstance(aksi, str):
        raise ValueError("Filter aksi harus berupa teks.")
    pengguna = pengguna.strip() if pengguna else None
    aksi = aksi.strip() if aksi else None
    return log_repo.daftar_terbaru(limit=limit, pengguna=pengguna or None, aksi=aksi or None)
