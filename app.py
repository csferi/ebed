import streamlit as st
import json
import random
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, date
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
    tagok_raw = [t.strip() for t in tagok_raw if t and str(t).strip()]
    if not tagok_raw:
        default_tagok = ["Anna", "Balázs", "Gábor", "Dóra"]
        sheet_tagok.update("A1:A" + str(len(default_tagok)), [[t] for t in default_tagok])
        tagok_raw = default_tagok
    
    # 2. Tranzakciók betöltése
    rows = sheet_tranzakciok.get_all_values()
    fejlecek = ["id", "tipus", "fizette", "osszeg", "resztvevok", "kitol", "kinek", "datum"]
    
    if not rows or not rows[0] or rows[0][0].strip() != "id":
        sheet_tranzakciok.clear()
        sheet_tranzakciok.append_row(fejlecek)
        rows = [fejlecek]
        
    tranzakciok = []
    
    for r in rows[1:]:
        row_data = r + [""] * (len(fejlecek) - len(r))
        row_dict = dict(zip(fejlecek, row_data))
        valodi_id = row_dict.get("id", "").strip()
        
        if valodi_id:
            try:
                resztvevok_str = row_dict.get("resztvevok", "[]").strip()
                resztvevok_list = json.loads(resztvevok_str) if resztvevok_str else []
                
                tranzakciok.append({
                    "id": float(valodi_id),
                    "tipus": str(row_dict.get("tipus", "")).strip(),
                    "fizette": str(row_dict.get("fizette", "")).strip(),
                    "osszeg": float(row_dict.get("osszeg")) if row_dict.get("osszeg") else 0.0,
                    "resztvevok": [str(x).strip() for x in resztvevok_list],
                    "kitol": str(row_dict.get("kitol", "")).strip(),
                    "kinek": str(row_dict.get("kinek", "")).strip(),
                    "datum": str(row_dict.get("datum", "")).strip()
                })
            except Exception:
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

# --- E-mail küldő segédfüggvény az ellenőrzőkódhoz ---
def send_verification_email(code):
    try:
        conf = st.secrets["email"]
        msg = MIMEText(f"Szia Ferenc!\n\nAz ebédelszámoló alkalmazásban valaki kezdeményezte az összes tranzakció törlését.\n\nAz ellenőrző kód: {code}\n\nHa nem te indítottad a folyamatot, hagyd figyelmen kívül ezt a levelet!")
        msg["Subject"] = "Ebéd Elszámoló - Biztonsági törlési kód"
        msg["From"] = conf["sender_email"]
        msg["To"] = "cser.ferenc@dentalplus.hu"
        
        server = smtplib.SMTP(conf["smtp_server"], conf["smtp_port"])
        server.starttls()
        server.login(conf["sender_email"], conf["sender_password"])
        server.sendmail(conf["sender_email"], ["cser.ferenc@dentalplus.hu"], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"Nem sikerült elküldeni az e-mailt: {e}")
        return False

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
                resz_osszeg = tr["osszeg"] 
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
    
    uj_tag = st.text_input("Új tag hozzáadása:")
    if st.button("➕ Hozzáadás") and uj_tag:
        uj_tag_clean = uj_tag.strip()
        if uj_tag_clean and uj_tag_clean not in data["tagok"]:
            data["tagok"].append(uj_tag_clean)
            save_tagok_to_sheets(data["tagok"])
            st.success(f"{uj_tag_clean} hozzáadva!")
            st.rerun()
            
    st.divider()
    
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
        # A kiemelt piros doboz megmarad, mert ez asztali gépen és mobilon is kiválóan látszik
        formatted_osszeg = f"{t['osszeg']:,}".replace(",", " ")
        st.markdown(
            f"🔴 **{t['kitol']}** tartozik **{t['kinek']}** részére: "
            f"<span style='font-size: 18px; font-weight: bold; color: #ff4b4b; background-color: #ffebeb; padding: 2px 8px; border-radius: 5px;'>{formatted_osszeg} Ft</span>", 
            unsafe_allow_html=True
        )
else:
    st.success("🎉 Mindenki nullán van, nincs aktuális tartozás!")

st.divider()

# --- 3. ŰRLAPOK: Új események rögzítése ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("🍱 Új ebéd beírása")
    with st.form("ebed_form", clear_on_submit=True):
        fizette = st.selectbox("Ki fizetett?", tagok)
        osszeg = st.number_input("Adag ára / Fő (Ft):", min_value=0, step=100)
        resztvevok = st.multiselect("Kiknek hozott ebédet? (A fizetőt is jelöld be!)", tagok, default=[])
        ebed_datum = st.date_input("Mikor történt?", value=date.today())
        
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
                    "datum": ebed_datum.strftime("%Y-%m-%d")
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
        torles_datum = st.date_input("Mikor történt a rendezés?", value=date.today())
        
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
                    "datum": torles_datum.strftime("%Y-%m-%d")
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
        
        formatted_osszeg = f"{tr['osszeg']:,}".replace(",", " ")
        
        if tr["tipus"] == "ebed" and tr["fizette"] in tagok:
            # HTML helyett natív Markdown színezés (:green[szöveg]) és félkövérítés (**szöveg**)
            # Ez garantálja, hogy mobilon is tökéletesen az alapértelmezett betűtípust használja a rendszer!
            st.markdown(
                f"🕒 {tr['datum']} | **{tr['fizette']}** fizetett "
                f"**:green[{formatted_osszeg} Ft]**/fő összeget. "
                f"Résztvevők: {', '.join([r for r in tr['resztvevok'] if r in tagok])}"
            )
            megjelenitett += 1
        elif tr["tipus"] == "torles" and tr["kitol"] in tagok and tr["kinek"] in tagok:
            st.markdown(
                f"🕒 {tr['datum']} | 💸 **{tr['kitol']}** megadta a tartozását **{tr['kinek']}** részére "
                f"(**:green[{formatted_osszeg} Ft]**)"
            )
            megjelenitett += 1
            
    # --- Összes adat törlése biztonsági kódos e-mail küldéssel ---
    st.subheader("⚠️ Veszélyes zóna")
    
    if "delete_verification_code" not in st.session_state:
        if st.button("🗑️ Összes adat törlése (Alaphelyzet)", type="primary"):
            code = str(random.randint(100000, 999999))
            st.session_state.delete_verification_code = code
            
            with st.spinner("Ellenőrző kód küldése a cser.ferenc@dentalplus.hu címre..."):
                if send_verification_email(code):
                    st.success("Az ellenőrző kódot sikeresen elküldtük!")
                    st.rerun()
    else:
        st.warning("Biztonsági megerősítés szükséges!")
        beirt_kod = st.text_input("Írd be a cser.ferenc@dentalplus.hu címre küldött 6 jegyű ellenőrző kódot:", value="")
        
        col_ok, col_cancel = st.columns(2)
        with col_ok:
            if st.button("✅ Törlés véglegesítése", type="primary"):
                if beirt_kod.strip() == st.session_state.delete_verification_code:
                    clear_all_tranzakciok_on_sheets()
                    del st.session_state.delete_verification_code
                    st.success("Minden adat törölve a Google Táblázatból!")
                    st.rerun()
                else:
                    st.error("Hibás biztonsági kód! Kérlek, próbáld újra.")
        with col_cancel:
            if st.button("❌ Mégsem"):
                del st.session_state.delete_verification_code
                st.rerun()
