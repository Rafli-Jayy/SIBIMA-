"""Proyeksi read-only jadwal SIBIMA, bukan pembuat sesi/absensi.

Tidak ada tanggal mulai jadwal pada schema. Slot yang lewat tanpa sesi hanyalah
INDIKASI belum dilaporkan, bukan bukti tutor tidak mengajar.
"""
from datetime import date, datetime, time, timedelta
from app.ui.jadwal_context import HARI


def _tanggal(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _jam(value):
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        try:
            return time.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _cari_sesi(sesi, item, tanggal):
    """Pilih sesi milik jadwal dan tanggal ini. Sesi None = query gagal/tidak diambil."""
    if sesi is None:
        return None
    schedule_id = item.get("schedule_id", item.get("id"))
    for row in sesi:
        if _tanggal(row.get("tanggal")) != tanggal:
            continue
        row_schedule_id = row.get("schedule_id")
        if row_schedule_id is not None and schedule_id is not None and row_schedule_id != schedule_id:
            continue
        return row
    return None


def _ringkas_slot(item, sesi, tanggal, *, lampau, sekarang):
    row = _cari_sesi(sesi, item, tanggal)
    nomor = row.get("pertemuan_ke") if row else None
    if row:
        if row.get("status_pertemuan") == "batal":
            status = "Dibatalkan (tercatat)"
        elif row.get("status_pertemuan") == "selesai":
            status = "Selesai (dikonfirmasi Tutor)"
        elif row.get("status_pertemuan") == "perlu_laporan":
            status = "Perlu absensi / laporan Tutor"
        else:
            status = "Sesi tercatat (belum tentu selesai)"
    elif sesi is None:
        status = "Status laporan belum tersedia" if lampau else "Terjadwal (perkiraan)"
    elif lampau:
        status = "Belum dilaporkan (perkiraan)"
    elif tanggal == sekarang.date() and _jam(item.get("jam_mulai")) <= sekarang.time() < _jam(item.get("jam_selesai")):
        status = "Dalam jam jadwal (belum dikonfirmasi)"
    else:
        status = "Terjadwal (perkiraan)"
    return {"tanggal": tanggal, "status": status, "session_id": row.get("session_id") if row else None,
            "nomor": nomor, "ada_sesi": bool(row), "perkiraan": not bool(row)}


def proyeksi_jadwal(item, sesi=None, sekarang=None):
    """Satu jadwal -> slot lampau terdekat & slot mendatang (tanpa INSERT).

    Jika kelas sedang melewati jam rutin hari ini, slot hari ini berada pada
    bagian 'berikutnya'; tidak dipastikan bahwa pembelajaran sedang berlangsung.
    Tidak menyimpulkan tanggal mulai/jumlah pertemuan dari pola mingguan.
    """
    if item.get("aktif") is False or str(item.get("hari") or "").lower() not in HARI:
        return None
    start = _jam(item.get("jam_mulai"))
    end = _jam(item.get("jam_selesai"))
    if start is None or end is None or start >= end:
        return None
    now = sekarang or datetime.now()
    if isinstance(now, date) and not isinstance(now, datetime):
        now = datetime.combine(now, time.min)
    if not isinstance(now, datetime):
        raise TypeError("Parameter sekarang harus berupa datetime atau date.")
    today = now.date()
    weekday = HARI.index(str(item["hari"]).lower())
    days_until = (weekday - today.weekday()) % 7
    next_day = today + timedelta(days=days_until)
    # Bila slot hari ini sudah berlalu, slot berikutnya pekan depan.
    if days_until == 0 and now.time() >= end:
        next_day += timedelta(days=7)
    prev_day = next_day - timedelta(days=7)
    return {
        "sebelumnya": _ringkas_slot(item, sesi, prev_day, lampau=True, sekarang=now),
        "berikutnya": _ringkas_slot(item, sesi, next_day, lampau=False, sekarang=now),
    }


CATATAN_PROYEKSI = (
    "Tanggal dihitung dari jadwal rutin (perkiraan). Jadwal belum punya tanggal "
    "mulai/pengecualian; label belum dilaporkan bukan bukti kelas tidak terlaksana. "
    "Sesi tercatat bukan berarti absensi lengkap atau pertemuan selesai."
)
