import os
import time
import json
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import pandas as pd

FON_LISTESI = ["AEV", "AEV", "AK3", "BIO", "BUY", "DHJ", "GKV", "GMR", "GRT", "GSP", "GTM", "HGM", "HRZ", "HVS", "ICZ", "IHK", "IIH", "IVF", "KLH", "KPC", "MAC", "MHF",  "RBH", "TCD", "TI2", "TI3", "TLZ", "YHK", "YHZ"]

def temizle_ve_sayi_yap_adet(deger_str):
    deger_str = deger_str.strip().replace('.', '')
    if deger_str == '-' or deger_str == "" or not deger_str:
        return None
    try:
        return int(deger_str)
    except ValueError:
        return None

def temizle_ve_sayi_yap_oran(deger_str):
    deger_str = deger_str.strip().replace('%', '').replace(',', '.')
    if deger_str == '-' or deger_str == "" or not deger_str:
        return None
    try:
        return float(deger_str)
    except ValueError:
        return None

def veriyi_ayristir(df):
    if df.empty:
        return df
    ilk_kolon_adi = df.columns[0]
    df = df[df[ilk_kolon_adi] != ilk_kolon_adi]
    yeni_df = pd.DataFrame()
    yeni_df[ilk_kolon_adi] = df[ilk_kolon_adi]
    for col in df.columns:
        if col == ilk_kolon_adi or "Tablo" in col:
            continue
        adetler = []
        oranlar = []
        for hucre in df[col]:
            hucre_str = str(hucre).strip()
            if '%' in hucre_str:
                parcalar = hucre_str.split('%')
                adet_ham = parcalar[0].strip()
                oran_ham = parcalar[1].strip()
                adetler.append(temizle_ve_sayi_yap_adet(adet_ham))
                oranlar.append(temizle_ve_sayi_yap_oran(oran_ham))
            else:
                adetler.append(None)
                oranlar.append(None)
        yeni_df[col] = adetler
        yeni_df[f"{col} ORAN (%)"] = oranlar
    return yeni_df

def tek_fon_verisi_topla(page, fon_kodu):
    url = f"https://fintables.com/fonlar/{fon_kodu}/portfoy/hisse-portfoy-gecmisi"
    print(f"\n[{fon_kodu}] Adresine gidiliyor: {url}")
    page.goto(url)

    print(f"[{fon_kodu}] Tablonun yüklenmesi bekleniyor...")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("tbody tr", timeout=15000)

    tum_hisseler = {}
    headers = []

    print(f"[{fon_kodu}] Verileri kaydırılarak toplanıyor...")

    son_hisse_sayisi = 0
    durma_sayaci = 0

    for adim in range(300):
        js_veri = page.evaluate("""
            () => {
                const result = { headers: [], rows: [] };
                const ths = document.querySelectorAll('thead th');
                result.headers = Array.from(ths).map(th => th.innerText.trim().replace(/\\s+/g, ' '));
                const rows = document.querySelectorAll('tr');
                rows.forEach(row => {
                    const cols = row.querySelectorAll('td, th');
                    if (cols.length > 0) {
                        result.rows.push(Array.from(cols).map(td => td.innerText.trim().replace(/\\s+/g, ' ')));
                    }
                });
                return result;
            }
        """)

        if not headers and js_veri['headers']:
            headers = js_veri['headers']

        for row_data in js_veri['rows']:
            if row_data and row_data[0] != "":
                hisse_adi = row_data[0].split()[0]
                if hisse_adi not in tum_hisseler and "Hisse" not in hisse_adi:
                    tum_hisseler[hisse_adi] = row_data

        page.evaluate("window.scrollBy(0, 400)")
        page.evaluate("""
            const scrollableDivs = document.querySelectorAll('div');
            scrollableDivs.forEach(div => {
                if (div.scrollHeight > div.clientHeight && window.getComputedStyle(div).overflowY !== 'hidden') {
                    div.scrollBy(0, 400);
                }
            });
        """)

        page.wait_for_timeout(200)

        mevcut_hisse_sayisi = len(tum_hisseler)

        if mevcut_hisse_sayisi == son_hisse_sayisi:
            durma_sayaci += 1
            if durma_sayaci >= 5:
                break
        else:
            durma_sayaci = 0
            son_hisse_sayisi = mevcut_hisse_sayisi

    print(f"[{fon_kodu}] Tarama bitti. {len(tum_hisseler)} adet benzersiz hisse toplandı.")

    if tum_hisseler:
        veri_listesi = list(tum_hisseler.values())
        max_cols = max(len(r) for r in veri_listesi)
        for r in veri_listesi:
            while len(r) < max_cols:
                r.append("-")
        if len(headers) < max_cols:
            headers = ["Şirket"] + [f"Sütun {i}" for i in range(1, max_cols)]
        else:
            headers = headers[:max_cols]
        df = pd.DataFrame(veri_listesi, columns=headers)
        return veriyi_ayristir(df)
    else:
        print(f"HATA: [{fon_kodu}] için tablo verisi bulunamadı.")
        return pd.DataFrame()

def main():
    if not FON_LISTESI:
        print("Geçerli bir fon kodu tanımlanmadı. İşlem iptal edildi.")
        return

    # GitHub Actions ortamında headless, profil olmadan çalışır
    basarili_sonuclar = {}

    with sync_playwright() as p:
        print("\nFirefox başlatılıyor (headless)...")
        browser = p.firefox.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        for fon in FON_LISTESI:
            fon = fon.strip().upper()
            try:
                duzenli_df = tek_fon_verisi_topla(page, fon)
                if not duzenli_df.empty:
                    basarili_sonuclar[fon] = duzenli_df
            except Exception as e:
                print(f"HATA: [{fon}] işlemesi sırasında beklenmeyen bir hata oluştu: {e}")

        context.close()
        browser.close()

    if basarili_sonuclar:
        # Sabit dosya adı — her çalışmada aynı dosyanın üzerine yazar
        dosya_adi_json = "fonlar_portfoy_gecmisi.json"

        json_verisi = {
            "guncelleme_zamani": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "fonlar": {}
        }
        for fon_kodu, df in basarili_sonuclar.items():
            temiz_df = df.astype(object).where(pd.notnull(df), None)
            json_verisi["fonlar"][fon_kodu] = temiz_df.to_dict(orient='records')

        with open(dosya_adi_json, 'w', encoding='utf-8') as f:
            json.dump(json_verisi, f, ensure_ascii=False, indent=2)

        print(f"\nTAMAMLANDI: {len(basarili_sonuclar)} fon verisi '{dosya_adi_json}' dosyasına kaydedildi.")
    else:
        print("\nKaydedilecek hiçbir veri başarıyla çekilemedi.")
        exit(1)

if __name__ == "__main__":
    main()
