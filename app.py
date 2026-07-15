def load_data_from_sheets():
    # Tagok betöltése
    tagok_raw = sheet_tagok.col_values(1)
    if not tagok_raw:
        default_tagok = ["Anna", "Balázs", "Gábor", "Dóra"]
        sheet_tagok.update("A1:A" + str(len(default_tagok)), [[t] for t in default_tagok])
        tagok_raw = default_tagok
    
    # Biztonsági ellenőrzés a Tranzakciókhoz: Ha teljesen üres a lap, létrehozzuk a fejlécet
    elsosor = sheet_tranzakciok.row_values(1)
    fejlecek = ["id", "tipus", "fizette", "osszeg", "resztvevok", "kitol", "kinek", "datum"]
    if not elsosor:
        sheet_tranzakciok.append_row(fejlecek)
    
    # Tranzakciók betöltése
    tranzakciok_raw = sheet_tranzakciok.get_all_records()
    tranzakciok = []
    for row in tranzakciok_raw:
        # Csak akkor dolgozzuk fel, ha érvényes sor (pl. van id-ja)
        if row.get("id"):
            tranzakciok.append({
                "id": float(row["id"]),
                "tipus": row["tipus"],
                "fizette": row["fizette"],
                "osszeg": int(row["osszeg"]) if row["osszeg"] else 0,
                "resztvevok": json.loads(row["resztvevok"]) if row["resztvevok"] else [],
                "kitol": row["kitol"],
                "kinek": row["kinek"],
                "datum": row["datum"]
            })
    
    return {"tagok": tagok_raw, "tranzakciok": tranzakciok}
