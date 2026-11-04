import streamlit as st

from fpl.ui import apply_theme, autorefresh
from fpl.ui_simple import glossary_cards, simple_hero

st.set_page_config(page_title="Kamus FPL", layout="wide")

apply_theme()
autorefresh()

simple_hero(
    "Kamus FPL",
    "Arti singkat setiap istilah dan angka yang muncul di dashboard.",
    kicker="Bantuan · Bahasa Manusia",
)

st.caption(
    "Tips: gunakan kotak pencarian. Kalau masih bingung dengan angka tertentu, "
    "buka Mode Analis di sidebar untuk melihat detailnya."
)

query = st.text_input("Cari istilah", placeholder="Contoh: EV, FDR, xGI, hit, chip...")
glossary_cards(query)

st.divider()
st.markdown(
    """
    **Cara membaca angka di dashboard**

    1. **Angka besar** biasanya perkiraan poin, bukan janji.
    2. **Hijau** = aman, **kuning** = perlu dipantau, **merah** = risiko.
    3. **Keyakinan Tinggi** berarti data lengkap dan model/simulator setuju.
    4. Kalau ragu, buka `[Lihat alasan]` atau `[Detail angka]`.
    """
)
