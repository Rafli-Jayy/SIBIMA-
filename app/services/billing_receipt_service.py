"""Pembuatan PDF kuitansi dan pengiriman email bukti pembayaran SIBIMA."""

from __future__ import annotations

import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import BUKTI_DIR, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD

NAVY = colors.HexColor("#173B68")
CYAN = colors.HexColor("#11A8B5")
PALE = colors.HexColor("#F0F5FC")
BORDER = colors.HexColor("#D8DEE8")
MUTED = colors.HexColor("#64748B")
GREEN = colors.HexColor("#17653A")
PALE_GREEN = colors.HexColor("#DDF5E5")


def _plain(value) -> str:
    """Escape data from the database before using it inside ReportLab Paragraph."""
    return escape(str(value if value is not None and str(value).strip() else "-"))


def _rupiah(value) -> str:
    try:
        nominal = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        nominal = 0
    return f"Rp{nominal:,.0f}".replace(",", ".")


def _tanggal(value) -> str:
    if value is None:
        return "-"
    if hasattr(value, "strftime"):
        return value.strftime("%d-%m-%Y %H:%M")
    return str(value)


def _periode(value) -> str:
    if value is None:
        return "-"
    if hasattr(value, "month") and hasattr(value, "year"):
        bulan = (
            "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember",
        )
        return f"{bulan[value.month - 1]} {value.year}"
    return str(value)


def buat_pdf_bukti(detail: dict) -> Path:
    """Generate a one-page PDF receipt for an already-approved payment."""
    if not isinstance(detail, dict):
        raise ValueError("Data bukti pembayaran tidak valid.")
    if detail.get("payment_status") != "lunas":
        raise ValueError("Bukti PDF hanya dapat dibuat untuk pembayaran berstatus LUNAS.")

    try:
        payment_id = int(detail["payment_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("ID pembayaran pada bukti tidak valid.") from exc
    if payment_id <= 0:
        raise ValueError("ID pembayaran pada bukti tidak valid.")

    folder = Path(BUKTI_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    safe_invoice = re.sub(r"[^A-Za-z0-9_-]", "_", str(detail.get("no_invoice") or "invoice"))
    output_path = folder / f"Bukti_{payment_id}_{safe_invoice}.pdf"

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="Brand", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=19, leading=22, textColor=NAVY, alignment=TA_LEFT,
        spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="SubBrand", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8.5, leading=11, textColor=MUTED,
    ))
    styles.add(ParagraphStyle(
        name="ReceiptTitle", parent=styles["Heading1"], fontName="Helvetica-Bold",
        fontSize=15, leading=19, textColor=NAVY, alignment=TA_CENTER,
        spaceBefore=7, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="SectionLabel", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=9, leading=12, textColor=NAVY, spaceBefore=7, spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="FieldLabel", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8, leading=10, textColor=MUTED,
    ))
    styles.add(ParagraphStyle(
        name="FieldValue", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=9, leading=12, textColor=colors.HexColor("#172033"),
    ))
    styles.add(ParagraphStyle(
        name="NormalSmall", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8.2, leading=11, textColor=colors.HexColor("#334155"),
    ))
    styles.add(ParagraphStyle(
        name="TotalLabel", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=9, leading=12, textColor=colors.HexColor("#475569"),
    ))
    styles.add(ParagraphStyle(
        name="TotalValue", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=20, leading=24, textColor=NAVY,
    ))
    styles.add(ParagraphStyle(
        name="Status", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=9, leading=12, textColor=GREEN, alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="CenterSmall", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8, leading=11, textColor=MUTED, alignment=TA_CENTER,
    ))

    width = A4[0] - 34 * mm
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        rightMargin=17 * mm, leftMargin=17 * mm,
        topMargin=15 * mm, bottomMargin=16 * mm,
        title=f"Bukti Pembayaran {_plain(detail.get('no_invoice'))}",
        author="SIBIMA KECE",
        subject="Bukti pembayaran terverifikasi oleh admin SIBIMA",
    )

    story = []
    brand = Table([
        [Paragraph("SIBIMA KECE", styles["Brand"])],
        [Paragraph("Sistem Informasi Bimbingan Belajar", styles["SubBrand"])],
    ], colWidths=[width])
    brand.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LINEBELOW", (0, -1), (-1, -1), 2, NAVY),
    ]))
    story.extend([brand, Spacer(1, 7 * mm)])
    story.append(Paragraph("BUKTI PEMBAYARAN", styles["ReceiptTitle"]))
    story.append(Paragraph(f"No. kuitansi: {_plain(detail.get('no_invoice'))}", styles["CenterSmall"]))
    story.append(Spacer(1, 3 * mm))
    status_box = Table([[Paragraph("LUNAS - TELAH DIVERIFIKASI ADMIN", styles["Status"])]], colWidths=[width])
    status_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_GREEN),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#B7E4C7")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(status_box)

    story.append(Paragraph("INFORMASI SISWA", styles["SectionLabel"]))
    student_rows = [
        [Paragraph("Nama siswa", styles["FieldLabel"]), Paragraph("NIS", styles["FieldLabel"])],
        [Paragraph(_plain(detail.get("nama_siswa")), styles["FieldValue"]), Paragraph(_plain(detail.get("nis")), styles["FieldValue"])],
        [Paragraph("Program bimbel", styles["FieldLabel"]), Paragraph("Periode tagihan", styles["FieldLabel"])],
        [Paragraph(_plain(detail.get("nama_program")), styles["FieldValue"]), Paragraph(_plain(_periode(detail.get("periode"))), styles["FieldValue"])],
    ]
    student = Table(student_rows, colWidths=[width * 0.62, width * 0.38])
    student.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 1), (-1, 1), 0.5, BORDER),
        ("LINEBELOW", (0, 3), (-1, 3), 0.5, BORDER),
    ]))
    story.append(student)

    story.append(Paragraph("RINCIAN PEMBAYARAN", styles["SectionLabel"]))
    payment_rows = [
        [Paragraph("Nomor tagihan", styles["NormalSmall"]), Paragraph(_plain(detail.get("no_invoice")), styles["NormalSmall"])],
        [Paragraph("ID pembayaran", styles["NormalSmall"]), Paragraph(str(payment_id), styles["NormalSmall"])],
        [Paragraph("Metode", styles["NormalSmall"]), Paragraph("Virtual Account (referensi internal)", styles["NormalSmall"])],
        [Paragraph("Tanggal dilaporkan", styles["NormalSmall"]), Paragraph(_plain(_tanggal(detail.get("paid_at"))), styles["NormalSmall"])],
        [Paragraph("Tanggal verifikasi admin", styles["NormalSmall"]), Paragraph(_plain(_tanggal(detail.get("processed_at"))), styles["NormalSmall"])],
    ]
    payments = Table(payment_rows, colWidths=[width * 0.42, width * 0.58])
    payments.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.35, BORDER),
    ]))
    story.append(payments)
    story.append(Spacer(1, 5 * mm))

    total = Table([
        [Paragraph("TOTAL PEMBAYARAN", styles["TotalLabel"])],
        [Paragraph(_rupiah(detail.get("payment_jumlah") or detail.get("invoice_jumlah") or 0), styles["TotalValue"])],
    ], colWidths=[width])
    total.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(total)
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(
        "Dokumen ini diterbitkan oleh sistem SIBIMA setelah pembayaran disetujui oleh admin. "
        "Virtual Account pada versi ini merupakan referensi internal dan bukan bukti transaksi "
        "yang diterbitkan bank atau payment gateway.", styles["NormalSmall"]
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Terima kasih telah belajar bersama SIBIMA KECE.", styles["CenterSmall"]))

    def draw_page(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(CYAN)
        canvas.setLineWidth(1.2)
        canvas.line(document.leftMargin, 10 * mm, A4[0] - document.rightMargin, 10 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(document.leftMargin, 6 * mm, "SIBIMA KECE | Dokumen elektronik")
        canvas.drawRightString(A4[0] - document.rightMargin, 6 * mm, f"Halaman {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return output_path


def kirim_pdf_via_email(detail: dict, pdf_path: str | Path) -> tuple[bool, str]:
    """Send the receipt to the email registered on the user's SIBIMA account."""
    if not isinstance(detail, dict) or detail.get("payment_status") != "lunas":
        return False, "Email bukti hanya bisa dikirim untuk pembayaran berstatus LUNAS."

    recipient = str(detail.get("email_siswa") or "").strip()
    if not recipient or "\r" in recipient or "\n" in recipient:
        return False, "Email siswa belum tersedia atau formatnya tidak valid. Periksa data akun siswa."
    parsed = parseaddr(recipient)[1]
    if parsed != recipient or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient):
        return False, "Alamat email pada akun siswa tidak valid. Periksa data akun siswa."

    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        return False, "Konfigurasi SMTP belum lengkap. Isi SMTP_HOST, SMTP_PORT, SMTP_USER, dan SMTP_PASSWORD di .env."
    if not 1 <= SMTP_PORT <= 65535:
        return False, "Port SMTP tidak valid. Periksa SMTP_PORT di .env."

    path = Path(pdf_path)
    if not path.is_file():
        return False, "File PDF bukti pembayaran tidak ditemukan."
    try:
        attachment = path.read_bytes()
    except OSError:
        return False, "File PDF bukti pembayaran tidak dapat dibaca."

    invoice_no = str(detail.get("no_invoice") or "-")
    student_name = str(detail.get("nama_siswa") or "Siswa SIBIMA")
    msg = EmailMessage()
    msg["Subject"] = f"Bukti Pembayaran SIBIMA KECE - {invoice_no}"
    msg["From"] = formataddr(("SIBIMA KECE", SMTP_USER))
    msg["To"] = recipient
    msg.set_content(
        f"Halo {student_name},\n\n"
        f"Terlampir bukti PDF untuk pembayaran tagihan {invoice_no} yang telah diverifikasi "
        "dan dinyatakan lunas oleh admin SIBIMA.\n\n"
        "Catatan: kode Virtual Account pada versi SIBIMA ini merupakan referensi internal, "
        "bukan bukti transfer yang diterbitkan bank.\n\n"
        "Salam,\nTim SIBIMA KECE\n"
    )
    msg.add_attachment(attachment, maintype="application", subtype="pdf", filename=path.name)

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
            return False, "Server SMTP menolak alamat email penerima. Periksa email akun siswa."
        return True, f"Bukti pembayaran dikirim ke {recipient}."
    except (smtplib.SMTPException, OSError, ValueError) as exc:
        return False, f"Email gagal dikirim ({type(exc).__name__}). PDF tetap tersimpan di {path}."
