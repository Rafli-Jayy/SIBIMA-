"""Exception khusus aplikasi. Lapisan UI menangkapnya dan menampilkan pesannya."""


class AppError(Exception):
    """Dasar semua error aplikasi. Pesan aman ditampilkan ke pengguna."""


class DataTidakValid(AppError):
    pass


class DataTidakDitemukan(AppError):
    pass


class DuplikatData(AppError):
    pass


class TidakDiizinkan(AppError):
    pass


class AkunTerkunci(AppError):
    pass


class KuotaPenuh(AppError):
    pass


class JadwalBentrok(AppError):
    pass
