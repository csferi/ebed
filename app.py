import streamlit as st
import json
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread

# --- Google Sheets Kapcsolat beállítása ---
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

try:
    # Betöltjük a titkosított kulcsokat a Streamlit Secrets-ből
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    gc = gspread.authorize(creds)
    
    # FIGYELEM: Cseréld ki az alábbi nevet a saját Google Táblázatod pontos nevére!
    sh = gc.open("Ebed_Nyilvantarto")
    sheet_tagok = sh.worksheet("Tagok")
    sheet_tranzakciok = sh.worksheet("Tranzakciok")
except Exception as e:
    st.error("Hiba történt a Google Táblázat elérésekor. Kérlek ellenőrizd a beállításokat és a Secrets-t!")
    st.exception(e)
    st.stop()

# --- Adatok szinkronizálása a Google Táblázattal ---
def load_data_from_sheets():
    # 1. Tagok betöltése (Első oszlop)
    tagok_raw = sheet_tagok.col_values(1)
    # Kiszűrjük az esetleges üres sorokat
    tagok_raw = [t.strip() for t in tagok_raw if t and str(t).strip()]
    if not tagok_raw:
        default_tagok = ["Anna", "Balázs", "Gábor", "Dóra"]
        sheet_tagok.update("A1:A" + str(len(default_tagok)), [[t] for t in default_tagok])
        tagok_raw = default_tagok
    
    # 2. Tranzakciók betöltése (Bombabiztos, get_all_records-mentes megoldás)
    rows = sheet_tranzakciok.get_all_values()
    fejlecek = ["id", "tipus", "fizette", "osszeg", "resztvevok", "kitol", "kinek", "datum"]
    
    # Ha teljesen üres a munkalap, vagy nincs benne fejléc, létrehozzuk és lementjük
    if not rows or not rows[0] or rows[0][0].strip() != "id":
        sheet_tranzakciok.clear()
        sheet_tranzakciok.append_row(fejlecek)
        rows = [fejlecek]
        
    tranzakciok = []
    
    # Az első sor a fejléc, a többit feldolgozzuk
    for r in rows[1:]:
        # Ha a sor rövidebb mint a fejléc, kiegészítjük üres stringekkel
        row_data = r + [""] * (len(fejlecek) - len(r))
        
        # Létrehozzuk a kulcs-érték párokat
        row_dict = dict(zip(fejlecek, row_data))
        
        # Csak akkor adjuk hozzá, ha van érvényes ID
        if row_dict.get("id"):
            try:
                # Feldolgozzuk a listát a résztvevőknél
                resztvevok_str = row_dict.get("resztvevok", "[]")
                resztvevok_list = json.loads(resztvevok_str) if resztvevok_str else []
                
                tranzakciok.append({
                    "id": float(row_dict["id"]),
                    "tipus": row_dict.get("tipus", ""),
                    "fizette": row_dict.get("fizette", ""),
                    "osszeg": int(row_dict["osszeg"]) if row_dict.get("osszeg") else 0,
                    "resztvevok": resztvevok_list,
                    "kitol": row_dict.get("kitol", ""),
                    "kinek": row_dict.get("kinek", ""),
                    "datum": row_dict.get("datum", "")
                })
            except Exception:
                # Hibás sorokat egyszerűen átugorjuk, hogy ne omoljon össze az app
                continue
                
    return {"tagok": tagok_raw, "tranzakciok": tranzakciok}

def save_tagok_to_sheets(tagok):
    sheet_tagok.clear()
    if tagok:
        sheet_tagok.update("A1:A" + str(len(tagok)), [[t] for t in tagok])

def add_tranzakcio_to_sheets(tr):
    sor = [
        tr.get("id", ""),
        tr.get("tipus", ""),
        tr.get("fizette", ""),
        tr.get("osszeg", 0),
        json.dumps(tr.get("resztvevok", [])),
        tr.get("kitol", ""),
        tr.get("kinek", ""),
        tr.get("datum", "")
    ]
    sheet_tranzakciok.append_row(sor)

def clear_all_tranzakciok_on_sheets():
    sheet_tranzakciok.clear()
    fejlecek = ["id", "tipus", "fizette", "osszeg", "resztvevok", "kitol", "kinek", "datum"]
    sheet_tranzakciok.append_row(fejlecek)

# --- Adatok betöltése ---
data = load_data_from_sheets()

st.title("🍔 Munkahelyi Ebéd Elszámoló")
st.caption("🔒 Biztonságos Google Cloud háttértárral szinkronizálva")

# --- Tartozások kiszámítása (Mátrix logika) ---
tagok = data["tagok"]
matrix = {t1: {t2: 0.0 for t2 in tagok} for t1 in tagok}

for tr in data["tranzakciok"]:
    if tr["tipus"] == "ebed":
        fizette = tr["fizette"]
        resztvevok = tr["resztvevok"]
        if fizette in matrix and resztvevok:
            ervenyes_resztvevok = [r for r in resztvevok if r in matrix]
            if ervenyes_resztvevok:
                resz_osszeg = tr["osszeg"] / len(ervenyes_resztvevok)
                for r in ervenyes_resztvevok:
                    if r != fizette:
                        matrix[r][fizette] += resz_osszeg

# Törlések / Visszafizetések levonása
netto_tartozasok = []
for i in range(len(tagok)):
    for j in range(i + 1, len(tagok)):
        t1 = tagok[i]
        t2 = tagok[j]
        
        t1_tartozik_t2_nek = matrix[t1][t2]
        t2_tartozik_t1_nek = matrix[t2][t1]
        
        for tr in data["tranzakciok"]:
            if tr["tipus"] == "torles":
                if tr["kitol"] == t1 and tr["kinek"] == t2:
                    t1_tartozik_t2_nek -= tr["osszeg"]
                if tr["kitol"] == t2 and tr["kinek"] == t1:
                    t2_tartozik_t1_nek -= tr["osszeg"]
        
        egyenleg = t1_tartozik_t2_nek - t2_tartozik_t1_nek
        
        if egyenleg > 1:
            netto_tartozasok.append({"kitol": t1, "kinek": t2, "osszeg": round(egyenleg)})
        elif egyenleg < -1:
            netto_tartozasok.append({"kitol": t2, "kinek": t1, "osszeg": round(abs(egyenleg))})

# Segédfüggvény tartozás ellenőrzéséhez
def van_tartozasa(tag):
    for nt in netto_tartozasok:
        if nt["kitol"] == tag or nt["kinek"] == tag:
            return True
    return False

# --- 1. OLDALSÁV: Tagok kezelése ---
with st.sidebar:
    st.header("👥 Csapattagok kezelése")
    
    # Tag hozzáadása
    uj_tag = st.text_input("Új tag hozzáadása:")
    if st.button("➕ Hozzáadás") and uj_tag:
        uj_tag_clean = uj_tag.strip()
        if uj_tag_clean and uj_tag_clean not in data["tagok"]:
            data["tagok"].append(uj_tag_clean)
            save_tagok_to_sheets(data["tagok"])
            st.success(f"{uj_tag_clean} hozzáadva!")
            st.rerun()
            
    st.divider()
    
    # Könnyű és biztonságos törlés
    st.subheader("Személy eltávolítása")
    if data["tagok"]:
        torlendo_tag = st.selectbox("Ki távozik?", data["tagok"])
        if st.button("❌ Tag törlése", type="primary"):
            if van_tartozasa(torlendo_tag):
                st.error(f"**{torlendo_tag}** nem törölhető, mert még van elszámolatlan egyenlege! Előbb nullázzátok a tartozását.")
            else:
                data["tagok"].remove(torlendo_tag)
                save_tagok_to_sheets(data["tagok"])
                st.success(f"{torlendo_tag} sikeresen törölve!")
                st.rerun()
    else:
        st.write("Nincs törölhető tag.")

if len(data["tagok"]) < 2:
    st.warning("Kérjük, vigyél fel legalább 2 tagot az oldalsávban a működéshez!")
    st.stop()

# --- 2. FŐPANEL: Aktuális egyenlegek ---
st.header("📊 Ki kinek mennyivel tartozik?")
if netto_tartozasok:
    for t in netto_tartozasok:
        st.markdown(f"🔴 **{t['kitol']}** tartozik **{t['kinek']}** részére:  `{t['osszeg']:,} Ft`".replace(",", " "))
else:
    st.success("🎉 Mindenki nullán van, nincs aktuális tartozás!")

st.divider()

# --- 3. ŰRLAPOK: Új események rögzítése ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("🍱 Új ebéd beírása")
    with st.form("ebed_form", clear_on_submit=True):
        fizette = st.selectbox("Ki fizetett?", tagok)
        osszeg = st.number_input("Összeg (Ft):", min_value=0, step=100)
        resztvevok = st.multiselect("Kiknek hozott ebédet? (A fizetőt is jelöld be!)", tagok, default=[fizette])
        
        if st.form_submit_button("Ebéd rögzítése"):
            if osszeg > 0 and resztvevok:
                uj_tr = {
                    "id": datetime.now().timestamp(),
                    "tipus": "ebed",
                    "fizette": fizette,
                    "osszeg": osszeg,
                    "resztvevok": resztvevok,
                    "kitol": "",
                    "kinek": "",
                    "datum": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                add_tranzakcio_to_sheets(uj_tr)
                st.success("Ebéd elmentve a Google Táblázatba!")
                st.rerun()
            else:
                st.error("Kérjük, adj meg összeget és válaszd ki a résztvevőket!")

with col2:
    st.subheader("💰 Tartozás rendezése")
    with st.form("torles_form", clear_on_submit=True):
        kitol = st.selectbox("Ki fizetett vissza?", tagok)
        kinek = st.selectbox("Kinek fizetett?", tagok, index=1 if len(tagok)>1 else 0)
        
        aktualis_visszafizetendo = 0
        for nt in netto_tartozasok:
            if nt["kitol"] == kitol and nt["kinek"] == kinek:
                aktualis_visszafizetendo = nt["osszeg"]
        
        st.caption(f"Aktuális tartozás ({kitol} -> {kinek}): {aktualis_visszafizetendo:,} Ft".replace(",", " "))
        
        if st.form_submit_button("Tartozás nullázása / rendezése"):
            if kitol == kinek:
                st.error("Magadnak nem tudsz visszafizetni!")
            elif aktualis_visszafizetendo == 0:
                st.warning("Nincs fennálló tartozás e között a két ember között.")
            else:
                uj_tr = {
                    "id": datetime.now().timestamp(),
                    "tipus": "torles",
                    "fizette": "",
                    "osszeg": aktualis_visszafizetendo,
                    "resztvevok": [],
                    "kitol": kitol,
                    "kinek": kinek,
                    "datum": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                add_tranzakcio_to_sheets(uj_tr)
                st.success(f"{kitol} -> {kinek} tartozás rendezve!")
                st.rerun()

# --- 4. Előzmények ---
st.divider()
st.subheader("📜 Utolsó tranzakciók")
if data["tranzakciok"]:
    megjelenitett = 0
    for tr in reversed(data["tranzakciok"]):
        if megjelenitett >= 5:
            break
        
        if tr["tipus"] == "ebed" and tr["fizette"] in tagok:
            st.caption(f"🕒 {tr['datum']} | **{tr['fizette']}** fizetett `{tr['osszeg']:,} Ft`-ot. Résztvevők: {', '.join([r for r in tr['resztvevok'] if r in tagok])}".replace(",", " "))
            megjelenitett += 1
        elif tr["tipus"] == "torles" and tr["kitol"] in tagok and tr["kinek"] in tagok:
            st.caption(f"🕒 {tr['datum']} | 💸 **{tr['kitol']}** megadta a tartozását **{tr['kinek']}** részére (`{tr['osszeg']:,} Ft`)".replace(",", " "))
            megjelenitett += 1
            
    if st.button("🗑️ Összes adat törlése (Alaphelyzet)"):
        clear_all_tranzakciok_on_sheets()
        st.success("Minden adat törölve a Google Táblázatból!")
        st.rerun()
