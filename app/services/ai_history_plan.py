"""Patch 5D: declared Admin-only history capabilities and strict arguments."""
from __future__ import annotations

import base64
import binascii
import json
from datetime import date, datetime

HISTORY_TOOLS = (
    "admin_system_history",
    "admin_user_activity",
    "admin_user_timeline",
    "admin_history_analytics",
)

_DESCRIPTIONS = {
    "admin_system_history": "ADMIN. Riwayat activity_logs lintas pengguna. user_id pada log adalah PELAKU, bukan orang yang terkena dampak perubahan. Gunakan tanggal YYYY-MM-DD Asia/Jakarta. Halaman max 20 baris.",
    "admin_user_activity": "ADMIN. Aktivitas yang DILAKUKAN pengguna. WAJIB cari kandidat lewat admin_find_users terlebih dahulu, lalu pakai user_id kandidat yang sudah ditemukan. Bukan histori perubahan terhadap akun orang itu.",
    "admin_user_timeline": "ADMIN. Peristiwa yang BENAR-BENAR tercatat terkait akun terpilih (pendaftaran, invoice, pembayaran), bukan audit trail sempurna. WAJIB admin_find_users dahulu untuk ID. Status adalah status terkini, bukan status pada waktu kejadian.",
    "admin_history_analytics": "ADMIN. COUNT semua activity_logs dalam periode, dikelompokkan menurut aksi/pelaku/hari. Hitungan total berasal dari SQL, bukan 20 baris awal.",
}

_ALLOWED = {
    "admin_system_history": {"tanggal_dari", "tanggal_sampai", "aksi", "limit", "cursor"},
    "admin_user_activity": {"user_id", "tanggal_dari", "tanggal_sampai", "aksi", "limit", "cursor"},
    "admin_user_timeline": {"user_id", "tanggal_dari", "tanggal_sampai", "limit", "cursor"},
    "admin_history_analytics": {"tanggal_dari", "tanggal_sampai", "aksi", "kelompok"},
}


def tool_schema(name: str) -> dict:
    if name not in HISTORY_TOOLS:
        raise ValueError("Fungsi histori tidak dikenali.")
    props = {}
    for key in sorted(_ALLOWED[name]):
        if key in ("tanggal_dari", "tanggal_sampai"):
            props[key] = {"type": "string", "description": "Tanggal lokal Asia/Jakarta YYYY-MM-DD inklusif."}
        elif key == "user_id":
            props[key] = {"type": "integer", "description": "ID akun dari hasil admin_find_users saat ini, bukan ID yang ditebak."}
        elif key == "limit":
            props[key] = {"type": "integer", "description": "1 sampai 20; default 10."}
        elif key == "aksi":
            props[key] = {"type": "string", "description": "Kode aksi persis sebagaimana tercatat pada log, bukan SQL/regex."}
        elif key == "cursor":
            props[key] = {"type": "string", "description": "Cursor halaman berikutnya dari hasil tool sebelumnya, bukan dibuat sendiri."}
        elif key == "kelompok":
            props[key] = {"type": "string", "enum": ["aksi", "pelaku", "hari"]}
    spec = {"type": "object", "properties": props}
    if "user_id" in _ALLOWED[name]:
        spec["required"] = ["user_id"]
    return {"type": "function", "name": name, "description": _DESCRIPTIONS[name], "parameters": spec}


def _date(value: object, key: str) -> str:
    if type(value) is not str or len(value) != 10:
        raise ValueError(f"{key} harus tanggal YYYY-MM-DD.")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Tanggal {key} tidak valid.") from exc
    if result.isoformat() != value:
        raise ValueError(f"Tanggal {key} tidak valid.")
    return value


def _decode_cursor(encoded: str, *, timeline: bool) -> tuple:
    if type(encoded) is not str or not 8 <= len(encoded) <= 256:
        raise ValueError("Cursor tidak valid.")
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != ({"t", "i", "s"} if timeline else {"t", "i"}):
            raise ValueError
        ts = datetime.fromisoformat(data["t"])
        if ts.tzinfo is None or ts.utcoffset() is None:
            raise ValueError
        if type(data["i"]) is not int or not 0 < data["i"] < 2**63:
            raise ValueError
        if timeline and (type(data["s"]) is not int or not 0 <= data["s"] <= 9):
            raise ValueError
    except (TypeError, ValueError, UnicodeError, OverflowError, KeyError, binascii.Error) as exc:
        raise ValueError("Cursor tidak valid.") from exc
    return (ts, data["s"], data["i"]) if timeline else (ts, data["i"])


def make_cursor(waktu: datetime, ident: int, *, seq: int | None = None) -> str:
    if not isinstance(waktu, datetime) or waktu.tzinfo is None:
        raise ValueError("Cursor memerlukan timestamp dengan timezone.")
    data = {"t": waktu.isoformat(), "i": int(ident)}
    if seq is not None:
        data["s"] = int(seq)
    return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")


def validate_history_args(name: str, args: object) -> dict:
    if name not in HISTORY_TOOLS:
        raise PermissionError("Fungsi histori tidak dikenal.")
    if not isinstance(args, dict) or set(args) - _ALLOWED[name]:
        raise ValueError("Parameter histori tidak diizinkan.")
    result = {}
    for key, val in args.items():
        if val is None:
            continue
        if key in ("tanggal_dari", "tanggal_sampai"):
            result[key] = _date(val, key)
        elif key == "user_id":
            if type(val) is not int or val <= 0:
                raise ValueError("ID pengguna harus berasal dari pencarian Admin.")
            result[key] = val
        elif key == "limit":
            if type(val) is not int or not 1 <= val <= 20:
                raise ValueError("Limit histori harus 1–20.")
            result[key] = val
        elif key == "aksi":
            if type(val) is not str or not 1 <= len(val.strip()) <= 60 or any(ord(c) < 32 or ord(c) == 127 for c in val):
                raise ValueError("Kode aksi tidak valid.")
            result[key] = val.strip()
        elif key == "kelompok":
            if val not in ("aksi", "pelaku", "hari") or type(val) is not str:
                raise ValueError("Pilihan kelompok histori tidak valid.")
            result[key] = val
        elif key == "cursor":
            _decode_cursor(val, timeline=name == "admin_user_timeline")
            result[key] = val
    if "user_id" in _ALLOWED[name] and "user_id" not in result:
        raise ValueError("ID pengguna dari pencarian Admin wajib diisi.")
    if result.get("tanggal_dari", "0000") > result.get("tanggal_sampai", "9999"):
        raise ValueError("Awal rentang melebihi akhir rentang.")
    if name == "admin_history_analytics":
        result.setdefault("kelompok", "aksi")
    else:
        result.setdefault("limit", 10)
    return result
