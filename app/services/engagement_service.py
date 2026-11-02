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
    """Daftar pengumuman aktif untuk akun siswa/tutor yang sedang login."""
    pengguna = _pengguna_aktif(role)
    if type(limit) is not int or limit < 1:
        raise ValueError("Batas notifikasi tidak valid.")
    return engagement_repo.daftar_notifikasi_penerima(pengguna["id"], role, limit)


def jumlah_notifikasi_belum_dibaca(role: str) -> int:
    """Hitung badge notifikasi pribadi untuk siswa atau tutor aktif."""
    pengguna = _pengguna_aktif(role)
    return engagement_repo.jumlah_notifikasi_belum_dibaca(pengguna["id"], role)


def buka_notifikasi(role: str, announcement_id: int) -> dict:
    """Buka notifikasi sesuai peran dan catat sudah dibaca untuk pengguna ini."""
    pengguna = _pengguna_aktif(role)
    if type(announcement_id) is not int or announcement_id < 1:
        raise ValueError("ID notifikasi tidak valid.")
    item = engagement_repo.detail_notifikasi_penerima(
        pengguna["id"], role, announcement_id
    )
    if item is None:
        raise ValueError("Notifikasi tidak ditemukan atau bukan untuk akun ini.")
    return item

# ----------------- PATCH-N2 -----------------
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.repositories import notification_sync_repo


def sinkronisasi_notifikasi(role: str) -> None:
    user=_pengguna_aktif(role)
    notification_sync_repo.sinkronisasi(user['id'],role)


def daftar_notifikasi_filter(role: str, *, arsip: bool = False,
                             kategori: str = 'semua', sumber: str = 'semua',
                             baca: str = 'semua', limit: int = 200) -> list[dict]:
    user=_pengguna_aktif(role)
    return engagement_repo.daftar_notifikasi_penerima(user['id'],role,limit,
        arsip=arsip,kategori=kategori,sumber=sumber,baca=baca)


def buka_notifikasi_arsip(role: str, announcement_id: int) -> dict:
    user=_pengguna_aktif(role)
    if type(announcement_id) is not int or announcement_id <= 0:
        raise ValueError('ID notifikasi tidak valid.')
    item=engagement_repo.detail_notifikasi_penerima(user['id'],role,announcement_id,arsip=True)
    if item is None:
        raise ValueError('Pesan arsip tidak ditemukan atau bukan milikmu.')
    return item


def arsipkan_notifikasi_pribadi(role: str, announcement_id: int) -> None:
    user=_pengguna_aktif(role)
    if not engagement_repo.arsipkan_notifikasi_pribadi(user['id'],role,announcement_id):
        raise ValueError('Notifikasi tidak ditemukan atau sudah tidak aktif.')


def tandai_semua_dibaca(role: str) -> int:
    user=_pengguna_aktif(role)
    return engagement_repo.tandai_semua_dibaca(user['id'],role)


def daftar_program_pengumuman_tutor() -> list[dict]:
    tutor=_pengguna_aktif('tutor')
    return engagement_repo.daftar_program_pengumuman_tutor(tutor['id'])


def buat_pengumuman_tutor(program_id: int, judul: str, isi: str,
                          durasi: str = '7_hari', tanggal_akhir: str | None = None) -> dict:
    tutor=_pengguna_aktif('tutor')
    if type(program_id) is not int or program_id <= 0:
        raise ValueError('Program kelas tidak valid.')
    if not isinstance(judul,str) or not 1 <= len(judul.strip()) <= 150:
        raise ValueError('Judul harus 1-150 karakter.')
    if not isinstance(isi,str) or not 1 <= len(isi.strip()) <= 10000:
        raise ValueError('Isi harus 1-10.000 karakter.')
    if durasi not in ('7_hari','pertemuan_berikut','tanggal'):
        raise ValueError('Masa berlaku tidak valid.')
    expires_custom=None
    if durasi=='tanggal':
        try:
            expires_custom=datetime.strptime(tanggal_akhir,'%Y-%m-%d %H:%M').replace(tzinfo=ZoneInfo('Asia/Jakarta'))
        except (TypeError,ValueError) as exc:
            raise ValueError('Format tanggal: YYYY-MM-DD HH:MM (WIB).') from exc
        now=datetime.now(ZoneInfo('Asia/Jakarta'))
        if not now < expires_custom <= now + timedelta(days=730):
            raise ValueError('Pilih masa berlaku dalam 2 tahun ke depan.')
    return engagement_repo.terbitkan_pengumuman_tutor(tutor['id'],program_id,
        judul.strip(),isi.strip(),durasi,expires_custom)


def daftar_pengumuman_tutor(status: str = 'aktif') -> list[dict]:
    tutor=_pengguna_aktif('tutor')
    return engagement_repo.daftar_pengumuman_tutor(tutor['id'],status)


def akhiri_pengumuman_tutor(batch_key: str) -> None:
    tutor=_pengguna_aktif('tutor')
    if not engagement_repo.akhiri_pengumuman_tutor(tutor['id'],batch_key):
        raise ValueError('Pengumuman tidak ditemukan, sudah berakhir, atau bukan milikmu.')


def daftar_pertemuan_tertunda_tutor(limit: int = 200) -> list[dict]:
    user=_pengguna_aktif('tutor')
    return notification_sync_repo.daftar_pertemuan_tertunda(user['id'],limit)


def buka_pertemuan_terlewat_tutor(schedule_id: int, tanggal) -> int:
    user=_pengguna_aktif('tutor')
    return notification_sync_repo.buka_pertemuan_terlewat(user['id'],schedule_id,tanggal)
