"""Valutazione della lettura dei messaggi via LLM: passa ogni messaggio di valutazione/messaggi.jsonl a Claude,
applica gli stessi controlli del codice della chat (date, servizio serale, arrotondamenti) e confronta campo per
campo con l'atteso. Stampa la precisione per campo e l'elenco degli errori.

Gira solo se c'è la chiave (ANTHROPIC_API_KEY nel processo o nelle variabili utente di Windows); altrimenti esce
dicendolo, senza errore. Ogni esecuzione chiama l'API (costo reale, piccolo con claude-haiku-5-5 a effort low).

Uso:
    .venv\\Scripts\\python.exe valuta_lettura.py [--modello claude-haiku-5-5] [--effort low] [--solo 10]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

RADICE = Path(__file__).resolve().parent
sys.path.insert(0, str(RADICE))

from ristorante.conversazione import _Conversazione, cfg_chat, lettura_da_llm  # noqa: E402
from ristorante.dati import leggi_json  # noqa: E402
from ristorante.lettura import LettoreAnthropic, LLMNonDisponibile, leggi_compatto, normalizza, trova_chiave  # noqa: E402
from ristorante.serate import Archivio  # noqa: E402

CAMPI = ["intento", "nome", "coperti", "data", "orario", "riferimento_nome", "riferimento_data"]


def carica_messaggi(percorso: Path) -> list[dict]:
    return [json.loads(r) for r in percorso.read_text(encoding="utf-8").splitlines() if r.strip()]


def valore(lett, campo):
    v = getattr(lett, campo)
    return v.isoformat() if isinstance(v, date) else v


def confronta(lett, atteso: dict) -> list[tuple]:
    """Campi diversi dall'atteso: [(campo, atteso, letto)]. Solo i campi presenti in `atteso` (null = deve mancare)."""
    errori = []
    for campo, att in atteso.items():
        letto = valore(lett, campo)
        if campo in ("nome", "riferimento_nome"):
            ok = (normalizza(letto) if letto else None) == (normalizza(att) if att else None)
        else:
            ok = letto == att
        if not ok:
            errori.append((campo, att, letto))
    return errori


def leggi(voce: dict, sala: dict, cartella: Path, lettore=None):
    """Lettura come la farebbe la chat: con `lettore` via LLM, senza solo il formato compatto (None se non è compatto)."""
    ora = datetime.fromisoformat(voce["ricevuto_il"])
    conv = _Conversazione(Archivio(cartella), sala, lettore, ora, "valutazione")
    if lettore is None:
        lett = leggi_compatto(voce["testo"])
        if lett is None:
            return None
    else:
        r = lettore.leggi(voce["testo"], ora, sala["servizio"]["inizio"], sala["servizio"]["fine"],
                          voce.get("contesto", ""))
        lett = lettura_da_llm(r)
    conv._valida(lett)
    return lett


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Valutazione della lettura via LLM")
    ap.add_argument("--file", default=str(RADICE / "valutazione" / "messaggi.jsonl"))
    ap.add_argument("--sala", default=str(RADICE / "dati" / "sala_esempio.json"))
    ap.add_argument("--modello", default=None)
    ap.add_argument("--effort", default=None)
    ap.add_argument("--solo", type=int, default=None, help="solo i primi N messaggi")
    a = ap.parse_args(argv)
    if trova_chiave() is None:
        print("Manca la chiave ANTHROPIC_API_KEY: valutazione non eseguita (nessuna chiamata all'API).")
        return 0
    from ristorante.piantina import carica_sala
    sala = carica_sala(a.sala)
    c = cfg_chat(sala)
    lettore = LettoreAnthropic(modello=a.modello or c["modello"], effort=a.effort or c["effort"],
                               max_tokens=c["max_tokens"], timeout_s=c["timeout_s"])
    messaggi = carica_messaggi(Path(a.file))[: a.solo]
    giusti = {k: 0 for k in CAMPI}
    totali = {k: 0 for k in CAMPI}
    errori, tempi, tok_in, tok_out = [], [], 0, 0
    with tempfile.TemporaryDirectory() as tmp:
        for voce in messaggi:
            t0 = time.perf_counter()
            try:
                lett = leggi(voce, sala, Path(tmp), lettore)
            except LLMNonDisponibile as e:
                print(f"Interrotta al messaggio {voce['id']}: {e}")
                return 0
            tempi.append(time.perf_counter() - t0)
            if lettore.ultimo_uso is not None:
                tok_in += getattr(lettore.ultimo_uso, "input_tokens", 0) or 0
                tok_out += getattr(lettore.ultimo_uso, "output_tokens", 0) or 0
            sbagliati = confronta(lett, voce["atteso"])
            for campo in voce["atteso"]:
                totali[campo] += 1
                giusti[campo] += all(s[0] != campo for s in sbagliati)
            errori += [(voce["id"], voce["testo"], *s) for s in sbagliati]
    print(f"Modello {lettore.modello}, effort {lettore.effort} · {len(messaggi)} messaggi · "
          f"tempo medio {sum(tempi) / len(tempi):.2f} s · token {tok_in} in / {tok_out} out")
    for campo in CAMPI:
        if totali[campo]:
            print(f"  {campo:<17} {giusti[campo]:>3}/{totali[campo]:<3} {100 * giusti[campo] / totali[campo]:5.1f}%")
    print(f"Errori ({len(errori)}):" if errori else "Nessun errore.")
    for i, testo, campo, att, letto in errori:
        print(f"  #{i} «{testo}»: {campo} atteso {att!r}, letto {letto!r}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
