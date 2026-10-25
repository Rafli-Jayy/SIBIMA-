-- =====================================================================
-- SIBIMA KECE - seed.sql
-- DATA CONTOH UNTUK PENGEMBANGAN, BUKAN DATA RESMI BIMBEL.
-- Ubah nama, jenjang, harga, kuota, dan ruang sesuai kebutuhan.
-- Aman dijalankan berulang kali: data dengan kode/nama yang sama dilewati.
-- Jalankan setelah schema.sql berhasil dibuat.
-- =====================================================================

BEGIN;

INSERT INTO rooms (nama, kapasitas, aktif)
VALUES
    ('Ruang Demo 1', 20, TRUE),
    ('Ruang Demo 2', 12, TRUE)
ON CONFLICT (nama) DO NOTHING;

INSERT INTO programs (
    kode, nama, jenjang, deskripsi, harga_bulanan, kuota, status,
    bobot_tugas, bobot_kuis, bobot_uts, bobot_uas
)
VALUES
    (
        'MAT-SMP', 'Matematika SMP', 'SMP',
        'Program contoh untuk pengujian SIBIMA. Silakan sesuaikan.',
        150000, 20, 'buka', 30, 20, 20, 30
    ),
    (
        'ING-SMP', 'Bahasa Inggris SMP', 'SMP',
        'Program contoh untuk pengujian SIBIMA. Silakan sesuaikan.',
        175000, 20, 'buka', 30, 20, 20, 30
    ),
    (
        'IPA-SMA', 'IPA SMA', 'SMA',
        'Program contoh untuk pengujian SIBIMA. Silakan sesuaikan.',
        200000, 15, 'buka', 30, 20, 20, 30
    )
ON CONFLICT (kode) DO NOTHING;

COMMIT;
