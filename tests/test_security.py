from app.utils.security import buat_otp, hash_password, verifikasi_password


def test_hash_dan_verifikasi():
    h = hash_password("rahasia123")
    assert h != "rahasia123"
    assert verifikasi_password("rahasia123", h)
    assert not verifikasi_password("salah", h)


def test_otp_enam_digit():
    otp = buat_otp()
    assert len(otp) == 6 and otp.isdigit()
