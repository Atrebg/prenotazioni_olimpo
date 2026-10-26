"""Chat 1:1 con il proprietario, da riga di comando (simula il canale WhatsApp che arriverà dopo).

Il processo resta vivo, così OR-Tools si carica una volta sola. Ogni risposta riporta il tempo impiegato.
In modalità interattiva parte anche la tabella delle disponibilità, calcolata in background su processi separati
(--senza-tabella la spegne; processi e worker da `chat` della sala oppure da --processi/--worker).

Uso:
    .venv\\Scripts\\python.exe chat.py                                    # chat interattiva ("esci" per uscire)
    .venv\\Scripts\\python.exe chat.py --messaggio "Rossi 4 sab 20:30"    # un colpo solo
    .venv\\Scripts\\python.exe chat.py --ora 2026-10-27T10:00             # finge l'orologio
    .venv\\Scripts\\python.exe chat.py --senza-tabella                     # senza tabella: verifica diretta
    .venv\\Scripts\\python.exe chat.py --sala dati\\sala_turni.json            # ristorante a turni (Rossi 4 sab 1t)
    .venv\\Scripts\\python.exe chat.py --piantina 2026-10-31              # piantina della serata + verifica
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

RADICE = Path(__file__).resolve().parent
sys.path.insert(0, str(RADICE))

t_import = time.perf_counter()
from ristorante.conversazione import (avvia_disponibilita, cfg_chat, ferma_disponibilita,  # noqa: E402
                                      gestisci_messaggio, lettore_predefinito, piantina_serata)
from ristorante.dati import leggi_json  # noqa: E402
T_IMPORT = time.perf_counter() - t_import


class Orologio:
    """Ora reale, oppure quella finta di --ora che avanza col tempo trascorso."""

    def __init__(self, finta: str | None):
        self.base = datetime.fromisoformat(finta) if finta else None
        self.t0 = time.monotonic()

    def adesso(self) -> datetime:
        if self.base is None:
            return datetime.now().replace(microsecond=0)
        return (self.base + timedelta(seconds=time.monotonic() - self.t0)).replace(microsecond=0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Chat con il motore delle prenotazioni")
    ap.add_argument("--cartella", default=str(RADICE / "dati" / "serate"), help="stato delle serate")
    ap.add_argument("--sala", default=str(RADICE / "dati" / "sala_esempio.json"))
    ap.add_argument("--mittente", default="proprietario")
    ap.add_argument("--ora", default=None, help="orologio finto, es. 2026-10-27T10:00")
    ap.add_argument("--messaggio", default=None, help="un solo messaggio, poi esce")
    ap.add_argument("--piantina", default=None, help="AAAA-MM-GG: disposizione dei tavoli della serata e verifica")
    ap.add_argument("--senza-tabella", action="store_true", help="niente tabella delle disponibilità in background")
    ap.add_argument("--processi", type=int, default=None, help="processi di calcolo della tabella")
    ap.add_argument("--worker", type=int, default=None, help="worker CP-SAT per processo")
    a = ap.parse_args(argv)
    sala = leggi_json(a.sala)
    if a.piantina:
        d = date.fromisoformat(a.piantina)
        sol, p_pren, p_sol = piantina_serata(a.cartella, d, sala)
        print(f"Piantina {d:%d/%m}: {sol['solver']['stato']} in {sol['solver']['tempo_s']} s · "
              f"{len(sol['assegnazioni'])} prenotazioni · {len(sol['tavoli'])} tavoli · {p_sol.parent / 'serata.html'}")
        return subprocess.run([sys.executable, str(RADICE / "verifica.py"), "--sala", a.sala, "--prenotazioni",
                               str(p_pren), "--soluzione", str(p_sol)]).returncode
    orologio = Orologio(a.ora)
    lett = lettore_predefinito(sala)
    stato_llm = "attiva (" + lett.modello + ", effort " + lett.effort + ")" if lett.disponibile else \
        "disattivata: manca la chiave ANTHROPIC_API_KEY, si legge solo il formato compatto"
    if a.messaggio is not None:
        t0 = time.perf_counter()
        print(gestisci_messaggio(a.messaggio, orologio.adesso(), a.mittente, a.cartella, sala=sala))
        print(f"({time.perf_counter() - t0:.2f} s; avvio {T_IMPORT:.1f} s)")
        return 0
    stato_tabella = "spenta (verifica diretta a ogni messaggio)"
    if not a.senza_tabella:
        t0 = time.perf_counter()
        c = cfg_chat(sala)
        avvia_disponibilita(a.cartella, sala, processi=a.processi, worker=a.worker, oggi=orologio.adesso().date())
        stato_tabella = (f"in background, {a.processi or c['processi']} processi x "
                         f"{a.worker or c['worker_per_processo']} worker CP-SAT (avviata in {time.perf_counter() - t0:.1f} s)")
    print(f"Chat pronta (avvio {T_IMPORT:.1f} s). Lettura via LLM: {stato_llm}. Tabella delle disponibilità: "
          f"{stato_tabella}. Scrivi 'esci' per uscire.")
    try:
        while True:
            try:
                testo = input("> ")
            except EOFError:
                break
            if testo.strip().lower() in ("esci", "exit", "quit"):
                break
            if not testo.strip():
                continue
            t0 = time.perf_counter()
            risposta = gestisci_messaggio(testo, orologio.adesso(), a.mittente, a.cartella, sala=sala)
            print(f"{risposta}\n  ({time.perf_counter() - t0:.2f} s)", flush=True)
    finally:
        ferma_disponibilita()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    sys.exit(main())
