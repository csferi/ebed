import streamlit as st
import json
import os
from datetime import datetime

# Adatfájl útvonala
DATA_FILE = "ebed_adatok.json"

# Adatszerkezet betöltése/létrehozása
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"tagok": ["Anna", "Balázs", "Gábor", "Dóra"], "tranzakciok": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if "data" not in st.session_state:
    st.session_state.data = load_data()

data = st.session_state.data

st.title("🍔 Munkahelyi Ebéd Elszámoló")

# --- Tartozások kiszámítása (Mátrix logika - a törlés ellenőrzéséhez előre kell hoznunk) ---
tagok = data["tagok"]
matrix = {t1: {t2: 0.0 for t2 in tagok} for t1 in tagok}

for tr in data["tranzakciok"]:
    if tr["tipus"] == "ebed":
        fizette = tr["fizette"]
        resztvevok = tr["resztvevok"]
        # Csak akkor vesszük figyelembe a tranzakciót, ha a szereplői még létező tagok
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

# Segédfüggvény: Ellenőrzi, hogy egy tagnak van-e bármilyen aktív tartozása vagy követelése
def van_tartozasa(tag):
    for nt in netto_tartozasok:
        if nt["kitol"] == tag or nt["kinek"] == tag:
            return True
    return False


# --- 1. OLDALSÁV: Tagok hozzáadása és KÖNNYŰ TÖRLÉSE ---
with st.sidebar:
    st.header("👥 Csapattagok kezelése")
    
    # Hozzáadás
    uj_tag = st.text_input("Új tag hozzáadása:")
    if st.button("➕ Hozzáadás") and uj_tag:
        if uj_tag not in data["tagok"]:
            data["tagok"].append(uj_tag)
            save_data(data)
            st.success(f"{uj_tag} hozzáadva!")
            st.rerun()
            
    st.divider()
    
    # Törlés
    st.subheader("Személy eltávolítása")
    if data["tagok"]:
        torlendo_tag = st.selectbox("Ki távozik?", data["tagok"])
        if st.button("❌ Tag törlése", type="primary"):
            if van_tartozasa(torlendo_tag):
                st.error(f"**{torlendo_tag}** nem törölhető, mert még van aktív elszámolatlan tartozása vagy követelése! Előbb nullázzátok az egyenlegét.")
            else:
                data["tagok"].remove(torlendo_tag)
                # Opcionális finomítás: megtisztítjuk a régi tranzakciós előzményeket a törölt tagtól,
                # hogy ne foglalja a helyet feleslegesen, ha már nullán volt.
                save_data(data)
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
        resztvevok = st.multiselect("Kiknek hozott ebédet? (A fizetőt is jelöld be, ha evett!)", tagok, default=[fizette])
        
        if st.form_submit_button("Ebéd rögzítése"):
            if osszeg > 0 and resztvevok:
                uj_tr = {
                    "id": datetime.now().timestamp(),
                    "tipus": "ebed",
                    "fizette": fizette,
                    "osszeg": osszeg,
                    "resztvevok": resztvevok,
                    "datum": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                data["tranzakciok"].append(uj_tr)
                save_data(data)
                st.success("Ebéd elmentve!")
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
                    "kitol": kitol,
                    "kinek": kinek,
                    "osszeg": aktualis_visszafizetendo,
                    "datum": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                data["tranzakciok"].append(uj_tr)
                save_data(data)
                st.success(f"{kitol} -> {kinek} tartozás rendezve!")
                st.rerun()


# --- 4. Előzmények ---
st.divider()
st.subheader("📜 Utolsó tranzakciók")
if data["tranzakciok"]:
    # Csak azokat a tranzakciókat mutatjuk, ahol a szereplők még léteznek (nem lettek törölve)
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
        data["tranzakciok"] = []
        save_data(data)
        st.success("Minden adat törölve!")
        st.rerun()