"""Specific role messages; display-only. Never changes tool permissions."""
from __future__ import annotations
import re


def role_access_clarification(role: str | None, question: str) -> str | None:
    if not isinstance(question, str):
        return None
    q = question.casefold()
    if role == "admin" and re.search(r"\bjadwal\s+mengajar\s+(?:saya|aku|gue|gw|ku)\b", q):
        return ("Anda login sebagai Admin. Jadwal mengajar pribadi merupakan informasi "
                "akun Tutor, sehingga tidak ada jadwal mengajar pribadi untuk sesi Admin ini. "
                "Anda dapat meminta pencarian jadwal Tutor berdasarkan nama melalui fitur "
                "pencarian Admin, atau menggunakan akun Tutor untuk jadwal pribadi.")
    if role in {"tutor", "siswa"} and re.search(r"\b(?:seluruh|semua)\s+(?:data\s+)?(?:nilai|tagihan|pembayaran)(?:\s+dan\s+(?:nilai|tagihan|pembayaran))?\s+(?:semua\s+)?siswa\b", q):
        return (f"Anda login sebagai {role.capitalize()}. Informasi nilai atau keuangan seluruh siswa "
                "merupakan data administrasi yang tidak tersedia untuk role ini. "
                + ("Anda hanya dapat meminta informasi akademik kelas yang diampu. "
                   if role == "tutor" else
                   "Anda hanya dapat membaca nilai dan tagihan milik akun sendiri. ")
                + "Permintaan ini tidak dijalankan.")
    if role == "siswa" and re.search(r"\b(?:nilai|tagihan|pembayaran|data pribadi)\s+(?:milik\s+)?(?:siswa lain|orang lain|teman saya)\b", q):
        return ("Anda login sebagai Siswa. Data pribadi siswa lain tidak boleh diakses "
                "melalui akun ini. Anda tetap dapat melihat informasi milik akun sendiri.")
    if role in {"tutor", "siswa"} and re.search(r"\b(?:jumlah|berapa|total)\s+(?:akun\s+)?siswa\s+aktif\s+(?:di|seluruh|se-)\s*sibima\b", q):
        return (f"Anda login sebagai {role.capitalize()}. Ringkasan jumlah seluruh siswa "
                "SIBIMA hanya tersedia pada akun Admin. "
                + ("Anda dapat menanyakan siswa di kelas yang Anda ampu." if role == "tutor"
                   else "Anda dapat menanyakan informasi pendaftaran Anda sendiri."))
    return None
