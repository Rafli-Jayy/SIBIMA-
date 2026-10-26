"""Aturan bisnis untuk pengelolaan program dan ruang oleh admin."""

from decimal import Decimal, InvalidOperation
import re

import psycopg

from app import session
from app.repositories import program_repo, user_repo

_BOBOT = ("bobot_tugas", "bobot_kuis", "bobot_uts", "bobot_uas")
_KOLOM_PROGRAM = {
    "kode", "nama", "jenjang", "deskripsi", "harga_bulanan", "kuota",
    "status", *_BOBOT,
}


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


def _teks(value, nama, batas, wajib=True):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{nama} harus berupa teks.")
    value = value.strip()
    if wajib and not value:
        raise ValueError(f"{nama} wajib diisi.")
    if len(value) > batas:
        raise ValueError(f"{nama} maksimal {batas} karakter.")
    return value or None


def _bilangan_bulat(value, nama, minimum=1, maksimum=32767):
    if isinstance(value, bool):
        raise ValueError(f"{nama} harus berupa angka bulat.")
    teks = str(value).strip()
    if not re.fullmatch(r"[+-]?\d+", teks):
        raise ValueError(f"{nama} harus berupa angka bulat tanpa desimal.")
    angka = int(teks)
    if not minimum <= angka <= maksimum:
        raise ValueError(f"{nama} harus antara {minimum} dan {maksimum}.")
    return angka


def _uang(value, nama="Harga bulanan"):
    try:
        hasil = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, AttributeError, ValueError):
        raise ValueError(f"{nama} harus berupa nominal angka yang valid.") from None
    if not hasil.is_finite() or hasil < 0:
        raise ValueError(f"{nama} tidak boleh negatif.")
    if hasil.as_tuple().exponent < -2:
        raise ValueError(f"{nama} maksimal memiliki dua angka desimal.")
    if hasil > Decimal("9999999999.99"):
        raise ValueError(f"{nama} melebihi batas nominal database.")
    return hasil.quantize(Decimal("0.01"))


def _bobot(values):
    hasil = {}
    for kolom in _BOBOT:
        hasil[kolom] = _bilangan_bulat(values.get(kolom), kolom.replace("bobot_", "Bobot "), 0, 100)
    if sum(hasil.values()) != 100:
        raise ValueError("Total bobot tugas, kuis, UTS, dan UAS harus tepat 100%.")
    return hasil


def buat_program(data: dict):
    """Validasi dan buat program baru. Mengembalikan (berhasil, pesan)."""
    if _admin_aktif() is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat mengelola program."
    try:
        if not isinstance(data, dict):
            raise ValueError("Data program tidak valid.")
        kode = _teks(data.get("kode"), "Kode program", 10).upper()
        if not re.fullmatch(r"[A-Z0-9_-]+", kode or ""):
            raise ValueError("Kode program hanya boleh berisi huruf, angka, garis bawah, atau tanda hubung.")
        nama = _teks(data.get("nama"), "Nama program", 100)
        jenjang = _teks(data.get("jenjang"), "Jenjang", 20)
        deskripsi = _teks(data.get("deskripsi"), "Deskripsi", 5000, wajib=False)
        harga = _uang(data.get("harga_bulanan"))
        kuota = _bilangan_bulat(data.get("kuota"), "Kuota")
        bobot = _bobot({
            "bobot_tugas": data.get("bobot_tugas", 30),
            "bobot_kuis": data.get("bobot_kuis", 20),
            "bobot_uts": data.get("bobot_uts", 20),
            "bobot_uas": data.get("bobot_uas", 30),
        })
        status = data.get("status", "buka")
        if status not in {"buka", "tutup"}:
            raise ValueError("Status program harus buka atau tutup.")
        program_id = program_repo.tambah_program(
            kode=kode, nama=nama, jenjang=jenjang, deskripsi=deskripsi,
            harga_bulanan=harga, kuota=kuota, status=status, **bobot,
        )
        return True, f"Program {kode} berhasil dibuat dengan ID {program_id}."
    except ValueError as exc:
        return False, str(exc)
    except psycopg.errors.UniqueViolation:
        return False, "Kode program sudah digunakan. Pilih kode lain."
    except psycopg.Error as exc:
        return False, f"Program gagal disimpan ke database ({type(exc).__name__})."


def ubah_program(program_id: int, perubahan: dict):
    """Validasi perubahan program termasuk kuota dan total bobot."""
    if _admin_aktif() is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat mengelola program."
    if type(program_id) is not int or program_id <= 0:
        return False, "ID program tidak valid."
    if not isinstance(perubahan, dict) or not perubahan:
        return False, "Pilih minimal satu data untuk diubah."
    try:
        if set(perubahan) - _KOLOM_PROGRAM:
            raise ValueError("Ada kolom perubahan yang tidak diizinkan.")
        nilai = dict(perubahan)
        if "kode" in nilai:
            nilai["kode"] = _teks(nilai["kode"], "Kode program", 10).upper()
            if not re.fullmatch(r"[A-Z0-9_-]+", nilai["kode"]):
                raise ValueError("Kode program hanya boleh berisi huruf, angka, garis bawah, atau tanda hubung.")
        if "nama" in nilai:
            nilai["nama"] = _teks(nilai["nama"], "Nama program", 100)
        if "jenjang" in nilai:
            nilai["jenjang"] = _teks(nilai["jenjang"], "Jenjang", 20)
        if "deskripsi" in nilai:
            nilai["deskripsi"] = _teks(nilai["deskripsi"], "Deskripsi", 5000, wajib=False)
        if "harga_bulanan" in nilai:
            nilai["harga_bulanan"] = _uang(nilai["harga_bulanan"])
        if "kuota" in nilai:
            nilai["kuota"] = _bilangan_bulat(nilai["kuota"], "Kuota")
            data = {x["id"]: x for x in program_repo.daftar_program_dengan_kuota()}.get(program_id)
            if data is None:
                return False, "Program tidak ditemukan."
            if nilai["kuota"] < data["terisi"]:
                raise ValueError(f"Kuota baru tidak boleh di bawah jumlah terisi ({data['terisi']}).")
        if "status" in nilai and nilai["status"] not in {"buka", "tutup"}:
            raise ValueError("Status program harus buka atau tutup.")
        if set(nilai) & set(_BOBOT):
            if not set(_BOBOT).issubset(nilai):
                raise ValueError("Untuk mengubah bobot, isi seluruh bobot tugas, kuis, UTS, dan UAS sekaligus.")
            nilai.update(_bobot(nilai))
        if not program_repo.ubah_program(program_id, **nilai):
            return False, "Program tidak ditemukan."
        return True, "Perubahan program berhasil disimpan."
    except ValueError as exc:
        return False, str(exc)
    except psycopg.errors.UniqueViolation:
        return False, "Kode program atau data unik lainnya sudah digunakan."
    except psycopg.Error as exc:
        return False, f"Program gagal diperbarui ke database ({type(exc).__name__})."


def buat_ruang(nama: str, kapasitas):
    if _admin_aktif() is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat mengelola ruang."
    try:
        nama = _teks(nama, "Nama ruang", 30)
        kapasitas = _bilangan_bulat(kapasitas, "Kapasitas ruang")
        ruang_id = program_repo.tambah_ruang(nama=nama, kapasitas=kapasitas)
        return True, f"Ruang berhasil ditambahkan dengan ID {ruang_id}."
    except ValueError as exc:
        return False, str(exc)
    except psycopg.errors.UniqueViolation:
        return False, "Nama ruang sudah digunakan."
    except psycopg.Error as exc:
        return False, f"Ruang gagal disimpan ke database ({type(exc).__name__})."


def ubah_ruang(ruang_id: int, perubahan: dict):
    if _admin_aktif() is None:
        return False, "Akses ditolak. Hanya admin aktif yang dapat mengelola ruang."
    if type(ruang_id) is not int or ruang_id <= 0:
        return False, "ID ruang tidak valid."
    if not isinstance(perubahan, dict) or not perubahan:
        return False, "Tidak ada perubahan ruang yang diberikan."
    try:
        nilai = {}
        if "nama" in perubahan:
            nilai["nama"] = _teks(perubahan["nama"], "Nama ruang", 30)
        if "kapasitas" in perubahan:
            nilai["kapasitas"] = _bilangan_bulat(perubahan["kapasitas"], "Kapasitas ruang")
        if set(perubahan) - {"nama", "kapasitas"}:
            raise ValueError("Kolom perubahan ruang tidak diizinkan.")
        if not program_repo.ubah_ruang(ruang_id, **nilai):
            return False, "Ruang tidak ditemukan."
        return True, "Perubahan ruang berhasil disimpan."
    except ValueError as exc:
        return False, str(exc)
    except psycopg.errors.UniqueViolation:
        return False, "Nama ruang sudah digunakan."
    except psycopg.Error as exc:
        return False, f"Ruang gagal diperbarui ke database ({type(exc).__name__})."
