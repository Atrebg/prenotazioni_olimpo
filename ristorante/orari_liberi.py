"""Prototipo indipendente per confronti: orari liberi sulla piantina Olimpo.

Non legge né modifica lo stato della chat esistente.
"""
from __future__ import annotations

from dataclasses import dataclass
from ortools.sat.python import cp_model
from .piantina import Piantina, LUNGO_DUE_GRUPPI

DURATA_STANDARD_MIN = 90


def durata(coperti: int) -> int:
    if isinstance(coperti, bool) or not isinstance(coperti, int) or coperti <= 0:
        raise ValueError("coperti deve essere un intero positivo")
    return DURATA_STANDARD_MIN


def durata_prenotazione(p: dict) -> int:
    """Le durate ridotte sono vincoli espliciti già accettati o proposte in verifica."""
    normale = durata(p["coperti"])
    ridotta = p.get("durata_concordata_min", normale)
    if isinstance(ridotta, bool) or not isinstance(ridotta, int) or not 1 <= ridotta <= normale:
        raise ValueError("durata concordata non valida")
    return ridotta


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
        if inizio < apertura or inizio + durata_prenotazione(p) > chiusura:
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
    return x < y + durata_prenotazione(b) and y < x + durata_prenotazione(a)


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


def valuta_con_uscita_anticipata(pia: Piantina, accettate: list[dict], nuova: dict,
                                  tempo_s: float = 20) -> dict:
    """Cerca prima 90 minuti, poi una proposta di uscita, senza registrare nulla.

    Il chiamante deve chiedere e ricevere un sì esplicito; dopo il sì deve ricontrollare
    con risolvi contro lo stato corrente, conservando durata_concordata_min.
    """
    if "durata_concordata_min" in nuova:
        raise ValueError("Una nuova richiesta deve partire dalla durata standard")
    valida_richieste(accettate)
    start = minuti(nuova["orario"])
    durata(nuova["coperti"])
    if not 19 * 60 <= start < 24 * 60:
        raise ValueError("richiesta fuori dal servizio")
    if start + DURATA_STANDARD_MIN <= 24 * 60:
        esito = risolvi(pia, accettate + [nuova], tempo_s)
        if esito.stato != "non entra":
            return {"stato": esito.stato, "piano": esito.piano}
    # Le disponibilità possono cambiare solo quando inizia una prenotazione o il servizio termina.
    fini = {minuti(p["orario"]) for p in accettate}
    fini.add(24 * 60)
    for fine in sorted((t for t in fini if start < t < start + DURATA_STANDARD_MIN), reverse=True):
        proposta = nuova | {"durata_concordata_min": fine - start}
        esito = risolvi(pia, accettate + [proposta], tempo_s)
        if esito.stato == "non verificato":
            return {"stato": "non verificato", "piano": None}
        if esito.stato == "entra":
            return {"stato": "proposta", "fine": f"{fine // 60:02}:{fine % 60:02}",
                    "prenotazione_proposta": proposta, "piano": esito.piano}
    return {"stato": "non entra", "piano": None}
