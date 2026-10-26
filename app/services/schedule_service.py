"""Aturan bisnis pengelolaan jadwal oleh admin."""

from datetime import datetime, time
import re

import psycopg

from app import session
from app.repositories import schedule_repo, user_repo

_HARI = set(schedule_repo.HARI_VALID)


def _admin_aktif():
    pengguna = session.get_user()
    if not pengguna or pengguna.get("role") != "admin":
        return None
    user_id = pengguna.get("id")
    if type(user_id) is not int or user_id <= 0:
        return None
    try:
        admin = user_repo.cari_by_id(user_id)
    except psycopg.Error:
        return None
    if not admin or admin.get("role") != "admin" or admin.get("status") != "aktif":
        return None
    return admin


def _id_positif(value, label="ID"):
    if type(value) is int:
        angka = value
    elif isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        angka = int(value.strip())
    else:
        raise ValueError(f"{label} harus berupa ID angka bulat.")
    if angka <= 0:
        raise ValueError(f"{label} harus lebih besar dari nol.")
    return angka


def _hari(value):
    if not isinstance(value, str):
        raise ValueError("Hari jadwal tidak valid.")
    hasil = value.strip().lower()
    if hasil not in _HARI:
        raise ValueError("Hari harus dipilih dari Senin sampai Minggu.")
    return hasil


def _jam(value, label):
    if isinstance(value, time):
        if value.tzinfo is not None:
            raise ValueError(f"{label} tidak boleh memakai zona waktu.")
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,2}:\d{2}", value.strip()):
        raise ValueError(f"{label} harus menggunakan format HH:MM, contoh 15:30.")
    try:
        return datetime.strptime(value.strip(), "%H:%M").time()
    except ValueError:
        raise ValueError(f"{label} bukan waktu yang valid.") from None


def _opsi_ada(daftar, item_id):
    return any(item.get("id") == item_id for item in daftar)


def _cek_referensi_aktif(data, current=None):
    """Pastikan pilihan baru aktif; referensi lama yang tidak berubah tetap boleh."""
    try:
        pilihan = {
            "program_id": schedule_repo.daftar_opsi_program(aktif_saja=True),
            "tutor_id": schedule_repo.daftar_opsi_tutor(aktif_saja=True),
            "room_id": schedule_repo.daftar_opsi_ruang(aktif_saja=True),
        }
        label = {"program_id": "Program terbuka", "tutor_id": "Tutor aktif", "room_id": "Ruang aktif"}
        for key, daftar in pilihan.items():
            identitas = data[key]
            if current is not None and current.get(key) == identitas:
                continue
            if not _opsi_ada(daftar, identitas):
                raise ValueError(f"{label[key]} yang dipilih tidak tersedia.")
        return True, "Valid."
    except ValueError as exc:
        return False, str(exc)


def opsi_program(aktif_saja=True):
    if _admin_aktif() is None:
        return False, "Akses ditolak."
    try:
        return True, schedule_repo.daftar_opsi_program(aktif_saja=aktif_saja)
    except psycopg.Error as exc:
        return False, f"Gagal membaca program ({type(exc).__name__})."


def opsi_tutor(aktif_saja=True):
    if _admin_aktif() is None:
        return False, "Akses ditolak."
    try:
        return True, schedule_repo.daftar_opsi_tutor(aktif_saja=aktif_saja)
    except psycopg.Error as exc:
        return False, f"Gagal membaca tutor ({type(exc).__name__})."


def opsi_ruang(aktif_saja=True):
    if _admin_aktif() is None:
        return False, "Akses ditolak."
    try:
        return True, schedule_repo.daftar_opsi_ruang(aktif_saja=aktif_saja)
    except psycopg.Error as exc:
        return False, f"Gagal membaca ruang ({type(exc).__name__})."


def daftar_jadwal(*, program_id=None, tutor_id=None, room_id=None, hari=None, aktif=None):
    if _admin_aktif() is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat melihat jadwal."
    try:
        if program_id is not None:
            program_id = _id_positif(program_id, "Program")
        if tutor_id is not None:
            tutor_id = _id_positif(tutor_id, "Tutor")
        if room_id is not None:
            room_id = _id_positif(room_id, "Ruang")
        if hari is not None:
            hari = _hari(hari)
        if aktif is not None and type(aktif) is not bool:
            raise ValueError("Filter status aktif tidak valid.")
        return True, schedule_repo.daftar_jadwal(
            program_id=program_id, tutor_id=tutor_id, room_id=room_id, hari=hari, aktif=aktif
        )
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Gagal membaca jadwal ({type(exc).__name__})."


def detail_jadwal(jadwal_id):
    if _admin_aktif() is None:
        return False, "Akses ditolak."
    try:
        jadwal_id = _id_positif(jadwal_id, "ID jadwal")
        item = schedule_repo.ambil_jadwal(jadwal_id)
        if item is None:
            return False, "Jadwal tidak ditemukan."
        return True, item
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Gagal membaca detail jadwal ({type(exc).__name__})."


def _validasi_data(data, current=None):
    if not isinstance(data, dict):
        raise ValueError("Data jadwal tidak valid.")
    semua = {
        "program_id": _id_positif(data.get("program_id"), "Program"),
        "tutor_id": _id_positif(data.get("tutor_id"), "Tutor"),
        "room_id": _id_positif(data.get("room_id"), "Ruang"),
        "hari": _hari(data.get("hari")),
        "jam_mulai": _jam(data.get("jam_mulai"), "Jam mulai"),
        "jam_selesai": _jam(data.get("jam_selesai"), "Jam selesai"),
    }
    if semua["jam_mulai"] >= semua["jam_selesai"]:
        raise ValueError("Jam selesai harus lebih besar dari jam mulai.")
    referensi_ok, pesan = _cek_referensi_aktif(semua, current=current)
    if not referensi_ok:
        raise ValueError(pesan)
    return semua


def _pesan_bentrok(item):
    if not item:
        return None
    mulai = item["jam_mulai"].strftime("%H:%M")
    selesai = item["jam_selesai"].strftime("%H:%M")
    if item["jenis"] == "tutor":
        return f"Jadwal bentrok dengan tutor pada jadwal ID {item['id']} ({item['nama_program']}, {mulai}-{selesai})."
    return f"Ruang bentrok dengan jadwal ID {item['id']} ({item['nama_program']}, {mulai}-{selesai})."


def buat_jadwal(data: dict):
    admin = _admin_aktif()
    if admin is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat membuat jadwal."
    try:
        jadwal = _validasi_data(data)
        bentrok = schedule_repo.cek_bentrok(
            tutor_id=jadwal["tutor_id"], room_id=jadwal["room_id"],
            hari=jadwal["hari"], jam_mulai=jadwal["jam_mulai"],
            jam_selesai=jadwal["jam_selesai"],
        )
        pesan = _pesan_bentrok(bentrok)
        if pesan:
            return False, pesan
        jadwal_id = schedule_repo.buat_jadwal(**jadwal, admin_id=admin["id"])
        return True, f"Jadwal berhasil dibuat dengan ID {jadwal_id}."
    except ValueError as exc:
        return False, str(exc)
    except psycopg.errors.ExclusionViolation as exc:
        if getattr(exc, "diag", None) and exc.diag.constraint_name == "ex_bentrok_tutor":
            return False, "Jadwal bentrok: tutor sudah mengajar pada hari dan waktu tersebut."
        if getattr(exc, "diag", None) and exc.diag.constraint_name == "ex_bentrok_ruang":
            return False, "Jadwal bentrok: ruang sudah digunakan pada hari dan waktu tersebut."
        return False, "Jadwal bertabrakan dengan jadwal aktif lainnya."
    except psycopg.errors.ForeignKeyViolation:
        return False, "Program, tutor, atau ruang tidak lagi tersedia. Muat ulang pilihan."
    except psycopg.Error as exc:
        return False, f"Gagal menyimpan jadwal ({type(exc).__name__})."


def ubah_jadwal(jadwal_id: int, data: dict):
    admin = _admin_aktif()
    if admin is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat mengubah jadwal."
    try:
        jadwal_id = _id_positif(jadwal_id, "ID jadwal")
        current = schedule_repo.ambil_jadwal(jadwal_id)
        if current is None:
            return False, "Jadwal tidak ditemukan."
        if not current["aktif"]:
            return False, "Jadwal sudah nonaktif dan tidak dapat diubah."
        if schedule_repo.ada_riwayat_pertemuan(jadwal_id):
            return False, (
                "Jadwal ini sudah memiliki riwayat pertemuan. Untuk menjaga riwayat "
                "tetap akurat, nonaktifkan jadwal lama lalu buat jadwal baru."
            )
        if not isinstance(data, dict) or not data:
            return False, "Pilih minimal satu data yang akan diubah."
        unknown = set(data) - {"program_id", "tutor_id", "room_id", "hari", "jam_mulai", "jam_selesai"}
        if unknown:
            return False, "Bidang perubahan jadwal tidak dikenal."
        merged = {
            "program_id": data.get("program_id", current["program_id"]),
            "tutor_id": data.get("tutor_id", current["tutor_id"]),
            "room_id": data.get("room_id", current["room_id"]),
            "hari": data.get("hari", current["hari"]),
            "jam_mulai": data.get("jam_mulai", current["jam_mulai"]),
            "jam_selesai": data.get("jam_selesai", current["jam_selesai"]),
        }
        valid = _validasi_data(merged, current=current)
        bentrok = schedule_repo.cek_bentrok(
            tutor_id=valid["tutor_id"], room_id=valid["room_id"],
            hari=valid["hari"], jam_mulai=valid["jam_mulai"],
            jam_selesai=valid["jam_selesai"], kecuali_id=jadwal_id,
        )
        pesan = _pesan_bentrok(bentrok)
        if pesan:
            return False, pesan
        # Kirim hanya kolom yang diminta, yang sudah dinormalisasi dan tervalidasi.
        update = {key: valid[key] for key in data}
        berhasil = schedule_repo.ubah_jadwal(jadwal_id, data=update, admin_id=admin["id"])
        if not berhasil:
            return False, "Jadwal tidak ditemukan atau sudah dinonaktifkan."
        return True, f"Jadwal ID {jadwal_id} berhasil diperbarui."
    except ValueError as exc:
        return False, str(exc)
    except psycopg.errors.ExclusionViolation as exc:
        if getattr(exc, "diag", None) and exc.diag.constraint_name == "ex_bentrok_tutor":
            return False, "Perubahan ditolak: tutor bentrok dengan jadwal aktif lain."
        if getattr(exc, "diag", None) and exc.diag.constraint_name == "ex_bentrok_ruang":
            return False, "Perubahan ditolak: ruang bentrok dengan jadwal aktif lain."
        return False, "Perubahan jadwal menyebabkan bentrok."
    except psycopg.errors.ForeignKeyViolation:
        return False, "Program, tutor, atau ruang tidak lagi tersedia. Muat ulang pilihan."
    except psycopg.Error as exc:
        return False, f"Gagal mengubah jadwal ({type(exc).__name__})."


def nonaktifkan_jadwal(jadwal_id: int):
    admin = _admin_aktif()
    if admin is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat menonaktifkan jadwal."
    try:
        jadwal_id = _id_positif(jadwal_id, "ID jadwal")
        berhasil = schedule_repo.nonaktifkan_jadwal(jadwal_id, admin_id=admin["id"])
        if not berhasil:
            return False, "Jadwal tidak ditemukan atau sudah nonaktif."
        return True, f"Jadwal ID {jadwal_id} berhasil dinonaktifkan. Riwayat pertemuan tetap disimpan."
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Gagal menonaktifkan jadwal ({type(exc).__name__})."
