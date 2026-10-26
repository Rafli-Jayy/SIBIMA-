"""Otorisasi dan validasi pengumuman global SIBIMA."""

import psycopg

from app import session
from app.repositories import engagement_repo, user_repo


def _pengguna_aktif(role: str) -> dict:
    pengguna = session.get_user() or {}
    if pengguna.get("role") != role or type(pengguna.get("id")) is not int:
        raise PermissionError(f"Fitur ini hanya untuk {role} aktif.")
    aktual = user_repo.cari_by_id(pengguna["id"])
    if not aktual or aktual.get("role") != role or aktual.get("status") != "aktif":
        raise PermissionError(f"Akun {role} tidak aktif atau sesi tidak valid.")
    return aktual


def buat_pengumuman(judul: str, isi: str) -> dict:
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
    return engagement_repo.buat_pengumuman(judul, isi, admin["id"])


def daftar_pengumuman_admin(limit: int = 100) -> list[dict]:
    _pengguna_aktif("admin")
    return engagement_repo.daftar_pengumuman(limit)


def pengumuman_terbaru_siswa(limit: int = 3) -> list[dict]:
    _pengguna_aktif("siswa")
    return engagement_repo.pengumuman_terbaru(limit)
