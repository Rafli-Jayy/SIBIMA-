"""Konfirmasi PDF aktivasi enrollment setelah keputusan admin berhasil.

Proses PDF dan email bersifat post-commit: kegagalannya tidak membatalkan
keputusan admin yang telah tersimpan di database.
"""

from __future__ import annotations

import html
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import BUKTI_DIR, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD

NAVY = colors.HexColor("#173B68")
CYAN = colors.HexColor("#11A8B5")
MUTED = colors.HexColor("#64748B")
BORDER = colors.HexColor("#D8DEE8")
PALE = colors.HexColor("#F0F5FC")
GREEN = colors.HexColor("#17653A")
PALE_GREEN = colors.HexColor("#DDF5E5")


def _teks(value) -> str:
    """Melindungi ReportLab Paragraph dari markup data pengguna."""
    return escape(str(value if value is not None and str(value).strip() else "-"))


def _tanggal(value) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%d-%m-%Y %H:%M")
    return str(value or "-")


def _validasi(detail: dict) -> int:
    if not isinstance(detail, dict):
        raise ValueError("Data konfirmasi aktivasi tidak valid.")
    eid = detail.get("enrollment_id")
    if type(eid) is not int or eid <= 0:
        raise ValueError("ID pendaftaran tidak valid.")
    if detail.get("status") != "aktif":
        raise ValueError("PDF aktivasi hanya untuk enrollment berstatus aktif.")
    if not detail.get("processed_at"):
        raise ValueError("Waktu persetujuan belum tersedia.")
    if not str(detail.get("nis") or "").strip():
        raise ValueError("NIS siswa belum tersedia.")
    if not str(detail.get("nama_siswa") or "").strip():
        raise ValueError("Nama siswa belum tersedia.")
    if not str(detail.get("nama_program") or "").strip():
        raise ValueError("Nama program belum tersedia.")
    return eid


def buat_pdf_konfirmasi_aktivasi(detail: dict) -> Path:
    """Hasilkan PDF konfirmasi enrollment aktif, bukan bukti pembayaran."""
    eid = _validasi(detail)
    folder = Path(BUKTI_DIR) / "aktivasi"
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / f"Konfirmasi_Aktivasi_{eid}.pdf"

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="AktBrand", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=22, leading=26, textColor=NAVY, alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name="AktSub", parent=styles["Normal"], fontSize=9, leading=12, textColor=MUTED,
    ))
    styles.add(ParagraphStyle(
        name="AktTitle", parent=styles["Heading1"], fontName="Helvetica-Bold",
        fontSize=16, leading=20, textColor=NAVY, alignment=TA_CENTER,
        spaceBefore=4, spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="AktLabel", parent=styles["Normal"], fontSize=9, leading=12, textColor=MUTED,
    ))
    styles.add(ParagraphStyle(
        name="AktValue", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=10, leading=14, textColor=NAVY,
    ))
    styles.add(ParagraphStyle(
        name="AktBody", parent=styles["Normal"], fontSize=9, leading=14,
        textColor=colors.HexColor("#334155"),
    ))
    styles.add(ParagraphStyle(
        name="AktStatus", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=10, leading=13, textColor=GREEN, alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="AktFooter", parent=styles["Normal"], fontSize=8, leading=12,
        textColor=MUTED, alignment=TA_CENTER,
    ))

    width = A4[0] - 34 * mm
    doc = SimpleDocTemplate(
        str(output), pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm,
        topMargin=16 * mm, bottomMargin=17 * mm,
        title=f"Konfirmasi Aktivasi SIBIMA {eid}", author="SIBIMA KECE",
        subject="Konfirmasi aktivasi kelas bimbingan belajar",
    )

    head = Table([
        [Paragraph("SIBIMA KECE", styles["AktBrand"])],
        [Paragraph("Sistem Informasi Bimbingan Belajar", styles["AktSub"])],
    ], colWidths=[width])
    head.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, -1), (-1, -1), 2, CYAN),
    ]))
    story = [head, Spacer(1, 9 * mm)]
    story.append(Paragraph("KONFIRMASI AKTIVASI KELAS", styles["AktTitle"]))
    story.append(Paragraph("Persetujuan pendaftaran oleh administrator SIBIMA", styles["AktFooter"]))
    story.append(Spacer(1, 5 * mm))
    banner = Table([[Paragraph("PENDAFTARAN DISETUJUI - KELAS AKTIF", styles["AktStatus"])]], colWidths=[width])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_GREEN),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#B7E4C7")),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.extend([banner, Spacer(1, 7 * mm)])

    fields = [
        ("ID pendaftaran", str(eid)),
        ("Nama siswa", detail.get("nama_siswa")),
        ("Nomor Induk Siswa (NIS)", detail.get("nis")),
        ("Program bimbel", detail.get("nama_program")),
        ("Tanggal persetujuan", _tanggal(detail.get("processed_at"))),
        ("Status pendaftaran", "Aktif"),
    ]
    rows = [[Paragraph(label, styles["AktLabel"]), Paragraph(_teks(value), styles["AktValue"])] for label, value in fields]
    table = Table(rows, colWidths=[width * 0.39, width * 0.61], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, 0), (-1, -2), 0.35, BORDER),
    ]))
    story += [table, Spacer(1, 8 * mm)]
    story.append(Paragraph(
        "Pendaftaran program di atas telah disetujui oleh administrator. "
        "Siswa dapat login ke SIBIMA untuk melihat jadwal dan informasi kelas, "
        "sesuai ketentuan akses dan pembayaran yang berlaku.", styles["AktBody"],
    ))
    story += [Spacer(1, 6 * mm), Paragraph(
        "Dokumen ini adalah konfirmasi aktivasi kelas yang diterbitkan oleh sistem SIBIMA, "
        "bukan kuitansi atau bukti transfer bank.", styles["AktBody"],
    ), Spacer(1, 5 * mm), Paragraph("Terima kasih telah belajar bersama SIBIMA KECE.", styles["AktFooter"])]

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(CYAN)
        canvas.line(document.leftMargin, 11 * mm, A4[0] - document.rightMargin, 11 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(document.leftMargin, 7 * mm, "SIBIMA KECE | Konfirmasi aktivasi elektronik")
        canvas.drawRightString(A4[0] - document.rightMargin, 7 * mm, f"Halaman {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output


def kirim_pdf_konfirmasi_aktivasi(detail: dict, pdf_path: str | Path) -> tuple[bool, str]:
    """Kirim email pemberitahuan dan lampiran PDF konfirmasi aktivasi."""
    try:
        _validasi(detail)
    except ValueError as exc:
        return False, str(exc)

    recipient = str(detail.get("email_siswa") or "").strip()
    if not recipient or "\r" in recipient or "\n" in recipient:
        return False, "Alamat email siswa tidak valid."
    if parseaddr(recipient)[1] != recipient or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient):
        return False, "Alamat email siswa tidak valid."
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD or not 1 <= SMTP_PORT <= 65535:
        return False, "Konfigurasi SMTP belum lengkap atau tidak valid."

    path = Path(pdf_path)
    if not path.is_file():
        return False, "File PDF konfirmasi tidak ditemukan."
    try:
        pdf_bytes = path.read_bytes()
    except OSError:
        return False, "File PDF konfirmasi tidak dapat dibaca."
    if not pdf_bytes.startswith(b"%PDF-"):
        return False, "Lampiran bukan dokumen PDF yang valid."

    nama = str(detail.get("nama_siswa") or "Siswa SIBIMA")
    program = str(detail.get("nama_program") or "-")
    tanggal = _tanggal(detail.get("processed_at"))
    eid = detail["enrollment_id"]
    msg = EmailMessage()
    msg["Subject"] = f"Konfirmasi Aktivasi Program SIBIMA - #{eid}"
    msg["From"] = formataddr(("SIBIMA KECE", SMTP_USER))
    msg["To"] = recipient
    msg.set_content(
        f"Halo {nama},\n\n"
        f"Pendaftaran program {program} sudah disetujui pada {tanggal}. "
        "Status kelas kamu sekarang AKTIF. PDF konfirmasi aktivasi terlampir.\n\n"
        "Silakan login ke SIBIMA untuk informasi kelas. Akses kelas tetap mengikuti "
        "ketentuan tagihan dan pembayaran yang berlaku.\n\n"
        "Dokumen ini bukan bukti pembayaran.\n\nTim SIBIMA KECE\n"
    )
    msg.add_alternative(
        "<!doctype html><html lang='id'><body style='margin:0;padding:24px;background:#eef2f7;"
        "font-family:Arial,sans-serif;color:#172033;'>"
        "<table role='presentation' style='max-width:600px;width:100%;margin:auto;background:#fff;"
        "border-collapse:collapse;border-radius:14px;overflow:hidden;'>"
        "<tr><td style='padding:24px;background:#173B68;color:#fff;text-align:center;"
        "font-size:24px;font-weight:bold;'>SIBIMA KECE</td></tr>"
        "<tr><td style='padding:28px;'>"
        "<div style='font-size:12px;font-weight:bold;color:#17653A;'>KELAS AKTIF</div>"
        "<h2 style='color:#173B68;'>Pendaftaran program disetujui!</h2>"
        f"<p>Halo <strong>{html.escape(nama)}</strong>,</p>"
        f"<p>Program <strong>{html.escape(program)}</strong> berhasil diaktifkan pada "
        f"<strong>{html.escape(tanggal)}</strong>.</p>"
        "<p>PDF konfirmasi aktivasi terlampir. Silakan login untuk melihat informasi kelas.</p>"
        "<p style='padding:14px;background:#F0F5FC;font-size:12px;'>"
        "Dokumen ini adalah konfirmasi aktivasi, bukan bukti pembayaran. "
        "Akses akademik mengikuti ketentuan tagihan yang berlaku.</p>"
        "<p>Salam,<br><strong>Tim SIBIMA KECE</strong></p>"
        "</td></tr></table></body></html>",
        subtype="html",
    )
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=path.name)

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
            return False, "Server SMTP menolak alamat penerima."
        return True, "Email aktivasi dan PDF konfirmasi berhasil dikirim."
    except (smtplib.SMTPException, OSError, ValueError) as exc:
        return False, f"Email konfirmasi gagal ({type(exc).__name__}). PDF tetap tersimpan."
