"""PATCH-004E regression: refund 100% of settled class payments; fake DB only."""
from decimal import Decimal
from unittest.mock import Mock
import pytest
from app.repositories import enrollment_repo
from app.services import admin_enrollment_service, billing_receipt_service

class Cursor:
    def __init__(self, status='aktif', amounts=('100000','150000'), pending=True, fail=None, mismatch=False, duplicate=False):
        self.status,self.fail,self.mismatch,self.duplicate=status,fail,mismatch,duplicate
        self.invoices=[{'id':i,'no_invoice':f'INV-{i}','status':'lunas'} for i,_ in enumerate(amounts,1)]
        self.payments=[{'payment_id':i+100,'invoice_id':i,'jumlah':Decimal(a),'payment_status':'lunas'} for i,a in enumerate(amounts,1)]
        if pending:
            self.invoices.append({'id':99,'no_invoice':'INV-99','status':'belum_dibayar'})
            self.payments.append({'payment_id':299,'invoice_id':99,'jumlah':Decimal(200000),'payment_status':'menunggu_konfirmasi'})
        if mismatch and self.invoices:self.invoices[0]['status']='belum_dibayar'
        if duplicate and self.payments:self.payments.append({**self.payments[0],'payment_id':999})
        self.row=None;self.rows=[];self.queries=[];self.refunds=[];self.closed=False;self.pending_closed=False;self.enrollment_closed=False;self.payment_ids=[]
    def __enter__(self): return self
    def __exit__(self,*_): return False
    def execute(self,query,params=None):
        q=' '.join(query.lower().split());self.queries.append((q,params));self.row=None;self.rows=[]
        if self.fail and self.fail in q: raise RuntimeError('failure injected')
        if 'from enrollments e join programs p' in q and 'for update of e' in q:
            if self.status is not None:self.row={'id':9,'student_id':22,'program_id':4,'status':self.status,'nama_program':'IPA'}
        elif q.startswith('select id, no_invoice, status from invoices'):self.rows=self.invoices
        elif q.startswith('select pay.id as payment_id'):self.rows=self.payments
        elif q.startswith('insert into payment_refunds'):
            payment_id,code,amount,reason=params
            self.row={'id':payment_id+200,'payment_id':payment_id,'kode_refund':code,'jumlah':amount,'alasan':reason,'status':'berhasil'}
            self.refunds.append(self.row)
        elif q.startswith("update payments set status = 'direfund'"):
            self.payment_ids.append(params[0]);self.row={'id':params[0]}
        elif q.startswith("update payments pay set status = 'gagal'"):self.pending_closed=True
        elif q.startswith("update invoices set status = 'batal'"):self.closed=True
        elif q.startswith("update enrollments set status = 'batal'"):self.enrollment_closed=True;self.row={'id':9}
        elif q.startswith('insert into activity_logs'):pass
        else:raise AssertionError(f'Unexpected query: {q[:180]}')
    def fetchone(self):return self.row
    def fetchall(self):return self.rows
class Conn:
    def __init__(self,c):self.cur=c;self.commits=0
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def cursor(self,**_):return self.cur
    def commit(self):self.commits+=1

def setup(monkeypatch,**kwargs):
    c=Cursor(**kwargs);conn=Conn(c)
    monkeypatch.setattr(enrollment_repo,'pool',Mock(connection=lambda:conn))
    return c,conn

def test_refunds_all_successful_months_and_cancels_unpaid(monkeypatch):
    c,conn=setup(monkeypatch)
    outcome=enrollment_repo.batalkan_admin(9,8,'Pindah kota')
    assert outcome['berhasil'] and outcome['total_refund']==Decimal(250000)
    assert len(outcome['refunds'])==2 and conn.commits==1
    assert c.closed and c.pending_closed and c.enrollment_closed
    assert c.payment_ids==[101,102]
    assert [x['kode_refund'] for x in c.refunds]==['RF-CAN-101','RF-CAN-102']
    assert all(x['alasan']=='Pindah kota' for x in c.refunds)

@pytest.mark.parametrize('status,amounts,expected',[
    ('aktif',(),True),('menunggu',(),True),('menunggu',('100000',),False),
    ('batal',('100000',),False),('ditolak',('100000',),False),
    ('selesai',('100000',),False),('menunggu_pembayaran',('100000',),False),
    (None,('100000',),False),
])
def test_supported_states(monkeypatch,status,amounts,expected):
    c,conn=setup(monkeypatch,status=status,amounts=amounts)
    outcome=enrollment_repo.batalkan_admin(9,8)
    assert outcome['berhasil'] is expected
    assert bool(conn.commits)==expected
    assert c.enrollment_closed is expected
    if status=='menunggu' and amounts:assert 'Tolak Pendaftaran' in outcome['pesan']

@pytest.mark.parametrize('which', ['enrollment_id','processed_by'])
def test_invalid_ids_never_call_db(monkeypatch,which):
    monkeypatch.setattr(enrollment_repo,'pool',Mock(connection=Mock(side_effect=AssertionError('DB invoked'))))
    args={'enrollment_id':9,'processed_by':8};args[which]=0
    with pytest.raises(ValueError):enrollment_repo.batalkan_admin(**args)

@pytest.mark.parametrize('reason',['X'*1001, 123])
def test_invalid_reason(monkeypatch,reason):
    monkeypatch.setattr(enrollment_repo,'pool',Mock(connection=Mock(side_effect=AssertionError('DB invoked'))))
    with pytest.raises(ValueError):enrollment_repo.batalkan_admin(9,8,reason)

def test_default_reason(monkeypatch):
    c,_=setup(monkeypatch)
    result=enrollment_repo.batalkan_admin(9,8,'   ')
    assert result['alasan']=='Pembatalan kelas oleh administrator.'
    assert c.refunds[0]['alasan']==result['alasan']

def test_corrupt_status_blocks_refund(monkeypatch):
    c,conn=setup(monkeypatch,mismatch=True)
    with pytest.raises(RuntimeError,match='tidak konsisten'):enrollment_repo.batalkan_admin(9,8)
    assert not c.refunds and not conn.commits

def test_duplicate_paid_invoice_blocks_refund(monkeypatch):
    c,conn=setup(monkeypatch,duplicate=True)
    with pytest.raises(RuntimeError,match='tepat satu'):enrollment_repo.batalkan_admin(9,8)
    assert not c.refunds and not conn.commits

def test_invoice_lunas_without_payment_blocks_refund(monkeypatch):
    c,conn=setup(monkeypatch,amounts=('100000',),pending=False)
    c.payments=[]
    with pytest.raises(RuntimeError,match='Invoice lunas'):enrollment_repo.batalkan_admin(9,8)
    assert not c.refunds and not conn.commits

@pytest.mark.parametrize('error_step',['insert into payment_refunds',"update invoices set status = 'batal'",'insert into activity_logs'])
def test_transaction_error_never_commits(monkeypatch,error_step):
    c,conn=setup(monkeypatch,fail=error_step)
    with pytest.raises(RuntimeError,match='failure injected'):enrollment_repo.batalkan_admin(9,8)
    assert conn.commits==0

def test_row_locks_before_changes(monkeypatch):
    c,_=setup(monkeypatch)
    enrollment_repo.batalkan_admin(9,8)
    q=[r[0] for r in c.queries]
    assert 'for update of e' in q[0]
    assert 'order by id for update' in q[1]
    assert 'for update of pay' in q[2]
    assert q.index(next(x for x in q if x.startswith('insert into payment_refunds')))<q.index(next(x for x in q if x.startswith("update invoices set status = 'batal'")))

def test_service_denies_non_admin(monkeypatch):
    monkeypatch.setattr(admin_enrollment_service,'_admin_aktif',lambda:None)
    monkeypatch.setattr(enrollment_repo,'batalkan_admin',Mock(side_effect=AssertionError('DB invoked')))
    ok,msg=admin_enrollment_service.batalkan_pendaftaran(9)
    assert not ok and 'Akses ditolak' in msg

def test_service_renders_one_document_per_refund(monkeypatch):
    monkeypatch.setattr(admin_enrollment_service,'_admin_aktif',lambda:{'id':8})
    data={'berhasil':True,'pesan':'Refund sukses','student_id':22,'nama_program':'IPA','alasan':'Alasan',
          'refunds':[{'status':'berhasil','payment_id':i,'kode_refund':f'RF-CAN-{i}','jumlah':Decimal(50000)} for i in [101,102]]}
    monkeypatch.setattr(enrollment_repo,'batalkan_admin',Mock(return_value=data))
    monkeypatch.setattr(admin_enrollment_service.user_repo,'cari_by_id',lambda _: {'email':'s@example.test','nama_lengkap':'Siswa'})
    sent=[]
    monkeypatch.setattr(billing_receipt_service,'buat_pdf_bukti_refund',lambda d: sent.append(d) or '/tmp/refund.pdf')
    monkeypatch.setattr(billing_receipt_service,'kirim_pdf_refund_via_email',lambda d,p:(True,'ok'))
    ok,msg=admin_enrollment_service.batalkan_pendaftaran(9)
    assert ok and 'dikirim' in msg and len(sent)==2
    assert all(d['jenis_refund']=='pembatalan' for d in sent)

def test_notification_failure_does_not_undo_success(monkeypatch):
    monkeypatch.setattr(admin_enrollment_service,'_admin_aktif',lambda:{'id':8})
    monkeypatch.setattr(enrollment_repo,'batalkan_admin',Mock(return_value={
        'berhasil':True,'pesan':'Tercatat','student_id':22,'nama_program':'IPA','alasan':'Alasan',
        'refunds':[{'status':'berhasil'}]}))
    monkeypatch.setattr(admin_enrollment_service.user_repo,'cari_by_id',lambda _: {'email':'s@example.test'})
    monkeypatch.setattr(billing_receipt_service,'buat_pdf_bukti_refund',Mock(side_effect=OSError('disk full')))
    ok,msg=admin_enrollment_service.batalkan_pendaftaran(9)
    assert ok and 'belum berhasil' in msg

def test_pdf_refund_cancellation(tmp_path,monkeypatch):
    monkeypatch.setattr(billing_receipt_service,'BUKTI_DIR',tmp_path)
    path=billing_receipt_service.buat_pdf_bukti_refund({
        'status':'berhasil','kode_refund':'RF-CAN-101','payment_id':101,
        'jumlah':Decimal(100000),'nama_siswa':'Siswa','nama_program':'IPA','alasan':'Alasan'})
    assert path.read_bytes().startswith(b'%PDF-')

def test_email_copy_says_cancel_not_reject(tmp_path,monkeypatch):
    path=tmp_path/'bukti.pdf';path.write_bytes(b'%PDF-FAKE')
    for k,v in {'SMTP_HOST':'smtp.example.test','SMTP_PORT':587,'SMTP_USER':'x@example.test','SMTP_PASSWORD':'test'}.items():
        monkeypatch.setattr(billing_receipt_service,k,v)
    sent={}
    class FakeSMTP:
        def __init__(self,*a,**k):pass
        def __enter__(self):return self
        def __exit__(self,*a):return False
        def ehlo(self):pass
        def starttls(self,**k):pass
        def login(self,*a):pass
        def send_message(self,mail):sent['mail']=mail;return {}
    monkeypatch.setattr(billing_receipt_service.smtplib,'SMTP',FakeSMTP)
    detail={'email_siswa':'s@example.com','nama_siswa':'Siswa','nama_program':'IPA','jumlah':Decimal(100000),
            'alasan':'Pindah kota','kode_refund':'RF-CAN-101','jenis_refund':'pembatalan'}
    ok,msg=billing_receipt_service.kirim_pdf_refund_via_email(detail,path)
    assert ok,msg
    plain=sent['mail'].get_body(preferencelist=('plain',)).get_content()
    html=sent['mail'].get_body(preferencelist=('html',)).get_content()
    assert 'dibatalkan oleh admin' in plain and 'Alasan pembatalan' in plain and 'ditolak' not in plain
    assert 'Kelas dibatalkan' in html
