import os
from prompt_toolkit import prompt

def main():
    print("=" * 60)
    print("      APLIKASI DRAG & DROP FILE INTERAKTIF (CLI)       ")
    print("=" * 60)
    print("Silakan seret dan jatuhkan (drag & drop) file Anda ke bawah ini.")
    print("(Catatan: Alamat file sengaja disembunyikan agar tampilan bersih)")
    print("-" * 60)

    # Menggunakan is_password=True agar teks alamat yang di-drop tidak dicetak di layar
    # Kita set password_char="" agar benar-benar kosong tanpa memunculkan bintang (****)
    jalur_raw = prompt("Jatuhkan file di sini (lalu tekan ENTER): ", is_password=True, password_char="")
    
    # Membersihkan spasi dan tanda kutip otomatis
    jalur_file = jalur_raw.strip().strip("'\"")

    print("\n" + "-" * 60)

    # Validasi keberadaan file
    if not os.path.exists(jalur_file) or not os.path.isfile(jalur_file):
        print("❌ [Error] File tidak valid atau tidak ditemukan!")
        print("Pastikan Anda melakukan drop file yang benar.")
        return

    # Tampilkan nama filenya saja dengan rapi
    nama_file_saja = os.path.basename(jalur_file)
    print(f"✅ Sukses memuat file: [ {nama_file_saja} ]")
    print("-" * 60)
    print(" ISI FILE: ")
    print("-" * 60)
    
    try:
        with open(jalur_file, 'r', encoding='utf-8') as file:
            print(file.read())
    except UnicodeDecodeError:
        print("[Sistem] File ini bukan file teks biasa (Gambar/Biner).")
    except Exception as e:
        print(f"[Error] Gagal membaca file: {e}")
        
    print("-" * 60)

if __name__ == "__main__":
    main()
