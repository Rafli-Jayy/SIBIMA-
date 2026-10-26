"""Service akademik tutor dengan pemeriksaan sesi, role, dan kepemilikan kelas."""

import psycopg

from app import session
from app.repositories import academic_repo, user_repo
from app.utils import academic_validation as validation


def _tutor_aktif():
    current = session.get_user()
    if not current or current.get("role") != "tutor":
        return None
    tutor_id = current.get("id")
    if type(tutor_id) is not int or tutor_id <= 0:
        return None
    try:
        user = user_repo.cari_by_id(tutor_id)
    except psycopg.Error:
        return None
    if not user or user.get("role") != "tutor" or user.get("status") != "aktif":
        return None
    return user


def _id(value, label):
    return validation.id_positif(value, label)


def jadwal(*, aktif=True):
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak. Hanya tutor dengan akun aktif yang dapat mengakses modul ini."
    try:
        return True, academic_repo.daftar_jadwal_tutor(user["id"], aktif=aktif)
    except psycopg.Error as exc:
        return False, f"Jadwal gagal diambil ({type(exc).__name__})."


def program_tutor():
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak. Hanya tutor dengan akun aktif yang dapat mengakses modul ini."
    try:
        return True, academic_repo.daftar_program_tutor(user["id"])
    except psycopg.Error as exc:
        return False, f"Daftar kelas gagal diambil ({type(exc).__name__})."


def daftar_siswa(program_id):
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak."
    try:
        program_id = _id(program_id, "Program")
        programs = academic_repo.daftar_program_tutor(user["id"])
        if not any(p["id"] == program_id for p in programs):
            return False, "Akses ditolak. Program ini bukan kelas yang kamu ampu."
        return True, academic_repo.daftar_siswa_kelas(user["id"], program_id)
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Daftar siswa gagal diambil ({type(exc).__name__})."


def detail_siswa(program_id, student_id):
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak."
    try:
        program_id = _id(program_id, "Program")
        student_id = _id(student_id, "Siswa")
        detail = academic_repo.detail_siswa_kelas(user["id"], program_id, student_id)
        if detail is None:
            return False, "Siswa tidak ditemukan pada kelas yang kamu ampu."
        return True, detail
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Detail siswa gagal diambil ({type(exc).__name__})."


def daftar_pertemuan(program_id=None):
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak."
    try:
        if program_id is not None:
            program_id = _id(program_id, "Program")
            programs = academic_repo.daftar_program_tutor(user["id"])
            if not any(p["id"] == program_id for p in programs):
                return False, "Program ini bukan kelas yang kamu ampu."
        return True, academic_repo.daftar_pertemuan(user["id"], program_id=program_id)
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Daftar pertemuan gagal diambil ({type(exc).__name__})."


def buka_pertemuan(schedule_id):
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak."
    try:
        schedule_id = _id(schedule_id, "Jadwal")
        hasil = academic_repo.buka_pertemuan(user["id"], schedule_id)
        if hasil["dibuat"]:
            return True, f"Pertemuan ke-{hasil['pertemuan_ke']} dibuat untuk tanggal {hasil['tanggal']} (ID {hasil['session_id']})."
        return True, f"Pertemuan hari ini sudah ada (ke-{hasil['pertemuan_ke']}, ID {hasil['session_id']}); memakai sesi yang sama."
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        if getattr(getattr(exc, "diag", None), "constraint_name", None) in {"uq_session_tanggal", "uq_session_ke"}:
            return False, "Pertemuan dengan tanggal/nomor tersebut sudah ada. Muat ulang daftar pertemuan."
        return False, f"Pertemuan gagal dibuat ({type(exc).__name__})."


def daftar_absensi(session_id):
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak."
    try:
        session_id = _id(session_id, "Pertemuan")
        return True, academic_repo.daftar_absensi_sesi(user["id"], session_id)
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Data absensi gagal diambil ({type(exc).__name__})."


def simpan_absensi(session_id, records):
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak."
    try:
        session_id = _id(session_id, "Pertemuan")
        if not isinstance(records, list) or not records:
            raise ValueError("Pilih setidaknya satu siswa untuk diabsen.")
        cleaned = []
        seen = set()
        for row in records:
            if not isinstance(row, dict):
                raise ValueError("Data absensi tidak valid.")
            student_id = _id(row.get("student_id"), "Siswa")
            if student_id in seen:
                raise ValueError("Siswa yang sama tercantum lebih dari sekali.")
            seen.add(student_id)
            status = validation.status_absensi(row.get("status"))
            note = validation.teks_catatan(row.get("keterangan", ""), "Keterangan", 200)
            cleaned.append({"student_id": student_id, "status": status, "keterangan": note})
        count = academic_repo.simpan_absensi(user["id"], session_id, cleaned)
        return True, f"Absensi tersimpan untuk {count} siswa."
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Absensi gagal disimpan ({type(exc).__name__})."


def rekap_absensi(program_id):
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak."
    try:
        program_id = _id(program_id, "Program")
        programs = academic_repo.daftar_program_tutor(user["id"])
        if not any(p["id"] == program_id for p in programs):
            return False, "Program ini bukan kelas yang kamu ampu."
        return True, academic_repo.rekap_absensi_tutor(user["id"], program_id)
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Rekap absensi gagal diambil ({type(exc).__name__})."


def input_nilai(program_id, student_id, jenis, nilai, judul="", tanggal=None):
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak."
    try:
        program_id = _id(program_id, "Program")
        student_id = _id(student_id, "Siswa")
        jenis = validation.jenis_nilai(jenis)
        nilai = validation.nilai_angka(nilai)
        judul = validation.teks_catatan(judul, "Judul nilai", 100)
        tanggal = validation.tanggal_valid(tanggal)
        grade_id = academic_repo.tambah_nilai(
            user["id"], program_id, student_id,
            jenis=jenis, judul=judul, nilai=nilai, tanggal=tanggal,
        )
        return True, f"Nilai berhasil disimpan (ID {grade_id})."
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Nilai gagal disimpan ({type(exc).__name__})."


def nilai_kelas(program_id):
    return daftar_siswa(program_id)


def daftar_nilai(program_id, *, hanya_milik_tutor=False):
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak."
    try:
        program_id = _id(program_id, "Program")
        programs = academic_repo.daftar_program_tutor(user["id"])
        if not any(p["id"] == program_id for p in programs):
            return False, "Program ini bukan kelas yang kamu ampu."
        return True, academic_repo.daftar_nilai_tutor(
            user["id"], program_id, hanya_milik_tutor=hanya_milik_tutor
        )
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Daftar nilai gagal diambil ({type(exc).__name__})."


def ubah_nilai(grade_id, jenis, nilai, judul="", tanggal=None):
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak."
    try:
        grade_id = _id(grade_id, "ID nilai")
        jenis = validation.jenis_nilai(jenis)
        nilai = validation.nilai_angka(nilai)
        judul = validation.teks_catatan(judul, "Judul nilai", 100)
        tanggal = validation.tanggal_valid(tanggal)
        berhasil = academic_repo.ubah_nilai(
            user["id"], grade_id, jenis=jenis, judul=judul, nilai=nilai, tanggal=tanggal
        )
        if not berhasil:
            return False, "Nilai tidak ditemukan, bukan nilai inputmu, atau bukan kelas yang kamu ampu."
        return True, "Nilai berhasil diperbarui."
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Nilai gagal diperbarui ({type(exc).__name__})."


def simpan_catatan(session_id, topik, ringkasan):
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak."
    try:
        session_id = _id(session_id, "Pertemuan")
        topik = validation.teks_catatan(topik, "Topik", 150)
        ringkasan = validation.teks_catatan(ringkasan, "Ringkasan", 10000)
        if not topik and not ringkasan:
            raise ValueError("Isi topik atau ringkasan sebelum menyimpan.")
        berhasil = academic_repo.simpan_catatan(
            user["id"], session_id, topik=topik, ringkasan=ringkasan
        )
        if not berhasil:
            return False, "Pertemuan tidak ditemukan, bukan milikmu, atau sudah dibatalkan."
        return True, "Catatan materi berhasil disimpan."
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Catatan materi gagal disimpan ({type(exc).__name__})."


def daftar_catatan(program_id=None):
    user = _tutor_aktif()
    if not user:
        return False, "Akses ditolak."
    try:
        if program_id is not None:
            program_id = _id(program_id, "Program")
            programs = academic_repo.daftar_program_tutor(user["id"])
            if not any(p["id"] == program_id for p in programs):
                return False, "Program ini bukan kelas yang kamu ampu."
        return True, academic_repo.daftar_catatan_tutor(user["id"], program_id=program_id)
    except ValueError as exc:
        return False, str(exc)
    except psycopg.Error as exc:
        return False, f"Catatan materi gagal diambil ({type(exc).__name__})."
