"""Misura dei tempi di risposta della chat con un copione fisso.

Stato iniziale: le 22 prenotazioni accettate di sabato_pieno (out/confronto_proposte/mai), in una cartella temporanea.
Copione: 10 messaggi compatti (proposte in fascia piena, posti liberi, un annullamento seguito da una richiesta che
prima non entrava, una conferma). Per ogni messaggio: risposta, tempo, e se la tabella delle disponibilità era pronta.

Uso:
    .venv\\Scripts\\python.exe misura_chat.py                      # come la chat (tabella in background se disponibile)
    .venv\\Scripts\\python.exe misura_chat.py --attendi-tabella    # ogni messaggio parte a tabella pronta
    .venv\\Scripts\\python.exe misura_chat.py --senza-tabella      # solo verifica diretta
    .venv\\Scripts\\python.exe misura_chat.py --turni              # sala a turni (dati/sala_turni.json), copione adattato

A turni lo stato iniziale sono le 21 prenotazioni accettate entro venerdì 30/10 alle 16:00 nel replay in ordine di
arrivo (turni, disposizione fissa, politica "mai": out/confronto_turni/fissa_mai, prodotto da confronto.py): il primo
turno ha 8 prenotazioni, il secondo 13 ed è pieno.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

RADICE = Path(__file__).resolve().parent
sys.path.insert(0, str(RADICE))

COPIONE = [
    "annulla Rizzo sab",          # libera 4 moduli: da qui il conteggio non basta più, servono le dimostrazioni
    "Gallo 5 sab 20:00",          # prima non entrava (rifiutata nel replay in ordine di arrivo)
    "Neri 4 sab 21:30",           # posto libero
    "Pace 2 sab 21:45",           # fascia piena: proposta
    "ok",                         # conferma della proposta
    "Moro 2 sab 20:15",           # fascia piena: proposta
    "Sala 4 sab 20:00",           # fascia piena: proposta
    "Lupi 2 sab 21:45",           # fascia piena: proposta
    "Verdi 4 sab 20:45",          # fascia piena
    "Esposti 2 sab 19:00",        # posto libero
]


COPIONE_TURNI = [
    "annulla Rizzo sab",          # libera il tavolo da 10 del secondo turno
    "Giordano 4 sab 21:00",       # prima non entrava (turno pieno nel replay); le 21:00 vanno nel secondo turno
    "Caruso 2 sab 2t",            # anche lei rifiutata nel replay: ora c'è posto
    "Sala 4 sab 21:30",           # secondo turno pieno: proposta del primo
    "ok",                         # conferma della proposta
    "Lupi 2 sab 2t",              # secondo turno pieno: proposta
    "Moro 2 sab 21:15",           # secondo turno pieno: proposta
    "Verdi 4 sab 21:45",          # secondo turno pieno: proposta
    "Pace 2 sab 1t",              # posto libero
    "Neri 4 sab 19:00",           # lontano dai turni: propone il primo senza registrare
]


class SenzaLLM:
    """Il copione è tutto in formato compatto: l'LLM non serve (e non va chiamato)."""
    disponibile = False


def stato_iniziale(cartella: Path) -> None:
    from ristorante.serate import scrivi_json_atomico, serata_vuota
    sol = json.loads((RADICE / "out" / "confronto_proposte" / "mai" / "soluzione.json").read_text(encoding="utf-8"))
    reg = {r["id"]: r for r in sol["registro"]}
    st = serata_vuota(date(2026, 10, 31))
    for i, a in enumerate(sorted(sol["assegnazioni"], key=lambda a: reg[a["id"]]["prenotata_il"]), 1):
        st["accettate"].append({"id": f"C20261031-{i:03d}", "nome": a["nome"], "coperti": a["coperti"],
                                "orario": a["orario_assegnato"], "orario_richiesto": a["orario_richiesto"],
                                "note": a.get("note", ""), "prenotata_il": reg[a["id"]]["prenotata_il"] + ":00",
                                "mittente": "importata"})
    st["contatore"] = len(st["accettate"])
    scrivi_json_atomico(cartella / "2026-10-31.json", st)


def stato_iniziale_turni(cartella: Path) -> None:
    from ristorante.serate import scrivi_json_atomico, serata_vuota
    sol = json.loads((RADICE / "out" / "confronto_turni" / "fissa_mai" / "soluzione.json").read_text(encoding="utf-8"))
    reg = {r["id"]: r for r in sol["registro"]}
    st = serata_vuota(date(2026, 10, 31))
    entro = [a for a in sol["assegnazioni"] if reg[a["id"]]["prenotata_il"] < "2026-10-30T16:00"]
    for i, a in enumerate(sorted(entro, key=lambda a: reg[a["id"]]["prenotata_il"]), 1):
        st["accettate"].append({"id": f"C20261031-{i:03d}", "nome": a["nome"], "coperti": a["coperti"],
                                "orario": a["orario_assegnato"], "orario_richiesto": a["orario_richiesto"],
                                "turno": a["turno"], "note": a.get("note", ""),
                                "prenotata_il": reg[a["id"]]["prenotata_il"] + ":00", "mittente": "importata"})
    st["contatore"] = len(st["accettate"])
    scrivi_json_atomico(cartella / "2026-10-31.json", st)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attendi-tabella", action="store_true")
    ap.add_argument("--senza-tabella", action="store_true")
    ap.add_argument("--processi", type=int, default=None)
    ap.add_argument("--worker", type=int, default=None)
    ap.add_argument("--json", default=None, help="salva le misure in questo file")
    ap.add_argument("--turni", action="store_true", help="sala a turni e copione adattato")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    from ristorante import conversazione
    from ristorante.dati import leggi_json
    sala = leggi_json(RADICE / "dati" / ("sala_turni.json" if a.turni else "sala_esempio.json"))
    copione = COPIONE_TURNI if a.turni else COPIONE
    t_import = time.perf_counter() - t0
    disp = None
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        try:
            cartella = Path(tmp)
            (stato_iniziale_turni if a.turni else stato_iniziale)(cartella)
            if not a.senza_tabella and hasattr(conversazione, "avvia_disponibilita"):
                t1 = time.perf_counter()
                disp = conversazione.avvia_disponibilita(cartella, sala, processi=a.processi, worker=a.worker,
                                                         oggi=date(2026, 10, 30))
                print(f"Processi di calcolo avviati in {time.perf_counter() - t1:.1f} s")
            ora = datetime(2026, 10, 30, 11, 0)
            misure = []
            if disp is not None and a.attendi_tabella:
                pronta, t_ric = disp.attendi_tabella(date(2026, 10, 31), timeout=600)
                print(f"Tabella iniziale pronta: {pronta} in {t_ric:.1f} s")
            from ristorante.serate import Archivio
            arch = Archivio(cartella)
            for i, msg in enumerate(copione, 1):
                pronta = disp.tabella_pronta(date(2026, 10, 31)) if disp is not None else None
                versione = arch.carica(date(2026, 10, 31)).get("versione", 0)
                t1 = time.perf_counter()
                risposta = conversazione.gestisci_messaggio(msg, ora + timedelta(minutes=i), "proprietario", cartella,
                                                           sala=sala, lettore=SenzaLLM())
                dt = time.perf_counter() - t1
                cambiato = arch.carica(date(2026, 10, 31)).get("versione", 0) != versione
                misure.append({"messaggio": msg, "risposta": risposta, "tempo_s": round(dt, 3), "tabella_pronta": pronta,
                               "stato_cambiato": cambiato})
                print(f"{i:2d}. [{dt:6.2f} s · tabella {'pronta' if pronta else ('non pronta' if pronta is False else 'n/a')}] "
                      f"{msg} → {risposta}", flush=True)
                if disp is not None and a.attendi_tabella and cambiato:
                    ok, t_ric = disp.attendi_tabella(date(2026, 10, 31), timeout=600)
                    misure[-1]["ricalcolo_tabella_s"] = round(t_ric, 2)
                    print(f"      stato cambiato, tabella ricalcolata: {ok} in {t_ric:.1f} s", flush=True)
        finally:
            conversazione.ferma_disponibilita()     # anche dopo un errore: niente processi appesi
    tempi = [m["tempo_s"] for m in misure]
    print(f"Avvio (import) {t_import:.1f} s · risposte: mediana {statistics.median(tempi):.2f} s, massimo {max(tempi):.2f} s")
    for etichetta, valore in (("tabella pronta", True), ("tabella non pronta", False)):
        t = [m["tempo_s"] for m in misure if m["tabella_pronta"] is valore]
        if t:
            print(f"  con {etichetta}: {len(t)} messaggi, mediana {statistics.median(t):.2f} s, massimo {max(t):.2f} s")
    ric = [m["ricalcolo_tabella_s"] for m in misure if "ricalcolo_tabella_s" in m]
    if ric:
        print(f"Ricalcolo tabella dopo ogni messaggio: mediana {statistics.median(ric):.1f} s, massimo {max(ric):.1f} s")
    if a.json:
        Path(a.json).write_text(json.dumps(misure, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
