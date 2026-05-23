"""
utils/format_helper.py
Helper format angka, tanggal, dan label.
"""
from datetime import datetime


def rupiah(amount) -> str:
    """Format angka ke format Rupiah Indonesia."""
    try:
        return f"Rp {float(amount):,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"


def nama_bulan(bulan_str: str) -> str:
    """Ubah '2024-01' → 'Januari 2024'."""
    BULAN = [
        '', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
        'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'
    ]
    try:
        tahun, bln = bulan_str.split('-')
        return f"{BULAN[int(bln)]} {tahun}"
    except Exception:
        return bulan_str


def bulan_sekarang() -> str:
    return datetime.now().strftime('%Y-%m')


def status_badge(status: str) -> dict:
    map_ = {
        'belum':   {'label': 'Belum Bayar', 'color': 'danger'},
        'sebagian':{'label': 'Sebagian',    'color': 'warning'},
        'lunas':   {'label': 'Lunas',       'color': 'success'},
    }
    return map_.get(status, {'label': status, 'color': 'secondary'})
