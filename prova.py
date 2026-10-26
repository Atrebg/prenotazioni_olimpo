"""Risposta al telefono: "c'è posto?".

Legge uno stato (una soluzione.json: prenotazioni già accettate con l'orario promesso) e una richiesta, e risponde
in italiano in una o due righe. Non scrive nessun file: la registrazione arriverà con il canale WhatsApp.

Uso:
    .venv\\Scripts\\python.exe prova.py --coperti 4 --orario 20:00
    .venv\\Scripts\\python.exe prova.py --stato out\\soluzione.json --sala dati\\sala_esempio.json --coperti 2 --orario 21:30
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent
sys.path.insert(0, str(RADICE))

from ristorante.dati import (  # noqa: E402
    MOTIVO_TROPPO_GRANDE,
    ErroreDati,
    costruisci_istanza,
    hhmm_a_min,
    min_a_hhmm,
)
from ristorante.modello import _Voce, _cfg_solver, _parametri, valuta_richiesta  # noqa: E402


def rispondi(sala: dict, stato: dict, coperti: int, orario: str, tempo_s: float | None = None) -> str:
    """Testo della risposta (una o due righe). Solleva ErroreDati se la richiesta non è valida."""
    pren = [{"id": r["id"], "nome": r["nome"], "coperti": r["coperti"], "orario": r["orario_richiesto"]}
            for r in stato.get("assegnazioni", [])]
    pren.append({"id": "_richiesta_", "nome": "richiesta", "coperti": coperti, "orario": orario})
    giorno = (stato.get("serata") or "Stasera").split()[0]
    ist = costruisci_istanza(sala, {"serata": giorno, "prenotazioni": pren})
    per_id = {p.id: p for p in ist.prenotazioni}
    accettate = []
    for r in stato.get("assegnazioni", []):
        p = per_id[r["id"]]
        accettate.append(_Voce(p, [(r["spostamento_min"], ist.a_passi(hhmm_a_min(r["orario_assegnato"])))], True))
    disposizione = stato.get("modalita", {}).get("disposizione") or ist.disposizione
    tempo_s = float(tempo_s if tempo_s is not None else _cfg_solver(ist, "tempo_proposta_s", 60))
    worker, seed = _parametri(ist, None, None)
    dec = valuta_richiesta(ist, accettate, per_id["_richiesta_"], disposizione, tempo_s,
                           _cfg_solver(ist, "tempo_spareggio_s", 20), tempo_s, worker, seed, cerca_proposte=True)
    rich = hhmm_a_min(orario)
    if ist.turni:           # sala a turni: l'orario va nel turno più vicino, le proposte sono gli altri turni
        tu = ist.turni[ist.turno_della(per_id["_richiesta_"])]
        chiesto = f"{tu.nome} turno ({min_a_hhmm(tu.inizio_min)})"
        if dec.esito == "accettata":
            return f"Sì, nel {chiesto} c'è posto."
        if dec.esito == "proposta":
            altri = [ist.turni[ist.turno_da_passo(p["inizio"])] for p in (dec.prima, dec.dopo) if p is not None]
            return (f"Il {tu.nome} turno è pieno. Posso "
                    + " oppure ".join(f"nel {t.nome}, alle {min_a_hhmm(t.inizio_min)}" for t in altri) + ".")
        if dec.motivo == MOTIVO_TROPPO_GRANDE:
            return f"Per {coperti} persone non ho un tavolo abbastanza grande."
        if dec.decisione == "impossibile (dimostrato)":
            return f"{giorno} tutti i turni sono pieni."
        return f"Il {chiesto}: non riesco a confermarlo subito (verifica non chiusa entro {tempo_s:g} s)."
    if dec.esito == "accettata":
        if dec.spostamento == 0:
            return f"Sì, alle {orario} c'è posto."
        return f"Alle {orario} no, alle {min_a_hhmm(rich + dec.spostamento)} sì."
    if dec.esito == "proposta":
        orari = [min_a_hhmm(rich + p["spostamento"]) for p in (dec.prima, dec.dopo) if p is not None]
        return f"Alle {orario} sono pieno. Posso alle {' oppure alle '.join(orari)}."
    if dec.motivo == MOTIVO_TROPPO_GRANDE:
        return f"Per {coperti} persone non ho un tavolo abbastanza grande."
    if dec.decisione == "impossibile (dimostrato)":
        return f"{giorno} sono pieno fino a {ist.proposta_max_distanza_min} minuti dall'orario chiesto."
    return (f"Alle {orario} non riesco a confermarlo subito: la verifica non si è chiusa entro {tempo_s:g} s.\n"
            f"Ti richiamo appena ho la risposta.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="C'è posto? Risposta al telefono (non scrive file)")
    ap.add_argument("--stato", default=str(RADICE / "out" / "soluzione.json"),
                    help="soluzione.json con le prenotazioni accettate")
    ap.add_argument("--sala", default=str(RADICE / "dati" / "sala_esempio.json"))
    ap.add_argument("--coperti", type=int, required=True)
    ap.add_argument("--orario", required=True, help="HH:MM sulla griglia da 15 minuti")
    ap.add_argument("--tempo", type=float, default=None, help="limite del solver per ogni orario provato (s)")
    a = ap.parse_args(argv)
    with open(a.sala, encoding="utf-8") as fh:
        sala = json.load(fh)
    with open(a.stato, encoding="utf-8") as fh:
        stato = json.load(fh)
    try:
        print(rispondi(sala, stato, a.coperti, a.orario, a.tempo))
    except ErroreDati as exc:
        print(f"Richiesta non valida: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
