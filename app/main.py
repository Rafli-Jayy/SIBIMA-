"""Titik masuk program. Jalankan dari folder proyek: python -m app.main"""
from app import db
from app.ui import menu_auth
from app.ui.console import console


def main():
    try:
        menu_auth.jalankan()
    except KeyboardInterrupt:
        console.print("\nProgram dihentikan.")
    finally:
        db.tutup_pool()


if __name__ == "__main__":
    main()
