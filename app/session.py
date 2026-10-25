"""Menyimpan pengguna yang sedang login selama program berjalan."""

_user = None


def set_user(user):
    """user: dict baris tabel users (minimal id, username, nama_lengkap, role)."""
    global _user
    _user = user


def get_user():
    return _user


def logout():
    global _user
    _user = None


def sudah_login():
    return _user is not None


def punya_role(*role):
    """Contoh: punya_role('admin') atau punya_role('tutor', 'admin')."""
    return _user is not None and _user["role"] in role
