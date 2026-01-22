import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.features import DivIcon
from geopy.geocoders import Nominatim
import requests
from datetime import datetime, timedelta
import pandas as pd
import random
import os
import qrcode
from fpdf import FPDF
import tempfile

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="TR Lojistik Pro", layout="wide", page_icon="🚛")

# --- HAFIZA ---
if 'rota_verisi' not in st.session_state: st.session_state.rota_verisi = None
if 'baslangic' not in st.session_state: st.session_state.baslangic = None
if 'bitis' not in st.session_state: st.session_state.bitis = None
if 'ara_durak' not in st.session_state: st.session_state.ara_durak = None
if 'hava_durumu_noktalari' not in st.session_state: st.session_state.hava_durumu_noktalari = []
if 'mola_noktalari' not in st.session_state: st.session_state.mola_noktalari = []
if 'risk_mesajlari' not in st.session_state: st.session_state.risk_mesajlari = []
if 'ekstra_sure' not in st.session_state: st.session_state.ekstra_sure = 0

DB_FILE = "lojistik_db.csv"

# --- YARDIMCI: PDF OLUŞTURUCU (DÜZELTİLDİ) ---
def create_pdf(sofor, nereden, nereye, km, maliyet, arac):
    def tr_fix(text):
        mapping = {
            'ğ': 'g', 'Ğ': 'G', 'ş': 's', 'Ş': 'S', 'ı': 'i', 'İ': 'I',
            'ü': 'u', 'Ü': 'U', 'ö': 'o', 'Ö': 'O', 'ç': 'c', 'Ç': 'C'
        }
        for k, v in mapping.items():
            text = str(text).replace(k, v)
        return text

    pdf = FPDF()
    pdf.add_page()
    
    # 1. LOGO VE BAŞLIK
    pdf.set_font("Arial", 'B', 20)
    pdf.cell(0, 10, "TR LOJISTIK A.S.", 0, 1, 'C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 10, "Resmi Sefer Irsaliyesi / Official Waybill", 0, 1, 'C')
    pdf.line(10, 30, 200, 30)
    
    # 2. BİLGİLER
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"TARIH: {datetime.now().strftime('%Y-%m-%d %H:%M')}", 0, 1)
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(50, 10, f"KAPTAN SOFOR:", 0, 0)
    pdf.cell(0, 10, tr_fix(sofor), 0, 1)
    
    pdf.cell(50, 10, f"CIKIS:", 0, 0)
    pdf.cell(0, 10, tr_fix(nereden), 0, 1)
    
    pdf.cell(50, 10, f"VARIS:", 0, 0)
    pdf.cell(0, 10, tr_fix(nereye), 0, 1)
    
    pdf.cell(50, 10, f"ARAC:", 0, 0)
    pdf.cell(0, 10, f"34 TR 1923 - {tr_fix(arac)}", 0, 1)
    
    pdf.cell(50, 10, f"MESAFE:", 0, 0)
    pdf.cell(0, 10, f"{km:.0f} KM", 0, 1)
    
    # 3. QR KOD (DÜZELTİLDİ: ARTIK TELEFON NUMARASI SANMAYACAK)
    # Başına "METİN:" ibaresi eklemiyoruz ama formatı netleştiriyoruz.
    qr_icerik = f"""TR LOJISTIK ONAYLI BELGE
-------------------------
KAPTAN: {tr_fix(sofor)}
ROTA: {tr_fix(nereden)} -> {tr_fix(nereye)}
KM: {km:.0f}
TARIH: {datetime.now().strftime('%Y-%m-%d')}
DURUM: ONAYLANDI ✅
-------------------------
Bu belge dijital olarak uretilmistir."""
    
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(qr_icerik)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    
    # Geçici dosya ismi (Her seferinde farklı isim olsun ki karışmasın)
    temp_filename = f"temp_qr_{random.randint(10000,99999)}.png"
    img.save(temp_filename)
    
    # QR PDF'e Ekle
    pdf.image(temp_filename, x=150, y=40, w=40)
    
    # Temizlik (Geçici resmi sil)
    try:
        os.remove(temp_filename)
    except:
        pass
    
    # 4. İMZA
    pdf.ln(20)
    pdf.line(10, 140, 200, 140)
    pdf.cell(90, 10, "TESLIM EDEN (SOFOR)", 0, 0, 'C')
    pdf.cell(90, 10, "TESLIM ALAN (MUSTERI)", 0, 1, 'C')
    
    return pdf.output(dest='S').encode('latin-1')

# --- YARDIMCI FONKSİYONLAR ---
def get_location(address):
    try:
        geolocator = Nominatim(user_agent="kamyon_pro_v5")
        loc = geolocator.geocode(address, timeout=10)
        return [loc.latitude, loc.longitude] if loc else None
    except:
        return None

def get_route(points):
    coords_str = ";".join([f"{p[1]},{p[0]}" for p in points])
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson&steps=true"
    try:
        r = requests.get(url, timeout=10)
        return r.json() if r.status_code == 200 else None
    except:
        return None

def load_data():
    if os.path.exists(DB_FILE): return pd.read_csv(DB_FILE)
    return pd.DataFrame(columns=["Tarih", "Şoför", "Nereden", "Nereye", "KM", "Maliyet", "Araç"])

def save_trip(sofor, nereden, ara, nereye, km, maliyet, arac):
    df = load_data()
    yeni = pd.DataFrame([{
        "Tarih": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Şoför": sofor, "Nereden": nereden, "Ara Durak": ara if ara else "-", "Nereye": nereye,
        "KM": round(km, 2), "Maliyet": round(maliyet, 2), "Araç": arac
    }])
    df = pd.concat([df, yeni], ignore_index=True)
    df.to_csv(DB_FILE, index=False)
    return df

# --- SOL MENÜ ---
with st.sidebar:
    st.title("🚛 TR Lojistik")
    st.markdown("---")
    sofor_adi = st.text_input("👨‍✈️ Kaptan Şoför", "Muslum Baba")
    nereden = st.text_input("📍 Çıkış", "Istanbul")
    ara_durak_input = st.text_input("📦 Ara Durak", "")
    nereye = st.text_input("🏁 Varış", "Ankara")
    st.markdown("---")
    mevsim = st.selectbox("Mevsim", ["Kış ❄️", "Yaz ☀️", "Sonbahar 🍂"])
    trafik = st.select_slider("Trafik", options=["Açık 🟢", "Normal 🟡", "Yoğun 🟠"])
    mola_sikligi = st.slider("Mola (km)", 100, 400, 200)
    arac_tipi = st.selectbox("Araç", ["Tır (F-Max)", "Kamyon", "Panelvan"])
    st.markdown("---")
    hesapla_btn = st.button("🚀 PLANI BAŞLAT", type="primary", use_container_width=True)

# --- HESAPLAMA ---
if hesapla_btn:
    with st.spinner("Sistem hazırlanıyor..."):
        p1 = get_location(nereden)
        p3 = get_location(nereye)
        p2 = get_location(ara_durak_input) if ara_durak_input else None
        
        if p1 and p3:
            noktalar = [p1]
            if p2: noktalar.append(p2)
            noktalar.append(p3)
            
            st.session_state.baslangic = p1
            st.session_state.ara_durak = p2
            st.session_state.bitis = p3
            
            data = get_route(noktalar)
            if data:
                st.session_state.rota_verisi = data
                route = data["routes"][0]
                geometry = route["geometry"]["coordinates"]
                path = [[lat, lon] for lon, lat in geometry]
                total_pts = len(path)
                total_km = route["distance"] / 1000
                
                # Hava & Mola
                temp_hava, temp_risk, temp_mola, temp_gecikme = [], [], [], 0
                for i in range(1, 6):
                    idx = int((total_pts / 6) * i)
                    loc = path[idx]
                    if "Kış" in mevsim:
                        durum, emoji = random.choice([("Karlı", "❄️"), ("Buz", "🧊")])
                        if "Karlı" in durum: 
                            temp_gecikme += 30
                            temp_risk.append(f"⚠️ {i}. Bölge: Karlı - Zincir!")
                    elif "Sonbahar" in mevsim:
                        durum, emoji = "Yağmurlu", "🌧️"
                        temp_gecikme += 15
                        temp_risk.append(f"💧 {i}. Bölge: Kaygan Zemin")
                    else:
                        durum, emoji = "Güneşli", "☀️"
                    temp_hava.append({"loc": loc, "emoji": emoji, "popup": durum})

                if total_km > mola_sikligi:
                    stops = int(total_km / mola_sikligi)
                    for i in range(1, stops + 1):
                        idx = int((total_pts / (stops + 1)) * i)
                        html = f"<div style='background-color:#007bff;color:white;border:2px solid white;border-radius:5px;padding:2px;text-align:center;font-weight:bold;font-size:12px;width:70px;box-shadow:2px 2px 5px black;'>⛽ Mola {i}</div>"
                        temp_mola.append({"loc": path[idx], "html": html})

                st.session_state.hava_durumu_noktalari = temp_hava
                st.session_state.mola_noktalari = temp_mola
                st.session_state.risk_mesajlari = temp_risk
                st.session_state.ekstra_sure = temp_gecikme
            else:
                st.error("Rota servisi hatası.")
        else:
            st.error("Adres bulunamadı.")

# --- SEKME SİSTEMİ ---
tab1, tab2, tab3 = st.tabs(["🗺️ Operasyon", "🚚 Kaptan", "📊 Patron"])

with tab1: # OPERASYON
    st.subheader("Operasyon Merkezi")
    col_map, col_details = st.columns([2.5, 1])
    
    with col_map:
        merkez = st.session_state.baslangic if st.session_state.baslangic else [39.0, 35.0]
        m = folium.Map(location=merkez, zoom_start=6, tiles="CartoDB positron")

        if st.session_state.rota_verisi:
            route = st.session_state.rota_verisi["routes"][0]
            color = "red" if trafik == "Yoğun 🟠" else "#28a745"
            folium.GeoJson(route["geometry"], name="Rota", style_function=lambda x: {'color': color, 'weight': 5}).add_to(m)
            folium.Marker(st.session_state.baslangic, icon=folium.Icon(color="green", icon="play"), tooltip="Çıkış").add_to(m)
            if st.session_state.ara_durak: folium.Marker(st.session_state.ara_durak, icon=folium.Icon(color="orange", icon="truck", prefix="fa"), tooltip="Ara Durak").add_to(m)
            folium.Marker(st.session_state.bitis, icon=folium.Icon(color="red", icon="flag"), tooltip="Varış").add_to(m)
            for h in st.session_state.hava_durumu_noktalari: folium.Marker(h["loc"], popup=h["popup"], icon=DivIcon(icon_size=(30,30), html=f"<div style='font-size:30px;'>{h['emoji']}</div>")).add_to(m)
            for mola in st.session_state.mola_noktalari: folium.Marker(mola["loc"], icon=DivIcon(icon_size=(70,30), html=mola["html"])).add_to(m)
            bounds = [st.session_state.baslangic, st.session_state.bitis]
            if st.session_state.ara_durak: bounds.append(st.session_state.ara_durak)
            m.fit_bounds(bounds)

        st_folium(m, width=None, height=550, returned_objects=[])

    with col_details:
        st.write("#### 📊 Sefer Özeti")
        if st.session_state.rota_verisi:
            route = st.session_state.rota_verisi["routes"][0]
            km = route["distance"] / 1000
            normal_dk = route["duration"] / 60
            trafik_etkisi = normal_dk * 0.4 if trafik == "Yoğun 🟠" else 0
            toplam_dk = normal_dk + trafik_etkisi + st.session_state.ekstra_sure
            litres = 32 if "Tır" in arac_tipi else 15
            maliyet = (km / 100) * litres * 42.0
            varis = datetime.now() + timedelta(minutes=toplam_dk)

            # --- DÜZELTME BURADA: SAAT ARTIK AÇIKLAMALI ---
            st.success(f"🏁 Tahmini Varış: **{varis.strftime('%H:%M')}**")
            # -----------------------------------------------
            
            st.metric("🛣️ Mesafe", f"{km:.0f} km")
            st.metric("💸 Maliyet", f"{maliyet:,.0f} TL")
            
            st.divider()
            if st.session_state.risk_mesajlari:
                st.error(f"⚠️ **{len(st.session_state.risk_mesajlari)} Risk Var!**")
                for r in st.session_state.risk_mesajlari: st.caption(r)
            else: st.success("✅ Güvenli Rota")
            
            st.divider()
            
            # PDF BUTONU
            pdf_bytes = create_pdf(sofor_adi, nereden, nereye, km, maliyet, arac_tipi)
            st.download_button(
                label="📄 İRSALİYE BAS (PDF)",
                data=pdf_bytes,
                file_name=f"irsaliye_{sofor_adi}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
            
            # KAYIT BUTONU
            if st.button("💾 VERİTABANINA İŞLE", use_container_width=True):
                save_trip(sofor_adi, nereden, ara_durak_input, nereye, km, maliyet, arac_tipi)
                st.toast("Kayıt Başarılı!", icon="✅")
        else:
            st.info("Hesaplama bekleniyor...")

with tab2: # KAPTAN
    st.subheader(f"👋 İyi Yolculuklar, {sofor_adi}!")
    c1, c2 = st.columns(2)
    with c1:
        st.info("### 🎵 Müzik & Yemek")
        st.link_button("📻 Radyo Aç", "https://open.spotify.com/genre/0JQ5DAqbMKFQ00XGBls6ym", use_container_width=True)
        st.link_button("🍽️ Yemek Bul", "https://www.google.com/maps/search/restoranlar/", use_container_width=True)
        st.error("### 🆘 ACİL DURUM")
        if st.button("👮 POLİS", use_container_width=True): st.toast("155 Aranıyor...")
    with c2:
        st.success("### 📦 Görev")
        if st.session_state.rota_verisi:
            st.write(f"**Hedef:** {nereye.upper()}")
            st.button("✅ YÜKÜ TESLİM ET", type="primary", use_container_width=True)
        else: st.warning("Rota yok.")

with tab3: # PATRON
    st.subheader("📊 Raporlar")
    df = load_data()
    if not df.empty:
        st.dataframe(df, use_container_width=True)
        if st.button("🗑️ Temizle"):
            if os.path.exists(DB_FILE): os.remove(DB_FILE)
            st.rerun()
    else: st.info("Kayıt yok.")