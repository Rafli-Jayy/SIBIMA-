"""Regression PATCH-N1: query privacy and event idempotency design, no DB writes."""
from pathlib import Path

from app.repositories import engagement_repo

ROOT = Path(__file__).resolve().parents[1]


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls = []
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, query, params=()): self.calls.append((query, params))
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, cursor): self.cur=cursor; self.commits=0
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def cursor(self, **kwargs): return self.cur
    def commit(self): self.commits+=1


class FakePool:
    def __init__(self, conn): self.conn=conn
    def connection(self): return self.conn


def _pool(monkeypatch, rows):
    cur=FakeCursor(rows)
    conn=FakeConnection(cur)
    monkeypatch.setattr(engagement_repo,'pool',FakePool(conn))
    return cur,conn


def test_inbox_separates_targeted_private_from_role_broadcast(monkeypatch):
    cur,_=_pool(monkeypatch,[{'id':23,'sumber':'sistem'}])
    assert engagement_repo.daftar_notifikasi_penerima(4,'siswa',limit=7)[0]['id']==23
    sql,params=cur.calls[0]
    assert params==(4,4,'siswa',7)
    assert 'a.penerima_user_id = %s' in sql
    assert 'a.penerima_user_id IS NULL' in sql
    assert 'EXISTS' in sql and 't.target_role = %s' in sql
    assert 'a.archived_at IS NULL' in sql


def test_unread_count_uses_same_access_boundary(monkeypatch):
    cur,_=_pool(monkeypatch,[(3,)])
    assert engagement_repo.jumlah_notifikasi_belum_dibaca(4,'siswa')==3
    sql,params=cur.calls[0]
    assert params==(4,4,'siswa')
    assert 'a.penerima_user_id IS NULL' in sql
    assert 'r.announcement_id IS NULL' in sql


def test_detail_rejects_unowned_notification_before_marking_read(monkeypatch):
    cur,conn=_pool(monkeypatch,[])
    assert engagement_repo.detail_notifikasi_penerima(4,'siswa',45) is None
    assert len(cur.calls)==1
    assert cur.calls[0][1]==(45,4,'siswa')
    assert conn.commits==0


def test_detail_marks_only_owner_read(monkeypatch):
    cur,conn=_pool(monkeypatch,[{'id':45,'sumber':'sistem'}])
    item=engagement_repo.detail_notifikasi_penerima(4,'siswa',45)
    assert item['id']==45
    assert len(cur.calls)==2
    assert cur.calls[1][1]==(45,4)
    assert 'ON CONFLICT' in cur.calls[1][0]
    assert conn.commits==1


def test_admin_list_restricts_system_notifications(monkeypatch):
    cur,_=_pool(monkeypatch,[])
    engagement_repo.daftar_pengumuman_admin('aktif')
    assert "a.sumber = 'admin'" in cur.calls[0][0]


def test_admin_cannot_archive_system_inbox_messages(monkeypatch):
    cur,_=_pool(monkeypatch,[])
    engagement_repo.arsipkan_pengumuman(50, 1)
    assert "sumber = 'admin'" in cur.calls[0][0]



def test_business_events_triggers_are_transactional_and_deduplicated():
    sql=(ROOT/'sql/migrations/20261101_patch_n1_notifikasi_sistem.sql').read_text(encoding='utf-8')
    assert 'BEGIN;' in sql and 'COMMIT;' in sql
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS sibima_n1_event_key_uniq' in sql
    assert 'ON CONFLICT DO NOTHING' in sql
    for target in ('users','enrollments','invoices','payments'):
        assert 'ON public.'+target in sql
    assert 'IF current_database() <>' in sql
    assert 'SECURITY DEFINER' in sql
    assert 'REVOKE ALL ON FUNCTION public.sibima_n1_emit' in sql


def test_no_new_tables_required():
    sql=(ROOT/'sql/migrations/20261101_patch_n1_notifikasi_sistem.sql').read_text(encoding='utf-8')
    assert 'CREATE TABLE' not in sql.upper()
