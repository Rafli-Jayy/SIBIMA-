"""Chat dengan dua mode tampilan: scrollback terminal dan layar bersih."""
from contextlib import nullcontext
from rich.align import Align
from rich.panel import Panel
from rich.text import Text
from .ai_theme import make_console, question_style, fit_width, prompt_prefix
from .chat_state import ChatState, Message
from .mock_responder import MockResponder
from .response_renderer import render_chat, render_message, render_header
from .streaming_renderer import play_stream
from .action_preview import simulate_action


class ChatScreen:
    def __init__(self, role="siswa", console=None, responder=None, stream_delay=0.035, view_mode="clean", online=False):
        self.console = console if console is not None else make_console()
        self.state = ChatState(role=role)
        self.responder = responder if responder is not None else MockResponder()
        self.stream_delay = stream_delay
        self.online = online
        self._search_browser = None
        if view_mode not in ("clean", "scroll"):
            raise ValueError("Mode tampilan tidak dikenal")
        self.view_mode = view_mode

    def _question(self):
        import questionary
        # qmark memuat gutter kiri agar sejajar dengan workspace yang terpusat.
        return questionary.text("Tulis pesan", qmark=prompt_prefix(self.console.width),
                               style=question_style(),
                               erase_when_done=(self.view_mode == "scroll")).ask()

    def _choice(self, title: str, choices, default=None):
        import questionary
        return questionary.select(title, choices=choices, default=default,
                                  qmark=prompt_prefix(self.console.width),
                                  pointer="›", style=question_style()).ask()

    def _menu(self) -> bool:
        self.console.clear()
        self.console.print(render_header(self.state.role, console_width=self.console.width, online=self.online))
        choice = self._choice("Pilih navigasi", [
            "Lanjutkan percakapan", "Lihat riwayat", "Mulai percakapan baru",
            "Bantuan", "Keluar dari asisten",
        ])
        if choice == "Lihat riwayat":
            self._history()
        elif choice == "Mulai percakapan baru":
            self._reset_conversation()
        elif choice == "Bantuan":
            self._help()
        elif choice in (None, "Keluar dari asisten"):
            return True
        return False

    def _history(self) -> None:
        page = 0
        while True:
            self.console.clear()
            self.console.print(render_header(self.state.role, self.console.width, online=self.online))
            count = self.state.page_count()
            self.console.print(Align.center(Text(f"RIWAYAT   ·   Halaman {page+1} dari {count}", style="dim"), width=fit_width(self.console.width)))
            self.console.print()
            msgs = self.state.page(page)
            if not msgs:
                self.console.print(Align.center(Text("Belum ada percakapan.", style="dim"), width=fit_width(self.console.width)))
            for msg in msgs:
                self.console.print(render_message(msg, compact=len(msg.content)>1100, console_width=self.console.width))
                self.console.print()
            opts = ["Kembali ke percakapan"]
            if page + 1 < count:
                opts.append("Lihat pesan lebih lama")
            if page > 0:
                opts.append("Lihat pesan lebih baru")
            choice = self._choice("Riwayat", opts)
            if choice == "Lihat pesan lebih lama":
                page += 1
            elif choice == "Lihat pesan lebih baru":
                page -= 1
            else:
                return

    def _help(self) -> None:
        from rich.markdown import Markdown
        self.console.clear()
        self.console.print(render_header(self.state.role, self.console.width, online=self.online))
        content = (
            "**Coba ketik:** `Apa itu algoritma?`, `Contoh Python`, "
            "`Jadwal saya`, atau `Buat pengumuman`.\n\n"
            "**Navigasi:** `/menu` untuk membuka pilihan, `/riwayat` untuk percakapan lama, "
            "`/baru` untuk chat baru, `/kembali` untuk keluar.\n\n"
            + ("*AI belum membaca data internal SIBIMA. Jangan kirimkan informasi rahasia.*"
             if self.online else "*Ini adalah pratinjau UI offline. Contoh data akun bukan data asli SIBIMA.*")
        )
        self.console.print(Align.center(Panel(Markdown(content), title="PANDUAN", width=fit_width(self.console.width, 80), border_style="grey35")))
        self._choice("Lanjut", ["Kembali ke percakapan"])

    def _reset_conversation(self):
        self.state.clear()
        if self._search_browser is not None:
            self._search_browser.close()
            self._search_browser = None
        reset = getattr(self.responder, "reset", None)
        if callable(reset):
            reset()

    def _present_grounded_result(self, result: dict) -> dict:
        """Only render grounded answer + required Search Suggestions in browser."""
        payload = result.get("data", {}).get("search_result")
        if not isinstance(payload, dict):
            return {"kind": "error", "content": "Metadata Google Search tidak tersedia."}
        try:
            if self._search_browser is None:
                from .search_browser import SearchBrowser
                self._search_browser = SearchBrowser()
            url, opened = self._search_browser.open(payload)
        except Exception:
            return {"kind": "error", "content": "Gagal membuka browser pendamping Google Search."}
        notice = ("Hasil Google Search, sumber, dan saran pencarian dibuka di browser lokal."
                  if opened else "Browser belum terbuka. Buka alamat lokal ini untuk melihat hasil Google Search:\n" + url)
        return {"kind": "markdown", "content": notice, "data": {}}

    def _close_conversation(self):
        self.state.clear()
        if self._search_browser is not None:
            self._search_browser.close()
            self._search_browser = None
        closer = getattr(self.responder, "close", None)
        if callable(closer):
            closer()

    def run(self) -> None:
        """Pilih antara chat yang bisa di-scroll dan layar bersih ala 1D.

        Mode scroll mempertahankan scrollback terminal normal. Mode clean
        memakai alternate screen; pada kedua mode Prompt Toolkit/Questionary
        tidak berjalan bersamaan dengan Rich Live.
        """
        if self.view_mode == "scroll":
            self._scroll_chat_loop()
            return
        screen = self.console.screen(hide_cursor=False) if self.console.is_terminal else nullcontext()
        with screen:
            self._chat_loop()

    def _scroll_chat_loop(self) -> None:
        """Mode utama untuk pengguna: hanya APPEND pesan baru pada scrollback.

        Tidak memakai alternate screen atau clear() setelah setiap pesan.
        Prompt Questionary (erase_when_done=True) tidak ikut menjadi riwayat.
        Kontrol tambahan memakai alternate screen sesaat, sehingga isi
        percakapan tetap berada pada scrollback normal.
        """
        self.console.print(render_chat(self.state, console_width=self.console.width,
                                       show_composer=False, online=self.online))
        self.console.print(Align.center(Text(
            "Gulir ke atas untuk pesan lama  ·  /menu untuk navigasi",
            style="dim"), width=fit_width(self.console.width)))
        self.console.print()
        try:
            while True:
                query = self._question()
                if query is None:
                    break
                query = query.strip()
                if not query:
                    continue
                command = query.casefold()
                if command == "/kembali":
                    break
                if command == "/baru":
                    self._reset_conversation()
                    self.console.print(Align.center(Text(
                        "Percakapan baru dimulai.", style="dim"),
                        width=fit_width(self.console.width)))
                    continue
                if command in {"/menu", "/riwayat"}:
                    # Tampilan menu/riwayat sementara tidak masuk ke scrollback chat.
                    screen = (self.console.screen(hide_cursor=False)
                              if self.console.is_terminal else nullcontext())
                    with screen:
                        should_exit = self._menu() if command == "/menu" else False
                        if command == "/riwayat":
                            self._history()
                    if should_exit:
                        break
                    continue
                if query.startswith("/"):
                    reply = Message("assistant", "Perintah tidak dikenali. Ketik `/menu` untuk melihat pilihan.", kind="error")
                    self.state.add(reply)
                    self.console.print(render_message(reply, console_width=self.console.width))
                    continue
                user_message = Message("user", query)
                self.state.add(user_message)
                self.console.print(render_message(user_message, console_width=self.console.width))
                self.console.print()
                try:
                    # Live hanya menggambar jawaban yang sedang berlangsung.
                    # Setelah selesai, balasan dicetak sekali agar scrollback utuh.
                    result = play_stream(self.console,
                        self.responder.stream(query, self.state.role),
                        self.stream_delay, state=None)
                    if result.get("kind") == "search":
                        result = self._present_grounded_result(result)
                    kind = result.get("kind", "error")
                    data = result.get("data", {})
                    reply = Message("assistant", result.get("content", ""), kind=kind, data=data)
                    self.state.add(reply)
                    self.console.print(render_message(reply, console_width=self.console.width))
                    self.console.print()
                    if kind == "action" and not self.online:
                        screen = (self.console.screen(hide_cursor=False)
                                  if self.console.is_terminal else nullcontext())
                        with screen:
                            outcome = simulate_action(self.console, data)
                        outcome_message = Message("assistant", outcome)
                        self.state.add(outcome_message)
                        self.console.print(render_message(outcome_message, console_width=self.console.width))
                        self.console.print()
                except KeyboardInterrupt:
                    interrupted = Message("assistant", "Respons dihentikan. Tidak ada tindakan yang dilakukan.", kind="error")
                    self.state.add(interrupted)
                    self.console.print(render_message(interrupted, console_width=self.console.width))
                except Exception:
                    failed = Message("assistant", "Terjadi kendala saat menampilkan jawaban. Silakan coba kembali.", kind="error")
                    self.state.add(failed)
                    self.console.print(render_message(failed, console_width=self.console.width))
        finally:
            self._close_conversation()
            self.console.print(Align.center(Text("Percakapan telah ditutup.", style="dim"),
                                            width=fit_width(self.console.width)))

    def _chat_loop(self) -> None:
        try:
            while True:
                # Redraw HANYA satu halaman. Prompt dan header lama terhapus;
                # pesan yang sudah terkirim berasal dari state, tanpa composer.
                self.console.clear()
                self.console.print(render_chat(self.state, console_width=self.console.width, online=self.online))
                query = self._question()
                if query is None:
                    break
                query = query.strip()
                if not query:
                    continue
                command = query.casefold()
                if command == "/kembali":
                    break
                if command == "/menu":
                    if self._menu():
                        break
                    continue
                if command == "/baru":
                    self._reset_conversation()
                    continue
                if command == "/riwayat":
                    self._history()
                    continue
                if query.startswith("/"):
                    self.state.add(Message("assistant", "Perintah tidak dikenali. Ketik `/menu` untuk melihat pilihan.", kind="error"))
                    continue
                self.state.add(Message("user", query))
                try:
                    self.console.clear()
                    result = play_stream(self.console, self.responder.stream(query, self.state.role),
                                         self.stream_delay, state=self.state)
                    if result.get("kind") == "search":
                        result = self._present_grounded_result(result)
                    kind = result.get("kind", "error")
                    data = result.get("data", {})
                    self.state.add(Message("assistant", result.get("content", ""), kind=kind, data=data))
                    if kind == "action" and not self.online:
                        outcome = simulate_action(self.console, data)
                        self.state.add(Message("assistant", outcome))
                except KeyboardInterrupt:
                    self.state.add(Message("assistant", "Respons dihentikan. Tidak ada tindakan yang dilakukan.", kind="error"))
                except Exception:
                    self.state.add(Message("assistant", "Terjadi kendala saat menampilkan jawaban. Silakan coba kembali.", kind="error"))
        finally:
            self._close_conversation()
            self.console.clear()
            self.console.print(Align.center(Text("Percakapan telah ditutup.", style="dim")))
