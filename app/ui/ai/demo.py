"""Demo UI offline mandiri: python -m app.ui.ai.demo"""
import argparse
import sys
from .ai_theme import make_console, question_style, prompt_prefix
from .chat_screen import ChatScreen
from .response_renderer import render_header


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pratinjau antarmuka SIBIMA AI (offline)")
    parser.add_argument("--role", choices=["admin", "tutor", "siswa"], help="Lewati pilihan role simulasi")
    parser.add_argument("--fast", action="store_true", help="Streaming cepat untuk pengujian")
    parser.add_argument("--mode", choices=["scroll", "clean"], default="scroll",
                        help="scroll=riwayat bisa digulir; clean=layar terpisah seperti Patch 1D")
    parser.add_argument("--gallery", action="store_true",
                        help="Lihat galeri semua skenario tampilan UI")
    args = parser.parse_args(argv)
    console = make_console()
    if args.gallery:
        from .gallery import run_gallery
        run_gallery(console)
        return 0
    try:
        import questionary
    except ImportError:
        console.print("[red]Questionary belum tersedia.[/red] Instal: python -m pip install rich questionary")
        return 2
    try:
        if args.role:
            role = args.role
        else:
            console.print(render_header("siswa", console.width))
            role = questionary.select(
                "Pilih peran", choices=["siswa", "tutor", "admin", "Keluar"],
                qmark=prompt_prefix(console.width), pointer="›", style=question_style(),
            ).ask()
        if role is None or role == "Keluar":
            return 0
        screen = ChatScreen(role=role, console=console, stream_delay=0.0 if args.fast else 0.035,
                            view_mode=args.mode)
        screen.run()
        return 0
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Percakapan ditutup.[/dim]")
        return 0


if __name__ == "__main__":
    sys.exit(main())
