"""Aturan akses kelas Lite berdasarkan tunggakan, tanpa mengubah status enrollment.

Alias `e` wajib mengacu ke enrollments. Penangguhan dimulai pada H+4,
setelah tiga hari kalender penuh sesudah tanggal jatuh tempo invoice.
Status `selesai` tetap bisa mengakses riwayat akademik.
"""

# Hanya siswa dengan enrollment aktif dan invoice berbayar belum dibayar
# yang melewati H+3 yang dikunci. H+3 masih dalam masa toleransi.
AKSES_TERKUNCI_SQL = """(
    e.status = 'aktif'
    AND EXISTS (
        SELECT 1
        FROM invoices i_akses
        WHERE i_akses.enrollment_id = e.id
          AND i_akses.status = 'belum_dibayar'
          AND i_akses.jumlah > 0
          AND i_akses.jatuh_tempo < CURRENT_DATE - 3
    )
)"""


# Query akademik bersifat per program, tetapi siswa sekarang boleh punya
# beberapa RIWAYAT enrollment untuk program yang sama. Hanya enrollment
# TERBARU yang boleh dipakai sebagai dasar akses (selesai boleh lihat arsip).
# Kalau yang terakhir batal/ditolak, akses akademik harus hilang.
ENROLLMENT_TERAKHIR_TERSEDIA_SQL = """(
    e.status IN ('aktif', 'selesai')
    AND e.id = (
        SELECT MAX(e_terakhir.id) FROM enrollments e_terakhir
        WHERE e_terakhir.student_id = e.student_id
          AND e_terakhir.program_id = e.program_id
    )
)"""
