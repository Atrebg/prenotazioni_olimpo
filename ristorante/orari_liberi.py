"""Prototipo indipendente per confronti: orari liberi sulla piantina Olimpo.

Non legge né modifica lo stato della chat esistente.
"""
from __future__ import annotations

from dataclasses import dataclass
from ortools.sat.python import cp_model
from .piantina import Piantina, LUNGO_DUE_GRUPPI

DURATE = ((2, 90), (4, 105), (None, 120))


def durata(coperti: int) -> int:
    if isinstance(coperti, bool) or not isinstance(coperti, int) or coperti <= 0:
        raise ValueError("coperti deve essere un intero positivo")
    return next(minuti for limite, minuti in DURATE if limite is None or coperti <= limite)


def minuti(ora: str) -> int:
    try:
        a, b = ora.split(":")
        if len(a) != 2 or len(b) != 2 or not a.isdigit() or not b.isdigit():
            raise ValueError
        h, m = int(a), int(b)
        if h > 23 or m > 59:
            raise ValueError
        return h * 60 + m
    except (ValueError, AttributeError):
        raise ValueError(f"orario non valido: {ora!r}") from None


def valida_richieste(prenotazioni: list[dict], apertura=19 * 60, chiusura=24 * 60) -> None:
    ids = set()
    for p in prenotazioni:
        if not isinstance(p.get("id"), str) or not p["id"] or p["id"] in ids:
            raise ValueError("id mancante o duplicato")
        ids.add(p["id"])
        inizio = minuti(p["orario"])
        if inizio < apertura or inizio + durata(p["coperti"]) > chiusura:
            raise ValueError(f"{p['id']}: fuori dal servizio")


def _conflitto(u, v, cop_u: int, cop_v: int) -> bool:
    if u.tavolo != v.tavolo:
        return False
    if u.tipo == "lungo":
        return u.gruppo == v.gruppo or max(cop_u, cop_v) > LUNGO_DUE_GRUPPI
    if u.quadrati is not None and v.quadrati is not None:
        return max(u.quadrati[0], v.quadrati[0]) <= min(u.quadrati[1], v.quadrati[1])
    return True


def si_sovrappongono(a: dict, b: dict) -> bool:
    x, y = minuti(a["orario"]), minuti(b["orario"])
    return x < y + durata(b["coperti"]) and y < x + durata(a["coperti"])


def verifica(pia: Piantina, prenotazioni: list[dict], piano: dict[str, str]) -> list[str]:
    """Controllo separato dell'assegnazione restituita da un algoritmo o agente."""
    try:
        valida_richieste(prenotazioni)
    except ValueError as exc:
        return [str(exc)]
    errori = []
    unita = {u.chiave: u for u in pia.unita()}
    ids = {p["id"] for p in prenotazioni}
    if set(piano) != ids:
        errori.append("Il piano deve assegnare esattamente tutte le prenotazioni")
    for p in prenotazioni:
        u = unita.get(piano.get(p["id"]))
        if u is None:
            errori.append(f"{p['id']}: unità sconosciuta")
        elif u.posti < p["coperti"]:
            errori.append(f"{p['id']}: capienza insufficiente")
    for i, p in enumerate(prenotazioni):
        u = unita.get(piano.get(p["id"]))
        if not u:
            continue
        for q in prenotazioni[i + 1:]:
            v = unita.get(piano.get(q["id"]))
            if v and si_sovrappongono(p, q) and _conflitto(u, v, p["coperti"], q["coperti"]):
                errori.append(f"{p['id']} e {q['id']}: occupazioni incompatibili")
    return errori


@dataclass
class Esito:
    stato: str
    piano: dict[str, str] | None


def risolvi(pia: Piantina, prenotazioni: list[dict], tempo_s: float = 20) -> Esito:
    """Un piano possibile, oppure impossibilità dimostrata o risposta non conclusiva."""
    valida_richieste(prenotazioni)
    modello = cp_model.CpModel()
    unita = pia.unita()
    scelte = {}
    for p in prenotazioni:
        for u in unita:
            if u.posti >= p["coperti"]:
                scelte[p["id"], u.chiave] = modello.new_bool_var(f"{p['id']}:{u.chiave}")
        modello.add_exactly_one([scelte[p["id"], u.chiave] for u in unita if (p["id"], u.chiave) in scelte])
    for i, p in enumerate(prenotazioni):
        for q in prenotazioni[i + 1:]:
            if not si_sovrappongono(p, q):
                continue
            for u in unita:
                a = scelte.get((p["id"], u.chiave))
                if a is None:
                    continue
                for v in unita:
                    b = scelte.get((q["id"], v.chiave))
                    if b is not None and _conflitto(u, v, p["coperti"], q["coperti"]):
                        modello.add(a + b <= 1)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = tempo_s
    solver.parameters.num_search_workers = 1
    stato = solver.solve(modello)
    if stato in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        piano = {p["id"]: u.chiave for p in prenotazioni for u in unita
                 if (p["id"], u.chiave) in scelte and solver.value(scelte[p["id"], u.chiave])}
        errori = verifica(pia, prenotazioni, piano)
        if errori:
            raise RuntimeError("Piano non valido: " + "; ".join(errori))
        return Esito("entra", piano)
    return Esito("non entra" if stato == cp_model.INFEASIBLE else "non verificato", None)
