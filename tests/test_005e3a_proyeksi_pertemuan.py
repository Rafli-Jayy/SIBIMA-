"""PATCH-005E3-A: proyeksi jadwal harus aman, jujur, dan read-only."""
from datetime import date, datetime, time
from pathlib import Path

import pytest

from app.ui.proyeksi_pertemuan import proyeksi_jadwal, CATATAN_PROYEKSI

ROOT = Path(__file__).resolve().parent.parent


def _jadwal(**changes):
    base = {"schedule_id": 8, "hari": "selasa", "jam_mulai": time(16),
            "jam_selesai": time(17, 30), "aktif": True}
    base.update(changes)
    return base


def _sesi(tanggal, schedule_id=8, status="terlaksana", nomor=2):
    return {"schedule_id": schedule_id, "tanggal": tanggal, "session_id": 22,
            "status_pertemuan": status, "pertemuan_ke": nomor}


def test_proyeksi_menampilkan_tanggal_mendatang_tanpa_nomor_palsu():
    result = proyeksi_jadwal(_jadwal(), [], datetime(2026, 11, 2, 10))
    assert result["berikutnya"]["tanggal"] == date(2026, 11, 3)
    assert result["berikutnya"]["nomor"] is None
    assert result["berikutnya"]["session_id"] is None
    assert result["berikutnya"]["status"] == "Terjadwal (perkiraan)"


def test_pada_hari_jadwal_sebelum_mulai_dan_saat_slot():
    sebelum = proyeksi_jadwal(_jadwal(), [], datetime(2026, 11, 3, 15, 59))
    sedang = proyeksi_jadwal(_jadwal(), [], datetime(2026, 11, 3, 16, 45))
    assert sebelum["berikutnya"]["tanggal"] == date(2026, 11, 3)
    assert sebelum["berikutnya"]["status"] == "Terjadwal (perkiraan)"
    assert sedang["berikutnya"]["tanggal"] == date(2026, 11, 3)
    assert sedang["berikutnya"]["status"] == "Dalam jam jadwal (belum dikonfirmasi)"


def test_sesudah_jadwal_berakhir_masuk_slot_lampau_bukan_selesai():
    result = proyeksi_jadwal(_jadwal(), [], datetime(2026, 11, 3, 17, 30))
    assert result["sebelumnya"]["tanggal"] == date(2026, 11, 3)
    assert result["sebelumnya"]["status"] == "Belum dilaporkan (perkiraan)"
    assert result["berikutnya"]["tanggal"] == date(2026, 11, 10)


def test_tidak_ada_laporan_sama_sekali_bukan_alfa():
    status = proyeksi_jadwal(_jadwal(), [], datetime(2026, 11, 4))["sebelumnya"]["status"]
    assert "Belum dilaporkan" in status
    assert "Alfa" not in status
    assert "bukan bukti" in CATATAN_PROYEKSI


def test_laporan_gagal_diambil_bukan_dianggap_tidak_dilaporkan():
    status = proyeksi_jadwal(_jadwal(), None, datetime(2026, 11, 4))["sebelumnya"]["status"]
    assert "belum tersedia" in status
    assert "Belum dilaporkan" not in status


def test_sesi_terlaksana_lama_bukan_dianggap_selesai():
    r = proyeksi_jadwal(_jadwal(), [_sesi(date(2026, 11, 3))], datetime(2026, 11, 4))
    assert r["sebelumnya"]["status"] == "Sesi tercatat (belum tentu selesai)"
    assert r["sebelumnya"]["nomor"] == 2
    assert r["sebelumnya"]["session_id"] == 22


def test_sesi_batal_tercatat_dengan_label_jelas():
    r = proyeksi_jadwal(_jadwal(), [_sesi(date(2026, 11, 3), status="batal")], datetime(2026, 11, 4))
    assert r["sebelumnya"]["status"] == "Dibatalkan (tercatat)"


def test_sesi_dari_jadwal_lain_tidak_boleh_tertukar():
    r = proyeksi_jadwal(_jadwal(), [_sesi(date(2026, 11, 3), schedule_id=12)], datetime(2026, 11, 4))
    assert r["sebelumnya"]["session_id"] is None
    assert "Belum dilaporkan" in r["sebelumnya"]["status"]


def test_sesi_tutor_yang_sudah_scoped_boleh_tanpa_id_jadwal():
    row = _sesi(date(2026, 11, 3))
    del row["schedule_id"]
    r = proyeksi_jadwal(_jadwal(id=8), [row], datetime(2026, 11, 4))
    assert r["sebelumnya"]["session_id"] == 22


def test_sesi_dengan_tanggal_dari_string_iso():
    r = proyeksi_jadwal(_jadwal(), [_sesi("2026-11-03")], datetime(2026, 11, 4))
    assert r["sebelumnya"]["session_id"] == 22


@pytest.mark.parametrize("hari,jam_mulai,jam_selesai,aktif", [
    ("senen",time(16),time(17),True),
    ("selasa",time(18),time(17),True),
    ("selasa",None,time(17),True),
    ("selasa",time(16),None,True),
    ("selasa",time(16),time(17),False),
])
def test_data_jadwal_tidak_valid_aman(hari,jam_mulai,jam_selesai,aktif):
    assert proyeksi_jadwal(_jadwal(hari=hari,jam_mulai=jam_mulai,jam_selesai=jam_selesai,aktif=aktif),[],datetime(2026,11,4)) is None


def test_tipe_string_jam_dan_hari_diterima():
    r = proyeksi_jadwal(_jadwal(hari="Selasa",jam_mulai="16:00:00",jam_selesai="17:30:00"), [], datetime(2026,11,4))
    assert r["berikutnya"]["tanggal"] == date(2026,11,10)


def test_tidak_memutasi_jadwal_atau_sesi():
    j = _jadwal()
    s = [_sesi(date(2026,11,3))]
    beforej = j.copy()
    befores = s[0].copy()
    proyeksi_jadwal(j, s, datetime(2026,11,4))
    assert j == beforej and s[0] == befores


def test_date_as_now_for_deterministic_preview():
    r = proyeksi_jadwal(_jadwal(), [], date(2026,11,3))
    assert r["berikutnya"]["tanggal"] == date(2026,11,3)


def test_sql_siswa_tetap_mewajibkan_enrollment_dan_h3():
    source = (ROOT / 'app/repositories/student_repo.py').read_text(encoding='utf-8')
    section = source.split('def daftar_pertemuan_siswa(', 1)[1].split('def rekap_absensi(',1)[0]
    assert 'cs.schedule_id' in section
    assert "e.status = 'aktif'" in section
    assert 'AKSES_TERKUNCI_SQL' in section
    assert 'ENROLLMENT_TERAKHIR_TERSEDIA_SQL' in section
    assert 'cs.tanggal >= e.created_at::date' in section
    assert 'INSERT' not in section.upper() and 'UPDATE' not in section.upper()


def test_ui_menggunakan_data_sesi_terotorisasi_bukan_membuat_sesi():
    student = (ROOT / 'app/ui/menu_siswa_academic.py').read_text(encoding='utf-8')
    tutor = (ROOT / 'app/ui/menu_tutor_academic.py').read_text(encoding='utf-8')
    assert '_sesi_per_program_jadwal' in student
    assert 'student_service.pertemuan_saya(program_id)' in student
    assert 'proyeksi_jadwal(j, sesis.get(j.get("program_id")))' in student
    assert 'proyeksi_jadwal(item, sessions)' in tutor
    assert 'CATATAN_PROYEKSI' in student and 'CATATAN_PROYEKSI' in tutor


def test_helper_tidak_memakai_database_atau_mencatat_kegiatan():
    source = (ROOT / 'app/ui/proyeksi_pertemuan.py').read_text(encoding='utf-8').upper()
    for term in ('PSYCOPG', 'INSERT INTO', 'UPDATE ', 'DELETE FROM', 'CLASS_SESSIONS'):
        assert term not in source


def test_panel_siswa_tidak_menuduh_belum_lapor_sebelum_siswa_bergabung():
    import ast
    from rich.console import Console
    from rich.panel import Panel
    from rich.markup import escape
    import io
    from app.ui.jadwal_context import label_hari, jam_jadwal

    source = (ROOT / "app/ui/menu_siswa_academic.py").read_text(encoding="utf-8")
    node = next(x for x in ast.parse(source).body if isinstance(x, ast.FunctionDef)
                and x.name == "_panel_rencana_siswa")
    output = io.StringIO()
    def tanggal_human(x):
        return x.strftime('%d-%m-%Y')
    state = {"datetime": datetime, "date": date, "proyeksi_jadwal": lambda item, sessions: proyeksi_jadwal(item, sessions, datetime(2026,11,4)),
             "console": Console(file=output, width=110), "Panel": Panel,
             "escape": escape, "label_hari": label_hari, "jam_jadwal": jam_jadwal,
             "_tanggal": tanggal_human, "info": lambda *args: None,
             "CATATAN_PROYEKSI": CATATAN_PROYEKSI}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "menu_siswa_academic.py", "exec"), state)
    j = _jadwal(program_id=7, nama_program="Matematika", hari="selasa")
    enrollment = {"program_id": 7, "status":"aktif", "akses_terkunci":False,
                  "created_at": datetime(2026,11,4,10)}
    state["_panel_rencana_siswa"]([j], {7: []}, [enrollment])
    rendered = output.getvalue()
    assert "Sebelum pendaftaran ini" in rendered
    assert "10-11-2026" in rendered
    assert "Belum dilaporkan" not in rendered


def test_panel_siswa_tidakterkunci_tetap_memakai_laporan_terverifikasi():
    from app.ui.proyeksi_pertemuan import CATATAN_PROYEKSI
    assert "tanggal mulai" in CATATAN_PROYEKSI
    source = (ROOT / "app/ui/menu_siswa_academic.py").read_text(encoding="utf-8")
    assert 'status == "aktif" and not locked' in source
    assert '"status" != "aktif"' in source or 'e.get("status") != "aktif"' in source
    assert 'e.get("akses_terkunci")' in source
