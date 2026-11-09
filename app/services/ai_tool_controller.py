"""Role-limited, schema-validated tool router for Gemini; no freeform SQL."""
from __future__ import annotations

from app import session
from app.repositories.ai_read_repo import AIReadRepository
from app.services.ai_history_plan import (
    HISTORY_TOOLS, tool_schema as history_schema, validate_history_args,
)
from app.services.ai_query_planner import (
    TOOL_ROLE as PATCH5C_TOOLS, tool_schema as analytics_schema, validate_plan,
)
from app.services.rag.rag_chat_tool import (RAGKnowledgeTool, TOOL_DECLARATION, TOOL_NAME)
from app.services.ai_dynamic_plan import (NAME as DYNAMIC_NAME, ROLE_DYNAMIC_NAMES,
                                          role_dynamic_schema, validate_role_dynamic_plan)

# Base role matrix retained unchanged; additional tools are explicitly separated.
EXTRA_ROLE_TO_TOOLS = {
    "admin": ("get_my_identity", "admin_find_users", "admin_get_user_summary", "admin_list_students_by_tutor"),
    "tutor": ("get_my_identity",),
    "siswa": ("get_my_identity",),
}
ROLE_TO_TOOLS = {
    "admin": ("get_admin_overview", "list_unpaid_invoices"),
    "tutor": ("get_my_teaching_schedule", "list_my_class_students", "get_my_class_attendance"),
    "siswa": ("get_my_schedule", "get_my_grades", "get_my_attendance", "get_my_invoices", "get_my_payments", "get_my_enrollments"),
}
PATCH5C_ROLE_TO_TOOLS = {
    role: tuple(name for name, allowed_role in PATCH5C_TOOLS.items() if allowed_role == role)
    for role in ("admin", "tutor", "siswa")
}
DESCRIPTIONS = {
    "get_my_identity": "Kenali nama lengkap, username, role dan status akun yang SEDANG login. Gunakan untuk pertanyaan nama saya/akun saya/siapa saya. Tidak menerima parameter user_id.",
    "admin_find_users": "ADMIN SAJA. Cari nama lengkap atau username siswa/tutor/admin dengan kata sebagian (contoh 'Zarkasi'). Jumlah jadwal mengajar aktif BERBEDA dari jumlah program berbeda. Jika banyak kandidat, jelaskan dan pilih berdasarkan user_id yang ditemukan, jangan menebak. Argumen query adalah nama yang dicari.",
    "admin_get_user_summary": "ADMIN SAJA. Setelah menemukan user_id resmi dari admin_find_users, tampilkan ringkasan dan jadwal/program milik pengguna tersebut. Jangan gunakan untuk identitas sendiri; pakai get_my_identity.",
    "admin_list_students_by_tutor": "ADMIN SAJA. Untuk pertanyaan siapa saja murid/siswa yang diajar tutor bernama tertentu. WAJIB cari nama tutor lebih dulu melalui admin_find_users, lalu gunakan tutor_user_id yang ditemukan. Menghasilkan siswa dengan enrollment aktif di program yang jadwal aktifnya diampu Tutor; tidak membuktikan kehadiran di pertemuan tertentu. Jika ada banyak kandidat Tutor, minta klarifikasi.",
    "get_admin_overview": "Ringkasan jumlah siswa aktif, tutor aktif, program buka, enrollment aktif, dan tagihan belum lunas.",
    "list_unpaid_invoices": "Daftar tagihan belum lunas (Admin saja). Gunakan overdue_only=true untuk yang sudah terlambat.",
    "get_my_teaching_schedule": "Daftar jadwal mengajar milik Tutor yang login.",
    "list_my_class_students": "Daftar siswa aktif pada kelas yang saat ini diampu Tutor.",
    "get_my_class_attendance": "Rekap kehadiran siswa pada sesi selesai di kelas Tutor.",
    "get_my_schedule": "Jadwal kelas aktif yang dapat diakses Siswa yang login.",
    "get_my_grades": "Nilai siswa yang login pada kelas yang masih berhak diakses.",
    "get_my_attendance": "Daftar absensi siswa yang login pada kelas yang boleh diakses.",
    "get_my_invoices": "Daftar tagihan milik siswa yang login (termasuk tunggakan).",
    "get_my_payments": "Riwayat pembayaran milik siswa yang login. Status pembayaran BERBEDA dari status pendaftaran.",
    "get_my_enrollments": "Status pendaftaran PROGRAM per siswa yang login. WAJIB untuk pertanyaan diterima admin, dikonfirmasi, pending/menunggu, atau kelas sudah aktif. Jangan menyimpulkan dari status lunas pembayaran.",
}
WITH_PROGRAM = {"list_my_class_students", "get_my_class_attendance", "get_my_grades", "get_my_attendance"}


def tool_schema(name: str) -> dict:
    if name in ROLE_DYNAMIC_NAMES.values():
        return role_dynamic_schema(next(role for role, tool in ROLE_DYNAMIC_NAMES.items() if tool == name))
    if name in PATCH5C_TOOLS:
        return analytics_schema(name)
    if name in HISTORY_TOOLS:
        return history_schema(name)
    props = {}
    if name in WITH_PROGRAM:
        props["program_id"] = {"type": "integer", "description": "Filter ID program; hilangkan jika seluruh program yang diizinkan."}
    if name == "admin_find_users":
        props["query"] = {"type": "string", "description": "Nama lengkap atau username (minimal 2 dan maksimal 80 karakter)."}
    if name == "admin_get_user_summary":
        props["user_id"] = {"type": "integer", "description": "ID akun kandidat dari pencarian Admin, bukan dari teks bebas."}
    if name == "admin_list_students_by_tutor":
        props["tutor_user_id"] = {"type": "integer", "description": "ID akun Tutor yang diperoleh dari hasil admin_find_users; bukan ID buatan sendiri."}
    if name == "list_unpaid_invoices":
        props["overdue_only"] = {"type": "boolean", "description": "Hanya tagihan melewati jatuh tempo."}
    parameters = {"type": "object", "properties": props}
    if name == "admin_find_users":
        parameters["required"] = ["query"]
    if name == "admin_get_user_summary":
        parameters["required"] = ["user_id"]
    if name == "admin_list_students_by_tutor":
        parameters["required"] = ["tutor_user_id"]
    return {"type": "function", "name": name, "description": DESCRIPTIONS[name],
            "parameters": parameters}


def validate_args(name: str, args: object) -> dict:
    if name in ROLE_DYNAMIC_NAMES.values():
        return validate_role_dynamic_plan(args, next(role for role, tool in ROLE_DYNAMIC_NAMES.items() if tool == name))
    if name in PATCH5C_TOOLS:
        return validate_plan(name, args, PATCH5C_TOOLS[name])
    if name in HISTORY_TOOLS:
        return validate_history_args(name, args)
    if not isinstance(args, dict):
        raise ValueError("Parameter fungsi harus objek JSON.")
    allowed = ({"program_id"} if name in WITH_PROGRAM else
               {"overdue_only"} if name == "list_unpaid_invoices" else
               {"query"} if name == "admin_find_users" else
               {"user_id"} if name == "admin_get_user_summary" else
               {"tutor_user_id"} if name == "admin_list_students_by_tutor" else set())
    if set(args) - allowed:
        raise ValueError("Parameter yang diminta tidak diizinkan.")
    if "program_id" in args and (type(args["program_id"]) is not int or args["program_id"] <= 0):
        raise ValueError("ID program tidak valid.")
    if "overdue_only" in args and type(args["overdue_only"]) is not bool:
        raise ValueError("Filter tunggakan harus boolean.")
    if name == "admin_find_users":
        query = args.get("query")
        if not isinstance(query, str) or not 2 <= len(query.strip()) <= 80:
            raise ValueError("Nama pencarian harus sepanjang 2–80 karakter.")
        if any(ord(char) < 32 or ord(char) == 127 for char in query):
            raise ValueError("Nama pencarian mengandung karakter kontrol.")
        return {"query": query.strip()}
    if name == "admin_get_user_summary" and (type(args.get("user_id")) is not int or args["user_id"] <= 0):
        raise ValueError("ID akun pencarian tidak valid.")
    if name == "admin_list_students_by_tutor" and (
            type(args.get("tutor_user_id")) is not int or args["tutor_user_id"] <= 0):
        raise ValueError("ID Tutor dari hasil pencarian tidak valid.")
    return args


class AIToolController:
    def __init__(self, role: str, *, repo=None, identity=None, rag_tool=None):
        current = identity if identity is not None else session.get_user()
        if not isinstance(current, dict) or type(current.get("id")) is not int or current["id"] <= 0:
            raise PermissionError("AI database membutuhkan sesi login yang valid.")
        if current.get("role") != role or role not in ROLE_TO_TOOLS or current.get("status") != "aktif":
            raise PermissionError("Role pengguna tidak sesuai atau akun tidak aktif.")
        self.user_id, self.role = current["id"], role
        self.repo = repo if repo is not None else AIReadRepository()
        self._discovered_user_ids: set[int] = set()
        self._discovered_tutor_ids: set[int] = set()
        self.rag_tool = rag_tool if rag_tool is not None else RAGKnowledgeTool.from_environment()

    def declarations(self) -> list[dict]:
        tools = [tool_schema(n) for n in ROLE_TO_TOOLS[self.role] + EXTRA_ROLE_TO_TOOLS[self.role]
                 + PATCH5C_ROLE_TO_TOOLS[self.role] + (HISTORY_TOOLS if self.role == "admin" else ())]
        tools.append(tool_schema(ROLE_DYNAMIC_NAMES[self.role]))
        if self.rag_tool is not None:
            tools.append(dict(TOOL_DECLARATION))
        return tools

    def execute(self, name: str, arguments: object) -> dict:
        # Revalidate memory session on EACH invocation; never read principal from tool args.
        current = session.get_user()
        if not isinstance(current, dict) or current.get("id") != self.user_id or current.get("role") != self.role:
            raise PermissionError("Sesi pengguna berubah atau sudah keluar.")
        if current.get("status") != "aktif":
            raise PermissionError("Akun tidak aktif.")
        if name == TOOL_NAME:
            if self.rag_tool is None:
                raise PermissionError("Fungsi RAG tidak diaktifkan.")
            if not isinstance(arguments, dict) or set(arguments) != {"query"}:
                raise ValueError("Pencarian RAG hanya menerima parameter query.")
            return self.rag_tool.search(arguments["query"], role=self.role)
        allowed = (ROLE_TO_TOOLS[self.role] + EXTRA_ROLE_TO_TOOLS[self.role] +
                   PATCH5C_ROLE_TO_TOOLS[self.role] + (HISTORY_TOOLS if self.role == "admin" else ()) +
                   (ROLE_DYNAMIC_NAMES[self.role],))
        if name not in allowed:
            raise PermissionError("Fungsi tidak diizinkan untuk role ini.")
        args = validate_args(name, arguments)
        if name == "admin_list_students_by_tutor" and args["tutor_user_id"] not in self._discovered_tutor_ids:
            raise PermissionError("Cari nama Tutor dahulu melalui pencarian Admin yang sah.")
        if name == "admin_list_students_by_tutor" and len(self._discovered_tutor_ids) > 1:
            raise PermissionError("Ada lebih dari satu Tutor yang cocok. Perjelas nama/username dan cari ulang sebelum membuka daftar siswa.")
        if name in ("admin_get_user_summary", "admin_user_activity", "admin_user_timeline") and args["user_id"] not in self._discovered_user_ids:
            raise PermissionError("Pilih akun terlebih dahulu melalui pencarian nama Admin.")
        if name in ("admin_user_activity", "admin_user_timeline") and len(self._discovered_user_ids) > 1:
            raise PermissionError("Beberapa akun cocok; cari ulang menggunakan nama/username lebih spesifik.")
        if name == "admin_find_users":
            # Invalidate previous discovery before new lookup, even if the
            # database lookup fails and cannot return a candidate list.
            self._discovered_user_ids.clear()
            self._discovered_tutor_ids.clear()
        # Read-only history uses the same repository/session/role checks as every AI tool.
        result = self.repo.execute(self.user_id, self.role, name, args)
        if name == "admin_find_users" and isinstance(result, dict):
            for row in result.get("data", [])[:10]:
                if isinstance(row, dict) and type(row.get("user_id")) is int:
                    self._discovered_user_ids.add(row["user_id"])
                    if row.get("role") == "tutor":
                        self._discovered_tutor_ids.add(row["user_id"])
        return result
