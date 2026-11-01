
"""Pengiriman email OTP SIBIMA KECE melalui SMTP atau simulasi."""

import html
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from app.config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    OTP_EXPIRE_MINUTES,
)

console = Console()

NAMA_PENGIRIM = "SIBIMA KECE"



def kirim_notifikasi_status(
    email: str,
    nama: str,
    kategori: str,
    status: str,
    detail: str | None = None,
) -> bool:
    """Mengirim email notifikasi setelah status akun atau pendaftaran berubah.

    kategori: 'akun' atau 'pendaftaran'
    status: 'aktif' atau 'ditolak'
    detail: nama program atau alasan penolakan.
    """
    if not isinstance(email, str) or not email.strip():
        return False

    if "\r" in email or "\n" in email:
        return False

    if kategori not in {"akun", "pendaftaran"}:
        return False

    if status not in {"aktif", "ditolak"}:
        return False

    nama = str(nama or "Pengguna SIBIMA").strip()
    detail = str(detail or "").strip()

    if kategori == "akun" and status == "aktif":
        subjek = "Akun SIBIMA KECE Berhasil Disetujui"
        judul = "Akun kamu sudah aktif!"
        isi = (
            "Selamat! Pendaftaran akun SIBIMA KECE kamu telah "
            "disetujui oleh administrator. Kamu sekarang dapat "
            "login menggunakan akun yang sudah didaftarkan."
        )
        label = "AKUN AKTIF"
        warna = "#059669"

    elif kategori == "akun" and status == "ditolak":
        subjek = "Informasi Hasil Pendaftaran Akun SIBIMA KECE"
        judul = "Pendaftaran akun belum disetujui"
        isi = (
            "Mohon maaf, pendaftaran akun SIBIMA KECE kamu "
            "belum dapat disetujui oleh administrator."
        )
        label = "PENDAFTARAN DITOLAK"
        warna = "#dc2626"

    elif kategori == "pendaftaran" and status == "aktif":
        subjek = "Pendaftaran Program SIBIMA KECE Disetujui"
        judul = "Pendaftaran program berhasil!"
        isi = (
            "Pendaftaran program bimbel kamu telah disetujui. "
            "Silakan login ke SIBIMA KECE untuk melihat jadwal "
            "dan informasi pembelajaran yang tersedia."
        )
        label = "PESERTA AKTIF"
        warna = "#059669"

    else:
        subjek = "Informasi Pendaftaran Program SIBIMA KECE"
        judul = "Hasil pendaftaran program"
        isi = (
            "Mohon maaf, pendaftaran program bimbel kamu "
            "belum dapat disetujui oleh administrator."
        )
        label = "PENDAFTARAN DITOLAK"
        warna = "#dc2626"

    nama_html = html.escape(nama)
    isi_html = html.escape(isi)
    detail_html = html.escape(detail)
    label_html = html.escape(label)

    bagian_detail_html = ""
    bagian_detail_teks = ""

    if detail:
        bagian_detail_html = f"""
        <div style="margin-top:22px;padding:16px;
                    border-radius:10px;background:#f1f5f9;
                    color:#334155;line-height:1.7;">
          <strong>Informasi tambahan</strong><br>
          {detail_html}
        </div>
        """
        bagian_detail_teks = f"\nInformasi tambahan:\n{detail}\n"

    isi_teks = (
        f"Halo, {nama}!\n\n"
        f"{isi}\n\n"
        f"Status: {label}\n"
        f"{bagian_detail_teks}\n"
        "Salam hangat,\nTim SIBIMA KECE\n\n"
        "Email otomatis. Mohon jangan membalas email ini."
    )

    isi_html_email = f"""\
<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(subjek)}</title>
</head>
<body style="margin:0;padding:28px 12px;background:#eef2f7;
             font-family:Arial,Helvetica,sans-serif;color:#172033;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr><td align="center">
      <table role="presentation" width="580" cellspacing="0" cellpadding="0"
             style="width:100%;max-width:580px;background:#ffffff;
                    border-radius:16px;overflow:hidden;">
        <tr>
          <td align="center" style="padding:30px;background:#101b35;
                     border-bottom:4px solid #22d3ee;">
            <div style="font-size:29px;font-weight:800;color:#ffffff;">
              SIBIMA <span style="color:#67e8f9;">KECE</span>
            </div>
            <div style="margin-top:9px;font-size:11px;letter-spacing:2px;
                        color:#cbd5e1;">
              INFORMASI STATUS AKUN
            </div>
          </td>
        </tr>
        <tr>
          <td style="padding:30px;">
            <div style="font-size:11px;font-weight:bold;letter-spacing:1px;
                        color:{warna};">
              {label_html}
            </div>
            <h1 style="font-size:25px;line-height:1.4;color:#101b35;">
              {html.escape(judul)}
            </h1>
            <p style="font-size:15px;line-height:1.8;color:#475569;">
              Halo, <strong>{nama_html}</strong>!
            </p>
            <p style="font-size:15px;line-height:1.8;color:#475569;">
              {isi_html}
            </p>
            {bagian_detail_html}
            <p style="margin-top:28px;font-size:14px;line-height:1.8;
                      color:#334155;">
              Salam hangat,<br><strong>Tim SIBIMA KECE</strong>
            </p>
          </td>
        </tr>
        <tr>
          <td align="center" style="padding:20px;background:#f8fafc;
                     border-top:1px solid #e2e8f0;font-size:11px;
                     line-height:1.8;color:#94a3b8;">
            Email otomatis dari SIBIMA KECE.<br>
            Mohon jangan membalas email ini.
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""

    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        console.print(
            "[red]SMTP belum lengkap. Notifikasi tidak terkirim.[/red]"
        )
        return False

    if not 1 <= SMTP_PORT <= 65535:
        console.print("[red]Port SMTP tidak valid.[/red]")
        return False

    pesan = EmailMessage()
    pesan["Subject"] = subjek
    pesan["From"] = formataddr(("SIBIMA KECE", SMTP_USER))
    pesan["To"] = email.strip()
    pesan.set_content(isi_teks)
    pesan.add_alternative(isi_html_email, subtype="html")

    konteks_ssl = ssl.create_default_context()

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(
                SMTP_HOST,
                SMTP_PORT,
                timeout=15,
                context=konteks_ssl,
            ) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                ditolak = server.send_message(pesan)
        else:
            with smtplib.SMTP(
                SMTP_HOST,
                SMTP_PORT,
                timeout=15,
            ) as server:
                server.ehlo()
                server.starttls(context=konteks_ssl)
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASSWORD)
                ditolak = server.send_message(pesan)

        if ditolak:
            return False

        console.print(
            "[green]Email notifikasi SIBIMA KECE berhasil dikirim.[/green]"
        )
        return True

    except (smtplib.SMTPException, OSError, ValueError) as exc:
        console.print(
            f"[red]Notifikasi email gagal ({type(exc).__name__}).[/red]"
        )
        return False


def tampilkan_otp_simulasi(kode: str) -> None:
    """Menampilkan OTP di terminal untuk pengembangan."""
    if not isinstance(kode, str) or not kode.isascii() or not kode.isdigit():
        raise ValueError("Kode OTP harus berupa angka.")

    isi = Text()
    isi.append("Kode OTP kamu:\n", style="white")
    isi.append(kode, style="bold bright_cyan")
    isi.append(
        f"\n\nBerlaku selama {OTP_EXPIRE_MINUTES} menit.",
        style="dim",
    )

    console.print(
        Panel(
            isi,
            title=f"[bold cyan]{NAMA_PENGIRIM}[/bold cyan]",
            subtitle="[dim]MODE SIMULASI[/dim]",
            border_style="cyan",
            padding=(1, 4),
            expand=False,
        )
    )


def _buat_html_email(kode: str) -> str:
    """Membuat template email HTML yang ramah untuk klien email."""
    kode_html = html.escape(kode)
    masa_berlaku = html.escape(str(OTP_EXPIRE_MINUTES))

    return f"""\
<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Verifikasi Email SIBIMA KECE</title>
</head>
<body style="margin:0;padding:0;background-color:#eef2f7;
             font-family:Arial,Helvetica,sans-serif;color:#172033;">

  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">
    Kode verifikasi akun SIBIMA KECE kamu sudah siap.
    Kode berlaku selama {masa_berlaku} menit.
  </div>

  <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
         style="background-color:#eef2f7;padding:32px 12px;">
    <tr>
      <td align="center">

        <table role="presentation" width="600" cellspacing="0"
               cellpadding="0"
               style="width:100%;max-width:600px;background:#ffffff;
                      border-radius:18px;overflow:hidden;
                      box-shadow:0 8px 30px rgba(15,23,42,0.08);">

          <!-- HEADER -->
          <tr>
            <td style="background:#101b35;padding:34px 28px;
                       text-align:center;border-bottom:4px solid #22d3ee;">

              <div style="font-size:12px;letter-spacing:4px;
                          color:#67e8f9;font-weight:bold;">
                SISTEM INFORMASI BIMBINGAN BELAJAR
              </div>

              <div style="margin-top:12px;font-size:34px;
                          line-height:1.2;font-weight:800;color:#ffffff;">
                SIBIMA <span style="color:#67e8f9;">KECE</span>
              </div>

              <div style="margin-top:12px;font-size:13px;
                          letter-spacing:2px;color:#cbd5e1;">
                EMAIL VERIFICATION
              </div>
            </td>
          </tr>

          <!-- CONTENT -->
          <tr>
            <td style="padding:34px 28px 18px;">

              <div style="display:inline-block;background:#ecfeff;
                          color:#0e7490;padding:8px 12px;
                          border-radius:20px;font-size:11px;
                          font-weight:bold;letter-spacing:1px;">
                LANGKAH KEAMANAN AKUN
              </div>

              <h1 style="font-size:25px;line-height:1.35;
                         color:#101b35;margin:22px 0 12px;">
                Verifikasi email kamu ✨
              </h1>

              <p style="font-size:15px;line-height:1.8;
                        color:#475569;margin:0 0 16px;">
                Halo, pengguna SIBIMA!
              </p>

              <p style="font-size:15px;line-height:1.8;
                        color:#475569;margin:0 0 24px;">
                Terima kasih sudah mendaftar di
                <strong>SIBIMA KECE</strong>. Masukkan kode berikut
                untuk memverifikasi alamat email dan melanjutkan
                proses aktivasi akunmu.
              </p>

              <!-- OTP CARD -->
              <table role="presentation" width="100%" cellspacing="0"
                     cellpadding="0"
                     style="background:#f0f9ff;border:1px solid #bae6fd;
                            border-radius:15px;">
                <tr>
                  <td align="center" style="padding:26px 12px;">

                    <div style="font-size:12px;font-weight:bold;
                                letter-spacing:2px;color:#0369a1;">
                      KODE VERIFIKASI OTP
                    </div>

                    <div style="margin:20px 0;padding:18px 10px;
                                background:#ffffff;border:1px dashed #38bdf8;
                                border-radius:12px;color:#0f172a;
                                font-size:36px;font-weight:800;
                                letter-spacing:9px;">
                      {kode_html}
                    </div>

                    <div style="font-size:13px;line-height:1.7;
                                color:#475569;">
                      Kode berlaku selama
                      <strong>{masa_berlaku} menit</strong>
                      sejak diterbitkan.
                    </div>

                  </td>
                </tr>
              </table>

              <!-- SECURITY WARNING -->
              <table role="presentation" width="100%" cellspacing="0"
                     cellpadding="0"
                     style="margin-top:24px;background:#fff7ed;
                            border-left:4px solid #f59e0b;">
                <tr>
                  <td style="padding:16px 18px;">
                    <div style="font-size:14px;font-weight:bold;
                                color:#9a3412;margin-bottom:6px;">
                      Jaga keamanan akunmu
                    </div>
                    <div style="font-size:13px;line-height:1.8;
                                color:#7c2d12;">
                      Jangan bagikan kode OTP ini kepada siapa pun,
                      termasuk orang yang mengaku sebagai petugas.
                      Tim SIBIMA tidak akan meminta kode OTP kamu.
                    </div>
                  </td>
                </tr>
              </table>

              <p style="margin:24px 0 8px;font-size:13px;
                        line-height:1.8;color:#64748b;">
                Jika kamu tidak merasa melakukan pendaftaran atau
                meminta kode ini, abaikan email ini. Jangan bagikan
                kode kepada siapa pun.
              </p>

              <p style="font-size:14px;line-height:1.8;
                        color:#334155;margin:24px 0 8px;">
                Semangat belajar dan berkembang!
              </p>

              <p style="font-size:14px;line-height:1.8;
                        color:#334155;margin:0 0 28px;">
                Salam hangat,<br>
                <strong style="color:#0e7490;">Tim SIBIMA KECE</strong>
              </p>

            </td>
          </tr>

          <!-- FOOTER -->
          <tr>
            <td style="background:#f8fafc;border-top:1px solid #e2e8f0;
                       padding:22px 24px;text-align:center;">

              <div style="font-size:12px;font-weight:bold;
                          color:#334155;">
                SIBIMA KECE
              </div>

              <div style="font-size:11px;line-height:1.8;
                          color:#94a3b8;margin-top:8px;">
                Email otomatis untuk verifikasi akun.<br>
                Mohon jangan membalas email ini.
              </div>

            </td>
          </tr>

        </table>

        <div style="max-width:560px;font-size:11px;line-height:1.7;
                    color:#94a3b8;text-align:center;padding:18px 8px;">
          Pesan ini dikirim untuk membantu menjaga keamanan akun
          SIBIMA KECE kamu.
        </div>

      </td>
    </tr>
  </table>

</body>
</html>
"""


def kirim_otp_email(email: str, kode: str) -> bool:
    """Mengirim OTP melalui SMTP dengan nama pengirim dan HTML branded."""
    if not isinstance(email, str) or not email.strip():
        return False

    if "\r" in email or "\n" in email:
        return False

    if (
        not isinstance(kode, str)
        or not kode.isascii()
        or not kode.isdigit()
    ):
        return False

    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        console.print(
            "[red]Konfigurasi SMTP belum lengkap. Periksa .env.[/red]"
        )
        return False

    if not 1 <= SMTP_PORT <= 65535:
        console.print("[red]Port SMTP tidak valid.[/red]")
        return False

    pesan = EmailMessage()
    pesan["Subject"] = "Kode Verifikasi Email | SIBIMA KECE"
    pesan["From"] = formataddr((NAMA_PENGIRIM, SMTP_USER))
    pesan["To"] = email.strip()

    # Versi teks biasa untuk klien email yang tidak mendukung HTML.
    pesan.set_content(
        f"""SIBIMA KECE - VERIFIKASI EMAIL

Halo, pengguna SIBIMA!

Berikut kode OTP untuk memverifikasi email kamu:

{kode}

Kode berlaku selama {OTP_EXPIRE_MINUTES} menit.

Jangan bagikan kode ini kepada siapa pun.
Tim SIBIMA tidak akan meminta kode OTP kamu.

Jika kamu tidak meminta kode ini, abaikan email ini.

Salam,
Tim SIBIMA KECE

Email otomatis. Mohon jangan membalas email ini.
"""
    )

    # Versi HTML untuk tampilan yang lebih menarik.
    pesan.add_alternative(
        _buat_html_email(kode),
        subtype="html",
    )

    konteks_ssl = ssl.create_default_context()

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(
                SMTP_HOST,
                SMTP_PORT,
                timeout=15,
                context=konteks_ssl,
            ) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                ditolak = server.send_message(pesan)
        else:
            with smtplib.SMTP(
                SMTP_HOST,
                SMTP_PORT,
                timeout=15,
            ) as server:
                server.ehlo()
                server.starttls(context=konteks_ssl)
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASSWORD)
                ditolak = server.send_message(pesan)

        if ditolak:
            console.print(
                "[red]Server SMTP menolak penerima email.[/red]"
            )
            return False

        console.print(
            "[green]Email OTP berhasil diterima oleh server SMTP.[/green]"
        )
        return True

    except (smtplib.SMTPException, OSError, ValueError) as exc:
        console.print(
            f"[red]Pengiriman email gagal ({type(exc).__name__}).[/red]"
        )
        return False
