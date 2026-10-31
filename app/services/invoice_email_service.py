"""Pembuatan invoice PDF dan pengiriman email invoice pendaftaran SIBIMA."""
from __future__ import annotations

import html
import re
import smtplib
import ssl
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr, formatdate
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import BASE_DIR, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD

INVOICE_DIR = BASE_DIR / "tagihan"
NAVY = colors.HexColor("#142B4A")
CYAN = colors.HexColor("#12A9BA")
PALE = colors.HexColor("#F1F6FC")
BORDER = colors.HexColor("#DCE5EF")
MUTED = colors.HexColor("#64748B")
AMBER = colors.HexColor("#92400E")
PALE_AMBER = colors.HexColor("#FEF3C7")

_BULAN_ID = (
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
)


def _rupiah(nilai) -> str:
    try:
        amount = Decimal(str(nilai))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    return "Rp " + f"{amount:,.0f}".replace(",", ".")


def _tanggal(nilai) -> str:
    if isinstance(nilai, datetime):
        nilai = nilai.date()
    if isinstance(nilai, date):
        return f"{nilai.day} {_BULAN_ID[nilai.month - 1]} {nilai.year}"
    return str(nilai or "-")


def _periode(nilai) -> str:
    if isinstance(nilai, datetime):
        nilai = nilai.date()
    if isinstance(nilai, date):
        return f"{_BULAN_ID[nilai.month - 1]} {nilai.year}"
    return str(nilai or "-")


def _escape(value) -> str:
    return html.escape(str(value if value is not None and str(value).strip() else "-"))


def _validasi_invoice(invoice: dict) -> tuple[str, Decimal, date | datetime, date | datetime]:
    if not isinstance(invoice, dict):
        raise ValueError("Data invoice tidak valid.")
    if invoice.get("status") != "belum_dibayar":
        raise ValueError("Email invoice hanya dibuat untuk tagihan berstatus belum dibayar.")
    no_invoice = str(invoice.get("no_invoice") or "").strip()
    if not no_invoice or "\r" in no_invoice or "\n" in no_invoice:
        raise ValueError("Nomor invoice tidak valid.")
    try:
        jumlah = Decimal(str(invoice.get("jumlah")))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Nominal invoice tidak valid.") from None
    if not jumlah.is_finite() or jumlah <= 0:
        raise ValueError("Invoice hanya dibuat untuk program berbayar dengan nominal positif.")
    periode = invoice.get("periode")
    jatuh_tempo = invoice.get("jatuh_tempo")
    if periode is None or jatuh_tempo is None:
        raise ValueError("Periode dan tanggal jatuh tempo invoice wajib tersedia.")
    return no_invoice, jumlah, periode, jatuh_tempo


def buat_pdf_invoice_pendaftaran(
    invoice: dict,
    nama_siswa: str,
    email_siswa: str,
    nama_program: str,
) -> Path:
    """Buat PDF invoice belum lunas; bukan kuitansi pembayaran."""
    no_invoice, jumlah, periode, jatuh_tempo = _validasi_invoice(invoice)
    nama_siswa = str(nama_siswa or "Siswa SIBIMA").strip()
    email_siswa = str(email_siswa or "-").strip()
    nama_program = str(nama_program or "Program bimbel").strip()
    INVOICE_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", no_invoice).strip("._") or "invoice"
    output = INVOICE_DIR / f"{safe_name}.pdf"

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="InvoiceBrand", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=23, leading=27, alignment=TA_CENTER, textColor=NAVY, spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="InvoiceSub", parent=styles["Normal"], fontName="Helvetica",
        fontSize=9, leading=12, alignment=TA_CENTER, textColor=MUTED,
    ))
    styles.add(ParagraphStyle(
        name="InvoiceTitle", parent=styles["Heading1"], fontName="Helvetica-Bold",
        fontSize=17, leading=21, alignment=TA_CENTER, textColor=NAVY,
    ))
    styles.add(ParagraphStyle(
        name="SectionLabel", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=10, leading=13, textColor=NAVY, spaceBefore=9, spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="FieldLabel", parent=styles["Normal"], fontSize=8, leading=10,
        textColor=MUTED,
    ))
    styles.add(ParagraphStyle(
        name="FieldValue", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=9, leading=12, textColor=colors.HexColor("#172033"),
    ))
    styles.add(ParagraphStyle(
        name="BodySmall", parent=styles["Normal"], fontSize=8.5, leading=12,
        textColor=colors.HexColor("#334155"),
    ))
    styles.add(ParagraphStyle(
        name="Status", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=9, leading=12, alignment=TA_CENTER, textColor=AMBER,
    ))
    styles.add(ParagraphStyle(
        name="Total", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=21, leading=26, textColor=NAVY,
    ))
    styles.add(ParagraphStyle(
        name="Footer", parent=styles["Normal"], fontSize=8, leading=11,
        alignment=TA_CENTER, textColor=MUTED,
    ))

    width = A4[0] - 34 * mm
    doc = SimpleDocTemplate(
        str(output), pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm,
        topMargin=15 * mm, bottomMargin=17 * mm,
        title=f"Invoice SIBIMA {no_invoice}", author="SIBIMA KECE",
        subject="Invoice tagihan program bimbingan belajar",
    )
    story = []
    brand = Table([
        [Paragraph("SIBIMA KECE", styles["InvoiceBrand"])],
        [Paragraph("Sistem Informasi Bimbingan Belajar", styles["InvoiceSub"])],
    ], colWidths=[width])
    brand.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, -1), (-1, -1), 2, CYAN),
    ]))
    story += [brand, Spacer(1, 7 * mm), Paragraph("INVOICE TAGIHAN", styles["InvoiceTitle"])]

    status = Table([[Paragraph("MENUNGGU PEMBAYARAN", styles["Status"])]], colWidths=[width])
    status.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_AMBER),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#FCD34D")),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story += [status, Spacer(1, 4 * mm)]

    identity = Table([
        [Paragraph("NOMOR INVOICE", styles["FieldLabel"]), Paragraph("DITERBITKAN", styles["FieldLabel"])],
        [Paragraph(_escape(no_invoice), styles["FieldValue"]), Paragraph(_escape(_tanggal(datetime.now().date())), styles["FieldValue"])],
    ], colWidths=[width * 0.62, width * 0.38])
    identity.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [identity, Paragraph("INFORMASI SISWA", styles["SectionLabel"])]

    student = Table([
        [Paragraph("Nama", styles["FieldLabel"]), Paragraph("Email", styles["FieldLabel"])],
        [Paragraph(_escape(nama_siswa), styles["FieldValue"]), Paragraph(_escape(email_siswa), styles["BodySmall"])],
        [Paragraph("Program bimbel", styles["FieldLabel"]), Paragraph("Periode tagihan", styles["FieldLabel"])],
        [Paragraph(_escape(nama_program), styles["FieldValue"]), Paragraph(_escape(_periode(periode)), styles["FieldValue"])],
    ], colWidths=[width * 0.55, width * 0.45])
    student.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 1), (-1, 1), 0.4, BORDER),
    ]))
    story += [student, Paragraph("RINCIAN TAGIHAN", styles["SectionLabel"])]

    details = Table([
        [Paragraph("Nominal tagihan penuh", styles["BodySmall"]), Paragraph(_rupiah(jumlah), styles["FieldValue"])],
        [Paragraph("Jatuh tempo", styles["BodySmall"]), Paragraph(_escape(_tanggal(jatuh_tempo)), styles["FieldValue"])],
        [Paragraph("Metode", styles["BodySmall"]), Paragraph("Simulasi pembayaran internal SIBIMA", styles["BodySmall"])],
    ], colWidths=[width * 0.47, width * 0.53])
    details.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORDER),
    ]))
    story.append(details)
    total = Table([
        [Paragraph("TOTAL YANG PERLU DIBAYAR", styles["FieldLabel"])],
        [Paragraph(_rupiah(jumlah), styles["Total"])],
    ], colWidths=[width])
    total.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story += [Spacer(1, 5 * mm), total, Paragraph("CARA MELANJUTKAN PEMBAYARAN", styles["SectionLabel"])]
    story.append(Paragraph(
        "1. Login ke aplikasi SIBIMA KECE menggunakan akun siswa. &nbsp; "
        "2. Buka menu <b>Tagihan &amp; Pembayaran</b> dan pilih invoice ini. &nbsp; "
        "3. Tekan <b>Bayar Sekarang</b>. Sistem akan menjalankan simulasi pembayaran "
        "dan memperbarui status secara otomatis.",
        styles["BodySmall"],
    ))
    story += [Spacer(1, 4 * mm), Paragraph(
        "PENTING: Invoice ini merupakan tagihan yang belum dibayar, bukan kuitansi. "
        "Pembayaran pada versi SIBIMA ini merupakan simulasi internal dan tidak memindahkan "
        "uang sungguhan atau terhubung ke bank/payment gateway.", styles["BodySmall"]
    ), Spacer(1, 5 * mm), Paragraph("Terima kasih telah belajar bersama SIBIMA KECE.", styles["Footer"])]

    def draw_footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(CYAN)
        canvas.setLineWidth(1)
        canvas.line(document.leftMargin, 11 * mm, A4[0] - document.rightMargin, 11 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(document.leftMargin, 7 * mm, "SIBIMA KECE | Dokumen invoice elektronik")
        canvas.drawRightString(A4[0] - document.rightMargin, 7 * mm, f"Halaman {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return output


def _html_invoice(nama: str, nama_program: str, invoice: dict) -> str:
    no_invoice, jumlah, periode, jatuh_tempo = _validasi_invoice(invoice)
    nama_html = _escape(nama)
    program_html = _escape(nama_program)
    no_html = _escape(no_invoice)
    total_html = _escape(_rupiah(jumlah))
    periode_html = _escape(_periode(periode))
    tempo_html = _escape(_tanggal(jatuh_tempo))
    return f"""<!doctype html>
<html lang=\"id\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Invoice SIBIMA KECE {no_html}</title></head>
<body style=\"margin:0;padding:24px 10px;background:#eef2f7;font-family:Arial,Helvetica,sans-serif;color:#172033;\">
<div style=\"display:none;max-height:0;overflow:hidden;opacity:0;\">Invoice {no_html} untuk program {program_html}; jatuh tempo {tempo_html}.</div>
<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\"><tr><td align=\"center\">
<table role=\"presentation\" width=\"600\" cellspacing=\"0\" cellpadding=\"0\" style=\"width:100%;max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden;\">
<tr><td style=\"background:#142b4a;border-bottom:4px solid #12a9ba;padding:28px;text-align:center;\"><div style=\"font-size:28px;font-weight:800;letter-spacing:1px;color:#ffffff;\">SIBIMA <span style=\"color:#67e8f9;\">KECE</span></div><div style=\"font-size:11px;letter-spacing:2px;color:#cbd5e1;margin-top:7px;\">INVOICE PROGRAM BIMBEL</div></td></tr>
<tr><td style=\"padding:28px;\"><div style=\"font-size:11px;font-weight:bold;letter-spacing:1px;color:#92400e;\">PENDAFTARAN TERCATAT · MENUNGGU PEMBAYARAN</div>
<h1 style=\"margin:10px 0 8px;color:#142b4a;font-size:24px;line-height:1.35;\">Pendaftaran program kamu berhasil dicatat!</h1>
<p style=\"margin:0 0 20px;color:#475569;font-size:15px;line-height:1.8;\">Halo, <strong>{nama_html}</strong>. Pendaftaranmu untuk program <strong>{program_html}</strong> berhasil dicatat. Invoice otomatis dibuat dan dilampirkan pada email ini.</p>
<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"background:#f1f6fc;border:1px solid #dce5ef;border-radius:12px;\"><tr><td style=\"padding:18px 20px;\"><div style=\"font-size:11px;color:#64748b;letter-spacing:1px;\">TOTAL TAGIHAN</div><div style=\"font-size:28px;font-weight:800;color:#142b4a;margin-top:7px;\">{total_html}</div><div style=\"margin-top:10px;font-size:13px;color:#475569;\">Nomor invoice: <strong>{no_html}</strong></div><div style=\"margin-top:5px;font-size:13px;color:#475569;\">Periode: {periode_html}</div><div style=\"margin-top:5px;font-size:13px;color:#92400e;\">Jatuh tempo: <strong>{tempo_html}</strong></div></td></tr></table>
<h2 style=\"margin:24px 0 8px;font-size:16px;color:#142b4a;\">Langkah pembayaran</h2><ol style=\"padding-left:21px;color:#475569;font-size:14px;line-height:1.8;\"><li>Login ke aplikasi SIBIMA KECE.</li><li>Buka menu <strong>Tagihan &amp; Pembayaran</strong> dan pilih invoice {no_html}.</li><li>Tekan <strong>Bayar Sekarang</strong> untuk menjalankan simulasi pembayaran otomatis.</li><li>Sistem akan menampilkan hasil simulasi berhasil atau gagal dan memperbarui status invoice secara otomatis.</li></ol>
<div style=\"margin-top:20px;padding:14px 16px;border-left:4px solid #f59e0b;background:#fffbeb;color:#78350f;font-size:12px;line-height:1.7;\"><strong>Catatan:</strong> Invoice terlampir adalah tagihan, bukan bukti pembayaran lunas. Pembayaran pada versi SIBIMA ini hanya simulasi internal dan tidak memindahkan uang sungguhan atau terhubung ke bank/payment gateway.</div>
<p style=\"margin-top:26px;color:#334155;font-size:14px;line-height:1.8;\">Salam hangat,<br><strong>Tim SIBIMA KECE</strong></p></td></tr>
<tr><td style=\"padding:18px 24px;background:#f8fafc;border-top:1px solid #e2e8f0;text-align:center;font-size:11px;line-height:1.7;color:#64748b;\">Email otomatis dari SIBIMA KECE.<br>Jika pesan ini masuk Spam, periksa autentikasi domain dan gunakan tombol “Bukan spam” setelah memastikan email memang berasal dari SIBIMA.</td></tr>
</table></td></tr></table></body></html>"""


def kirim_email_tagihan_bulanan(
    email: str,
    nama: str,
    nama_program: str,
    invoice: dict,
) -> tuple[bool, str]:
    """Buat PDF dan kirim email tagihan bulanan dengan keterangan simulasi."""
    try:
        no_invoice, jumlah, periode, jatuh_tempo = _validasi_invoice(invoice)
    except ValueError as exc:
        return False, str(exc)
    recipient = str(email or "").strip()
    try:
        pdf_path = buat_pdf_invoice_pendaftaran(invoice, nama, recipient or "-", nama_program)
    except Exception as exc:
        return False, f"Invoice tersimpan, tetapi PDF gagal dibuat ({type(exc).__name__})."
    if not recipient or "\r" in recipient or "\n" in recipient:
        return False, f"PDF tersimpan di {pdf_path}, tetapi alamat email siswa tidak valid."
    parsed = parseaddr(recipient)[1]
    if parsed != recipient or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient):
        return False, f"PDF tersimpan di {pdf_path}, tetapi alamat email siswa tidak valid."
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD or not 1 <= SMTP_PORT <= 65535:
        return False, f"PDF tersimpan di {pdf_path}, tetapi konfigurasi SMTP belum lengkap/valid."
    msg = EmailMessage()
    msg["Subject"] = f"Tagihan Bulanan SIBIMA KECE | {no_invoice}"
    msg["From"] = formataddr(("SIBIMA KECE", SMTP_USER))
    msg["To"] = recipient
    msg.set_content(
        f"Halo {nama or 'Siswa SIBIMA'},\n\nTagihan bulanan program {nama_program} "
        f"sebesar {_rupiah(jumlah)} untuk periode {_periode(periode)} telah diterbitkan. "
        f"Nomor invoice: {no_invoice}. Jatuh tempo: {_tanggal(jatuh_tempo)}.\n\n"
        "Buka menu Tagihan & Pembayaran dan tekan Bayar Sekarang untuk menjalankan simulasi. "
        "Simulasi ini tidak memindahkan uang sungguhan. Invoice PDF terlampir.\n\nTim SIBIMA KECE"
    )
    msg.add_alternative(
        f"""<!doctype html><html lang='id'><body style='margin:0;padding:24px;background:#eef2f7;font-family:Arial,sans-serif;color:#172033;'>
        <table role='presentation' style='max-width:600px;width:100%;margin:auto;background:#fff;border-radius:14px;border-collapse:collapse;overflow:hidden;'>
        <tr><td style='padding:24px;background:#142b4a;color:#fff;text-align:center;font-size:22px;font-weight:bold;'>SIBIMA KECE</td></tr>
        <tr><td style='padding:28px;'><p style='color:#92400e;font-size:12px;font-weight:bold;'>TAGIHAN BULANAN BARU</p>
        <h2 style='color:#142b4a;margin:8px 0;'>Tagihan bulan ini telah diterbitkan</h2><p>Halo <strong>{_escape(nama)}</strong>, tagihan program <strong>{_escape(nama_program)}</strong> untuk periode {_escape(_periode(periode))} sudah tersedia.</p>
        <div style='background:#f1f6fc;padding:18px;border-radius:10px;'><div style='font-size:12px;color:#64748b;'>TOTAL TAGIHAN</div><div style='font-size:25px;font-weight:bold;color:#142b4a;'>{_escape(_rupiah(jumlah))}</div><div style='font-size:12px;color:#64748b;margin-top:8px;'>Invoice: {_escape(no_invoice)} · Jatuh tempo: {_escape(_tanggal(jatuh_tempo))}</div></div>
        <p>Buka menu <strong>Tagihan &amp; Pembayaran</strong>, pilih invoice ini, lalu tekan <strong>Bayar Sekarang</strong>. Sistem akan menjalankan simulasi otomatis.</p>
        <p style='padding:12px;background:#fffbeb;color:#92400e;font-size:12px;'>Pembayaran ini hanya simulasi internal SIBIMA. Tidak ada uang sungguhan yang dipindahkan.</p>
        <p>Invoice PDF terlampir.<br>Salam,<br><strong>Tim SIBIMA KECE</strong></p></td></tr></table></body></html>""",
        subtype="html",
    )
    try:
        msg.add_attachment(pdf_path.read_bytes(), maintype="application", subtype="pdf", filename=pdf_path.name)
    except OSError:
        return False, f"PDF invoice tidak dapat dibaca: {pdf_path}"
    context = ssl.create_default_context()
    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=context) as server:
                server.login(SMTP_USER, SMTP_PASSWORD); refused = server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                server.ehlo(); server.starttls(context=context); server.ehlo()
                server.login(SMTP_USER, SMTP_PASSWORD); refused = server.send_message(msg)
        return (not refused, "Email tagihan bulanan dikirim." if not refused else "SMTP menolak penerima.")
    except (smtplib.SMTPException, OSError, ValueError) as exc:
        return False, f"Email tagihan bulanan gagal ({type(exc).__name__}); PDF tersimpan di {pdf_path}."


def kirim_email_invoice_pendaftaran(
    email: str,
    nama: str,
    nama_program: str,
    invoice: dict,
) -> tuple[bool, str]:
    """Buat invoice PDF dan kirim email HTML segera setelah pendaftaran dicatat."""
    try:
        no_invoice, jumlah, periode, jatuh_tempo = _validasi_invoice(invoice)
    except ValueError as exc:
        return False, str(exc)

    recipient = str(email or "").strip()
    # Generate the invoice document even if the recipient address or SMTP setup
    # is invalid, so the approved invoice still has a local PDF for follow-up.
    try:
        pdf_path = buat_pdf_invoice_pendaftaran(invoice, nama, recipient or "-", nama_program)
    except Exception as exc:
        return False, f"Invoice tersimpan di database, tetapi PDF gagal dibuat ({type(exc).__name__})."

    if not recipient or "\r" in recipient or "\n" in recipient:
        return False, f"PDF invoice tersimpan di {pdf_path}, tetapi alamat email siswa tidak valid."
    parsed = parseaddr(recipient)[1]
    if parsed != recipient or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient):
        return False, f"PDF invoice tersimpan di {pdf_path}, tetapi alamat email siswa tidak valid."

    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        return False, f"PDF invoice tersimpan di {pdf_path}, tetapi konfigurasi SMTP belum lengkap."
    if not 1 <= SMTP_PORT <= 65535:
        return False, f"PDF invoice tersimpan di {pdf_path}, tetapi SMTP_PORT tidak valid."

    subject = f"Invoice SIBIMA KECE | {no_invoice}"
    text_body = (
        f"Halo, {nama or 'Siswa SIBIMA'}!\n\n"
        f"Pendaftaran program {nama_program} berhasil dicatat. Invoice {no_invoice} "
        f"sebesar {_rupiah(jumlah)} untuk periode {_periode(periode)} dibuat otomatis. "
        f"Jatuh tempo: {_tanggal(jatuh_tempo)}.\n\n"
        "Invoice PDF terlampir. Untuk membayar, login ke aplikasi SIBIMA KECE, buka "
        "menu Tagihan & Pembayaran, pilih invoice ini, lalu tekan Bayar Sekarang. Sistem "
        "menjalankan simulasi dan memperbarui status secara otomatis.\n\n"
        "Catatan: Pembayaran pada versi ini hanya simulasi internal; tidak ada uang "
        "sungguhan yang dipindahkan dan tidak ada koneksi bank/payment gateway. Invoice bukan bukti pembayaran lunas.\n\n"
        "Salam hangat,\nTim SIBIMA KECE\n"
    )
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("SIBIMA KECE", SMTP_USER))
    msg["To"] = recipient
    msg["Reply-To"] = SMTP_USER
    msg["Date"] = formatdate(localtime=True)
    sender_domain = SMTP_USER.rsplit("@", 1)[-1] if "@" in SMTP_USER else None
    msg["Message-ID"] = make_msgid(domain=sender_domain) if sender_domain else make_msgid()
    msg.set_content(text_body)
    msg.add_alternative(_html_invoice(nama, nama_program, invoice), subtype="html")
    try:
        attachment = pdf_path.read_bytes()
    except OSError:
        return False, f"PDF invoice tidak dapat dibaca: {pdf_path}"
    msg.add_attachment(
        attachment, maintype="application", subtype="pdf", filename=pdf_path.name
    )

    context = ssl.create_default_context()
    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=context) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                refused = server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASSWORD)
                refused = server.send_message(msg)
        if refused:
            return False, f"PDF invoice tersimpan di {pdf_path}, tetapi SMTP menolak penerima."
        return True, f"Invoice {no_invoice} dikirim melalui SMTP ke {recipient}; PDF: {pdf_path}."
    except (smtplib.SMTPException, OSError, ValueError) as exc:
        return False, (
            f"PDF invoice tersimpan di {pdf_path}, tetapi email gagal dikirim "
            f"({type(exc).__name__})."
        )
