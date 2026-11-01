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
