"""Format dan klasifikasi informasi jadwal rutin (read-only).

Jadwal bukan bukti sebuah pertemuan sudah dilaksanakan.
"""
from datetime import date, timedelta

HARI = ("senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu")


def label_hari(value):
    return str(value or "—").capitalize()


def label_jam(value):
    if value is None:
        return "—"
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    return str(value)[:5]


def jam_jadwal(item):
    return f"{label_jam(item.get('jam_mulai'))}–{label_jam(item.get('jam_selesai'))}"


def kondisi_jadwal_siswa(enrollments, jadwal, hari=None):
    """Bedakan kosong hari ini, belum dijadwalkan, dan belum punya kelas.

    Daftar jadwal harus berasal dari service dengan filter H+3 dan kepemilikan.
    """
    active = [e for e in enrollments if e.get("status") == "aktif"]
    accessible = [e for e in active if not e.get("akses_terkunci")]
    if not active:
        return "belum_ada_kelas"
    if not accessible:
        return "terkunci_tagihan"
    if not jadwal:
        return "belum_dijadwalkan"
    if hari is not None and not any(j.get("hari") == hari for j in jadwal):
        return "tidak_ada_hari_ini"
    return "ada_jadwal"


def jadwal_rutin_terdekat(jadwal, hari_ini=None):
    """Tanggal perkiraan berdasarkan pola mingguan; BUKAN sesi terkonfirmasi.

    Tidak membedakan sesi ditiadakan atau perubahan khusus (belum dimodelkan).
    """
    if not jadwal:
        return None
    today = hari_ini or date.today()
    options = []
    for item in jadwal:
        if item.get("hari") not in HARI:
            continue
        offset = (HARI.index(item["hari"]) - today.weekday()) % 7
        options.append((offset, label_jam(item.get("jam_mulai")), item))
    if not options:
        return None
    offset, _, item = min(options, key=lambda x: (x[0], x[1]))
    return today + timedelta(days=offset), item
