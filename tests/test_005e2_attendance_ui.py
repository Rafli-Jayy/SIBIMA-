"""PATCH-005E2: uji antarmuka absensi tanpa database sungguhan.

Pengujian mengeksekusi fungsi asli dari menu_tutor_academic.py via AST agar
bisa dijalankan dengan mocks pada lingkungan audit tanpa questionary/psycopg.
Di PC pengguna, seluruh suite pytest tetap harus dijalankan.
"""
import ast
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markup import escape

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/ui/menu_tutor_academic.py"


class FakeQuestionary:
    def __init__(self, status_responses=("H",), note_responses=("",), confirms=(True,)):
        self.status_responses = iter(status_responses)
        self.note_responses = iter(note_responses)
        self.confirm_responses = iter(confirms)
        self.prompts = []
        self.choices = []

    def select(self, prompt, **kwargs):
        self.prompts.append(prompt)
        self.choices.append(kwargs["choices"])
        return SimpleNamespace(ask=lambda: next(self.status_responses))

    def text(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return SimpleNamespace(ask=lambda: next(self.note_responses))

    def confirm(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return SimpleNamespace(ask=lambda: next(self.confirm_responses))


class FakeChoice:
    def __init__(self, title, *, value):
        self.title = title
        self.value = value


def _context(status_responses=("H",), note_responses=("",), confirms=(True,), roster=None, session=None):
    module = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {"_pilih_pertemuan", "_peserta_absensi_unik", "_layar_absensi_siswa", "_isi_absensi"}
    fns = [node for node in module.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(fns) == 4
    target = ast.Module(body=fns, type_ignores=[])
    console_stream = io.StringIO()
    console = Console(file=console_stream, width=120, force_terminal=False, color_system=None)
    qs = FakeQuestionary(status_responses, note_responses, confirms)
    services = SimpleNamespace(daftar_pertemuan=object(), daftar_absensi=object(), simpan_absensi=object())
    session_data = session if session is not None else {
        "session_id": 9, "nama_program": "Matematika SMA", "kode_program": "MTK-SMA",
        "pertemuan_ke": 5, "tanggal": "2026-11-03", "jumlah_absen": 0, "jam_mulai": "16:00:00",
        "jam_selesai": "17:30:00", "nama_ruang": "Ruang A", "status_pertemuan": "terlaksana",
    }
    students = roster if roster is not None else [
        {"student_id": 41, "nis": "2026-041", "nama_lengkap": "Andi Pratama", "status_absensi": None, "keterangan": ""},
    ]
    saved = []
    printed = []

    def _run_service(call,*args):
        if call is services.daftar_pertemuan:
            return True, [session_data]
        if call is services.daftar_absensi:
            return True, students
        if call is services.simpan_absensi:
            saved.append((args[0],args[1]))
            return True, "Tersimpan"
        raise AssertionError("Service tidak dikenal")

    def _teks_nilai(x):
        return str(x) if x is not None else "—"

    def jam_jadwal(r):
        return str(r.get("jam_mulai"))[:5]+"–"+str(r.get("jam_selesai"))[:5]

    state = {
        "_run_service": _run_service, "_layar": lambda title,subtitle: (printed.append((title,subtitle)), console.print(title,subtitle)),
        "_pause": lambda: None, "_hasil": lambda *args: printed.append(args),
        "peringatan": lambda text: printed.append(text), "console":console,
        "Choice":FakeChoice,"Panel":Panel,"Table":Table,"Text":Text,"escape":escape,
        "_teks_nilai":_teks_nilai,"jam_jadwal":jam_jadwal,
        "_LABEL_ABSEN":{"H":"Hadir","I":"Izin","S":"Sakit","A":"Alpa"},
        "questionary":qs,"_GAYA":None,"academic_service":services,
        "_pilih":lambda prompt,choices: 9,
    }
    exec(compile(target, str(SOURCE), "exec"),state)
    return SimpleNamespace(fn=state, q=qs, saved=saved, out=console_stream, printed=printed, session=session_data)


def test_input_absensi_selalu_menampilkan_identitas_lengkap():
    ctx = _context(note_responses=("Datang tepat waktu",))
    ctx.fn["_isi_absensi"](9, pertemuan=ctx.session)
    text = ctx.out.getvalue()
    for item in ("Andi Pratama","2026-041","Matematika SMA","Pertemuan #5","SISWA 1 DARI 1","Belum dicatat"):
        assert item in text
    assert ctx.q.prompts[0] == "Status kehadiran untuk Andi Pratama:"
    assert ctx.q.prompts[1] == "Keterangan untuk Andi Pratama (opsional):"
    assert "Simpan absensi 1 siswa" in ctx.q.prompts[2]
    assert ctx.saved == [(9,[{"student_id":41,"status":"H","keterangan":"Datang tepat waktu"}])]


def test_label_status_sebelumnya_terlihat_saat_koreksi():
    roster=[{"student_id":41,"nis":"N41","nama_lengkap":"Andi", "status_absensi":"I", "keterangan":"Izin keluarga"}]
    ctx=_context(status_responses=("S",),note_responses=("Sakit",),roster=roster)
    ctx.fn["_isi_absensi"](9, pertemuan=ctx.session)
    out=ctx.out.getvalue()
    assert "Absensi sebelumnya" in out and "Izin" in out
    assert "Status dipilih" in out and "Sakit" in out
    assert any("status sebelumnya" in c.title for c in ctx.q.choices[0])
    assert ctx.saved[0][1][0]["status"] == "S"


@pytest.mark.parametrize("status,note,confirmed",[
    (None,"",True),("__back__","",True),("H",None,True),("H","",False),("H","",None),
])
def test_batal_tidak_menyimpan_sebagian(status,note,confirmed):
    ctx=_context(status_responses=(status,),note_responses=(note,),confirms=(confirmed,))
    ctx.fn["_isi_absensi"](9, pertemuan=ctx.session)
    assert ctx.saved == []


def test_dua_siswa_rekap_bernama_sebelum_konfirmasi():
    roster=[{"student_id":41,"nis":"N41","nama_lengkap":"Andi"},
            {"student_id":42,"nis":"N42","nama_lengkap":"Sinta"}]
    ctx=_context(status_responses=("H","I"),note_responses=("","Acara keluarga"),roster=roster)
    ctx.fn["_isi_absensi"](9, pertemuan=ctx.session)
    assert len(ctx.saved[0][1]) == 2
    output=ctx.out.getvalue()
    assert "Andi" in output and "Sinta" in output
    assert "RINGKASAN ABSENSI" in output and "Acara keluarga" in output
    assert "Sinta" in ctx.q.prompts[2]


def test_duplicate_enrollment_tidak_mengabsen_siswa_dua_kali():
    roster=[{"student_id":41,"nis":"N41","nama_lengkap":"Andi"},
            {"student_id":41,"nis":"N41","nama_lengkap":"Andi"}]
    ctx=_context(roster=roster)
    ctx.fn["_isi_absensi"](9, pertemuan=ctx.session)
    assert len(ctx.saved[0][1]) == 1
    assert len(ctx.q.prompts) == 3


def test_sesi_batal_tidak_membuka_absensi():
    ctx=_context(session={"session_id":9,"status_pertemuan":"batal","nama_program":"Matematika SMA"})
    ctx.fn["_isi_absensi"](9, pertemuan=ctx.session)
    assert not ctx.q.prompts and not ctx.saved
    assert any("dibatalkan" in str(x).lower() for x in ctx.printed)


def test_id_sesi_tidak_cocok_menolak_pengisian():
    ctx=_context()
    ctx.fn["_isi_absensi"](99, pertemuan=ctx.session)
    assert not ctx.q.prompts and not ctx.saved


def test_roster_kosong_menampilkan_alasan():
    ctx=_context(roster=[])
    ctx.fn["_isi_absensi"](9, pertemuan=ctx.session)
    assert not ctx.q.prompts and not ctx.saved
    assert any("Belum ada siswa" in str(x) for x in ctx.printed)


def test_sesi_ambil_dari_service_jika_detail_tidak_diberikan():
    ctx=_context()
    ctx.fn["_isi_absensi"](9)
    assert len(ctx.saved) == 1


def test_pilih_pertemuan_dapat_mengembalikan_detail_terpilih():
    ctx=_context()
    assert ctx.fn["_pilih_pertemuan"](dengan_detail=True) == ctx.session
    assert ctx.fn["_pilih_pertemuan"]() == 9


def test_info_helper_diimpor_agar_detail_jadwal_tidak_nameerror():
    source=SOURCE.read_text(encoding="utf-8")
    assert "from app.ui.console import console, bersihkan_layar, gagal, sukses, peringatan, info" in source
