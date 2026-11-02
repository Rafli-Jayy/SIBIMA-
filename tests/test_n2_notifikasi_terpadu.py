"""PATCH-N2 regression without writing to actual PostgreSQL."""
from pathlib import Path
import pytest
from app.services import engagement_service
from app.repositories import engagement_repo

ROOT=Path(__file__).resolve().parents[1]


def _active(monkeypatch,role='tutor',uid=20):
    monkeypatch.setattr(engagement_service,'_pengguna_aktif',lambda r: {'id':uid,'role':role,'status':'aktif'})


def test_tutor_announcement_uses_current_session(monkeypatch):
    _active(monkeypatch)
    captured=[]
    def fake_store(*args):captured.append(args);return {'jumlah_penerima':3}
    monkeypatch.setattr(engagement_repo,'terbitkan_pengumuman_tutor',fake_store)
    assert engagement_service.buat_pengumuman_tutor(12,' Belajar ', ' Kumpulkan tugas ')['jumlah_penerima']==3
    assert captured[0][:4]==(20,12,'Belajar','Kumpulkan tugas')


def test_invalid_duration_refused_before_database(monkeypatch):
    _active(monkeypatch)
    with pytest.raises(ValueError,match='Masa berlaku'):
        engagement_service.buat_pengumuman_tutor(12,'Pengumuman','Isi',durasi='tanpa_batas')


def test_tutor_cannot_end_other_batch_without_database_check(monkeypatch):
    _active(monkeypatch)
    with pytest.raises(ValueError,match='Kode pengumuman'):
        engagement_repo.akhiri_pengumuman_tutor(20,'lain')


def test_invalid_inbox_scope_rejected(monkeypatch):
    with pytest.raises(ValueError):engagement_repo.daftar_notifikasi_penerima(12,'admin')
    with pytest.raises(ValueError):engagement_repo.daftar_notifikasi_penerima(12,'siswa',kategori='DROP TABLE')
    with pytest.raises(ValueError):engagement_repo.daftar_notifikasi_penerima(12,'siswa',sumber='pengguna_lain')


def test_n2_sql_has_no_new_entity_and_monitors_after_installation():
    sql=(ROOT/'sql/migrations/20261101_patch_n2_notifikasi_terpadu.sql').read_text(encoding='utf-8')
    assert 'CREATE TABLE' not in sql.upper()
    assert 'notif_monitor_from' in sql
    assert 'sibima_n2_grade_insert' in sql
    assert 'sibima_n2_session_finished' in sql
    assert 'sibima_n2_schedule_changed' in sql
    assert 'SECURITY DEFINER' in sql
    assert 'BEGIN;' in sql and 'COMMIT;' in sql


def test_notices_are_scoped_to_own_user_and_active_class():
    code=(ROOT/'app/repositories/engagement_repo.py').read_text(encoding='utf-8')
    assert 'e.status::text=\'aktif\'' in code
    assert "a.dibuat_by=%s AND a.sumber='tutor'" in code
    assert 'AND dibuat_by=%s' in code
    assert 'batch_key' in code


def test_daily_reminder_does_not_write_attendance():
    code=(ROOT/'app/repositories/notification_sync_repo.py').read_text(encoding='utf-8')
    sync_only=code.split('def daftar_pertemuan_tertunda(')[0]
    assert 'INSERT INTO announcements' in sync_only
    assert 'INSERT INTO attendances' not in sync_only
    assert 'INSERT INTO class_sessions' not in sync_only
    assert "'schedule_pending'" in sync_only
    assert 'INSERT INTO class_sessions' in code  # hanya bila Tutor memilih membuat laporan


def test_private_archive_independent_of_global_archive():
    code=(ROOT/'app/repositories/engagement_repo.py').read_text(encoding='utf-8')
    assert 'announcement_reads(announcement_id,user_id,archived_at)' in code
    assert 'WHERE batch_key=%s' in code
