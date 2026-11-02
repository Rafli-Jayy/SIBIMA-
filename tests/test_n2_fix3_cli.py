"""Regresi FIX3/FIX7: kembali, layar sederhana, dan arsip pribadi bagi penerima."""
from app.ui import menu_tutor_pengumuman, menu_tutor_tertunda, menu_notifikasi
from app.services import engagement_service


def _choose_last_value(*args, **kwargs):
    class Result:
        def ask(self):
            return kwargs['choices'][-1].value
    return Result()


def test_pengumuman_kembali_bernilai_sentinel_dan_menutup_menu(monkeypatch):
    monkeypatch.setattr(menu_tutor_pengumuman.questionary, 'select', _choose_last_value)
    assert menu_tutor_pengumuman._pick('Pilih menu:', [('Pengumuman Aktif','aktif')]) is None
    monkeypatch.setattr(menu_tutor_pengumuman, '_header', lambda *a: None)
    called=[]
    monkeypatch.setattr(menu_tutor_pengumuman, '_list', lambda *a: called.append('list'))
    menu_tutor_pengumuman.jalankan()
    assert not called


def test_kembali_tidak_memuat_pengumuman_lagi(monkeypatch):
    monkeypatch.setattr(menu_tutor_pengumuman, '_header', lambda *a: None)
    monkeypatch.setattr(menu_tutor_pengumuman, '_pick', lambda *a: None)
    def no_fetch(*a):
        raise AssertionError('Jangan akses daftar pengumuman setelah Kembali')
    monkeypatch.setattr(engagement_service, 'daftar_pengumuman_tutor', no_fetch)
    menu_tutor_pengumuman.jalankan()


def test_pertemuan_tertunda_kembali_bukan_indeks(monkeypatch):
    monkeypatch.setattr(menu_tutor_tertunda.questionary, 'select', _choose_last_value)
    monkeypatch.setattr(menu_tutor_tertunda, 'bersihkan_layar', lambda: None)
    monkeypatch.setattr(menu_tutor_tertunda.console, 'print', lambda *a,**kw: None)
    monkeypatch.setattr(engagement_service, 'daftar_pertemuan_tertunda_tutor', lambda *a: [
        {'tanggal':'2026-11-01','nama_program':'Fisika','session_id':None,'schedule_id':11}
    ])
    menu_tutor_tertunda.jalankan()


def test_notifikasi_tidak_punya_filter_di_menu(monkeypatch):
    monkeypatch.setattr(menu_notifikasi, '_header', lambda *a: None)
    monkeypatch.setattr(engagement_service, 'sinkronisasi_notifikasi', lambda role: None)
    monkeypatch.setattr(engagement_service, 'jumlah_notifikasi_belum_dibaca', lambda role: 0)
    choices=[]
    def picker(label,items,**kw):
        choices.extend(items)
        return 'back'
    monkeypatch.setattr(menu_notifikasi, '_pilih', picker)
    assert menu_notifikasi.jalankan('siswa') is None
    assert not any('filter' in str(label).lower() or code=='filter' for label,code in choices)
    assert not hasattr(menu_notifikasi, '_filter')


def _notification(sumber, kategori):
    return {'id':15,'judul':'Contoh pengumuman', 'isi':'Informasi kelas', 'sumber':sumber,
            'kategori':kategori, 'created_at':None, 'expires_at':None,
            'nama_pembuat':'Tutor Contoh', 'nama_pelaku':None, 'nama_program':'Fisika',
            'related_type':None}


def test_detail_pengumuman_admin_bisa_diarsipkan(monkeypatch):
    monkeypatch.setattr(menu_notifikasi, '_header', lambda *a: None)
    monkeypatch.setattr(menu_notifikasi.console, 'print', lambda *a,**kw: None)
    monkeypatch.setattr(engagement_service, 'buka_notifikasi',lambda *a: _notification('admin','umum'))
    options=[]
    monkeypatch.setattr(menu_notifikasi,'_pilih',lambda _label,items,**kw: options.extend(items) or 'back')
    assert menu_notifikasi._detail('siswa',{'id':15}) is None
    assert options==[('Arsipkan Notifikasi','archive'),('Kembali ke daftar','back')]


def test_detail_pengumuman_tutor_bisa_diarsipkan(monkeypatch):
    monkeypatch.setattr(menu_notifikasi, '_header', lambda *a: None)
    monkeypatch.setattr(menu_notifikasi.console, 'print', lambda *a,**kw: None)
    monkeypatch.setattr(engagement_service, 'buka_notifikasi',lambda *a: _notification('tutor','pengumuman'))
    options=[]
    monkeypatch.setattr(menu_notifikasi,'_pilih',lambda _label,items,**kw: options.extend(items) or 'back')
    assert menu_notifikasi._detail('siswa',{'id':15}) is None
    assert options==[('Arsipkan Notifikasi','archive'),('Kembali ke daftar','back')]


def test_notifikasi_sistem_tetap_bisa_diarsip_pribadi(monkeypatch):
    monkeypatch.setattr(menu_notifikasi, '_header', lambda *a: None)
    monkeypatch.setattr(menu_notifikasi.console, 'print', lambda *a,**kw: None)
    monkeypatch.setattr(engagement_service, 'buka_notifikasi',lambda *a: _notification('sistem','nilai'))
    options=[]
    monkeypatch.setattr(menu_notifikasi,'_pilih',lambda _label,items,**kw: options.extend(items) or 'back')
    assert menu_notifikasi._detail('siswa',{'id':15}) is None
    assert ('Arsipkan Notifikasi','archive') in options
