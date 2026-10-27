"""Modello CP-SAT della sala vera (piantina data): i tavoli non si spostano, si decide solo chi siede dove, turno per turno.

Per ogni turno e per ogni unità della piantina (tavolo semplice, gruppo del lungo, pezzo contiguo di un blocco):
- a[i,u] = la prenotazione i siede sull'unità u nel suo turno; ogni unità ospita al più una prenotazione;
- blocchi separabili: act[p] = il pezzo p è nella partizione del turno; ogni quadrato sta in esattamente un pezzo
  attivo; se il blocco è diviso, ogni pezzo attivo ospita una prenotazione (un pezzo vuoto si riunirebbe al vicino);
- lungo: il secondo gruppo (fino a 8) si usa solo se c'è già il primo e il primo ha al più 8 coperti; i posti vuoti
  del lungo sono i suoi posti meno i coperti seduti (un gruppo da 8 da solo lascia vuoti 12 posti).
Obiettivo: non sistemate (solo nella piantina finale) >> posti vuoti per tavolo > divisioni dei blocchi >
cambi di partizione tra un turno e l'altro (riallestimento lieve). Tra tavoli semplici identici (stesso tipo e posti) le
simmetrie si rompono ordinando le prenotazioni per indice.
"""
from __future__ import annotations

from ortools.sat.python import cp_model

from .dati import ErroreDati, Istanza, min_a_hhmm
from .modello import _Modello, _Voce
from .modello_turni import _opzioni_turno
from .piantina import LUNGO_DUE_GRUPPI, Piantina


def _peso(ist: Istanza, chiave: str, default: int) -> int:
    return int(ist.sala.get("pesi", {}).get(chiave, default))


def costruisci_piantina(ist: Istanza, voci: list[_Voce], disposizione: str, obiettivo: str = "completo",
                        non_sistemate_fisse: int = 0, proiezioni: bool = True, rinforzo: bool = True) -> _Modello:
    pia: Piantina = ist.piantina
    m = cp_model.CpModel()
    K = len(ist.turni)
    mod = _Modello(m, [], voci, disposizione=disposizione, turni=True, piantina=True)
    opz = {v.pr.id: _opzioni_turno(ist, v) for v in voci}
    cop_min = min((v.pr.coperti for v in voci), default=1)
    unita = [u for u in pia.unita() if u.posti >= cop_min]
    att: dict[str, object] = {}               # chiave unità.turno -> presenza del pezzo (1 per i tavoli semplici)
    divisioni, cambi = [], []
    for k in range(K):
        for t in pia.tavoli:
            if t["tipo"] != "blocco" or not t.get("separabile"):
                continue
            tid, nq = str(t["id"]), int(t["moduli"])
            pezzi = [u for u in pia.unita_del(t)]
            vars_ = {}
            for u in pezzi:
                vars_[u.quadrati] = m.new_bool_var(f"act_{u.chiave}.k{k}")
                att[f"{u.chiave}.k{k}"] = vars_[u.quadrati]
            for q in range(nq):                    # partizione contigua: ogni quadrato in un solo pezzo
                m.add(sum(v for (a, b), v in vars_.items() if a <= q <= b) == 1)
            intero = vars_[(0, nq - 1)]
            divisioni.append(sum(v for qq, v in vars_.items() if qq != (0, nq - 1)) + intero - 1)
            mod.info_slot[f"t{tid}.k{k}"] = vars_
    if obiettivo == "completo":                    # cambio di partizione tra turni consecutivi (esatto: è nel costo)
        for k in range(1, K):
            for t in pia.tavoli:
                if t["tipo"] != "blocco" or not t.get("separabile"):
                    continue
                tid = str(t["id"])
                prima, ora = mod.info_slot[f"t{tid}.k{k - 1}"], mod.info_slot[f"t{tid}.k{k}"]
                diff = []
                for qq in ora:
                    d = m.new_bool_var(f"dp_t{tid}.q{qq[0]}-{qq[1]}.k{k}")
                    m.add_abs_equality(d, ora[qq] - prima[qq])
                    diff.append(d)
                c = m.new_bool_var(f"camb_t{tid}.k{k}")
                m.add_max_equality(c, diff)
                cambi.append(c)

    occ: dict[str, list] = {}                     # chiave unità.turno -> letterali delle prenotazioni sedute lì
    lungo_grande: dict[str, list] = {}           # lungo del turno: gruppi oltre LUNGO_DUE_GRUPPI sul primo + secondo gruppo
    lungo_primo: dict[str, list] = {}
    lungo_secondo: dict[str, list] = {}
    vuoti, non_sedute = [], []
    indice = {v.pr.id: n + 1 for n, v in enumerate(voci)}
    rank: dict[str, list] = {}                    # tavoli semplici: somma degli indici seduti (rottura simmetrie)
    for v in voci:
        pr = v.pr
        olits = []
        for sm, st, k in opz[pr.id]:
            ov = m.new_bool_var(f"o_{pr.id}_{sm}")
            mod.o[(pr.id, sm)] = ov
            olits.append((k, ov))
        seduta = 1 if v.obbligatoria else m.new_bool_var(f"seduta_{pr.id}")
        if not v.obbligatoria:
            non_sedute.append(1 - seduta)
        m.add(sum(ov for _, ov in olits) == seduta)
        n_el = 0
        for k, ov in olits:
            lits = []
            for u in unita:
                if u.posti < pr.coperti:
                    continue
                ch = f"{u.chiave}.k{k}"
                av = m.new_bool_var(f"a_{pr.id}_{ch}")
                mod.a[(pr.id, ch)] = av
                lits.append(av)
                occ.setdefault(ch, []).append(av)
                if u.gruppo == 2:                  # il lungo conta i posti vuoti una volta sola, sul primo gruppo
                    vuoti.append(-pr.coperti * av)
                    lungo_secondo.setdefault(f"t{u.tavolo}.k{k}", []).append(av)
                else:
                    vuoti.append((u.posti - pr.coperti) * av)
                    if u.gruppo == 1:
                        lungo_primo.setdefault(f"t{u.tavolo}.k{k}", []).append(av)
                if u.gruppo is not None and (u.gruppo == 2 or pr.coperti > LUNGO_DUE_GRUPPI):
                    lungo_grande.setdefault(f"t{u.tavolo}.k{k}", []).append(av)
                if u.quadrati is None and u.gruppo is None:
                    rank.setdefault(ch, []).append(indice[pr.id] * av)
            n_el += len(lits)
            if lits:
                m.add(sum(lits) == ov)
            else:
                m.add(ov == 0)
        if v.obbligatoria and not n_el:
            raise ErroreDati(f"{pr.id}: obbligatoria ma senza tavoli possibili")

    mod.unita = {f"{u.chiave}.k{k}": (u, k) for u in unita for k in range(K)}
    for ch, (u, k) in mod.unita.items():
        lst = occ.get(ch, [])
        if ch in att:                               # pezzo di un blocco
            if u.intero:
                if lst:
                    m.add(sum(lst) <= att[ch])
            elif lst:
                m.add(sum(lst) == att[ch])          # diviso: ogni pezzo attivo è occupato
            else:
                m.add(att[ch] == 0)
        elif len(lst) > 1:
            m.add(sum(lst) <= 1)
    for t in pia.tavoli:            # pezzi troppo piccoli per tutte le prenotazioni: mai separati (l'intero resta, vuoto)
        if t["tipo"] == "blocco" and t.get("separabile"):
            intero = (0, int(t["moduli"]) - 1)
            for k in range(K):
                for qq, var in mod.info_slot[f"t{t['id']}.k{k}"].items():
                    if qq != intero and f"t{t['id']}.q{qq[0]}-{qq[1]}.k{k}" not in mod.unita:
                        m.add(var == 0)
    for lst in lungo_grande.values():               # lungo: un gruppo fino a 20, oppure due fino a 8
        if len(lst) > 1:
            m.add(sum(lst) <= 1)
    for ch, lst in lungo_secondo.items():           # il secondo gruppo solo se c'è il primo
        m.add(sum(lst) <= sum(lungo_primo.get(ch, [])))
    # tavoli semplici identici (stesso tipo e posti), nello stesso turno: prenotazioni in ordine decrescente di indice
    gruppi: dict[tuple, list[str]] = {}
    for u in unita:
        if u.quadrati is None and u.gruppo is None:
            for k in range(K):
                gruppi.setdefault((u.tipo, u.posti, k), []).append(f"{u.chiave}.k{k}")
    for chiavi in gruppi.values():
        for c1, c2 in zip(chiavi, chiavi[1:]):
            if rank.get(c2):
                m.add(sum(rank.get(c1, [])) >= sum(rank[c2]))

    totale = (_peso(ist, "non_sistemata", 10000) * (sum(non_sedute) + non_sistemate_fisse)
              + _peso(ist, "posto_vuoto", 10) * sum(vuoti)
              + _peso(ist, "divisione_blocco", 4) * sum(divisioni)
              + _peso(ist, "riallestimento", 2) * sum(cambi))
    if obiettivo == "completo":
        m.minimize(totale)
    elif obiettivo != "nessuno":
        raise ValueError(obiettivo)
    return mod


def estrai_piantina(ist: Istanza, mod: _Modello, piano: dict) -> tuple[list, list, set]:
    """Tavoli della piantina con la partizione dei blocchi per turno, e chi siede dove."""
    def V(x):
        return x if isinstance(x, int) else piano.get(x.name, 0)

    pia: Piantina = ist.piantina
    tavoli = []
    for t in pia.tavoli:
        tid = str(t["id"])
        tav = {"id": tid, "tipo": t["tipo"], "posti": int(t["posti"])}
        if t["tipo"] == "blocco":
            tav.update(moduli=int(t["moduli"]), separabile=bool(t.get("separabile")))
            part = {}
            for k, tu in enumerate(ist.turni):
                vars_ = mod.info_slot.get(f"t{tid}.k{k}")
                part[tu.nome] = ([[a, b] for (a, b), v in sorted(vars_.items()) if V(v)] if vars_ is not None
                                 else [[0, int(t["moduli"]) - 1]])
            tav["partizioni"] = part
        tavoli.append(tav)
    assegnazioni, sedute = [], set()
    for v in mod.voci:
        ch = next((c for (pid, c), av in mod.a.items() if pid == v.pr.id and V(av)), None)
        if ch is None:
            continue
        u, k = mod.unita[ch]
        tu = ist.turni[k]
        sedute.add(v.pr.id)
        assegnazioni.append({
            "id": v.pr.id, "nome": v.pr.nome, "coperti": v.pr.coperti,
            "orario_richiesto": min_a_hhmm(v.pr.orario_min), "orario_assegnato": min_a_hhmm(tu.inizio_min),
            "spostamento_min": 0, "fine": min_a_hhmm(tu.fine_min), "tavolo": u.tavolo,
            "quadrati": list(u.quadrati) if u.quadrati is not None else None, "gruppo": u.gruppo,
            "posti_tavolo": u.posti, "note": v.pr.note, "turno": tu.nome,
            "turno_richiesto": ist.turni[ist.turno_della(v.pr)].nome,
        })
    ordine = {str(t["id"]): n for n, t in enumerate(pia.tavoli)}
    assegnazioni.sort(key=lambda r: (r["orario_assegnato"], ordine[r["tavolo"]], (r["quadrati"] or [0])[0],
                                     r["gruppo"] or 0))
    return tavoli, assegnazioni, sedute


def componenti_piantina(ist: Istanza, tavoli: list, assegnazioni: list, non_sistemate: list) -> dict:
    """Componenti dell'obiettivo ricalcolate dalla soluzione (stesse del modello)."""
    pesi = {"non_sistemata": _peso(ist, "non_sistemata", 10000), "posto_vuoto": _peso(ist, "posto_vuoto", 10),
            "divisione_blocco": _peso(ist, "divisione_blocco", 4), "riallestimento": _peso(ist, "riallestimento", 2)}
    vuoti = posti_vuoti(assegnazioni, {str(t["id"]): int(t["posti"]) for t in ist.piantina.tavoli if t["tipo"] == "lungo"})
    nomi = [t.nome for t in ist.turni]
    div = sum(len(t["partizioni"][n]) - 1 for t in tavoli if t.get("partizioni") for n in nomi)
    camb = sum(1 for t in tavoli if t.get("partizioni")
               for a, b in zip(nomi, nomi[1:]) if t["partizioni"][a] != t["partizioni"][b])
    per_turno = {n: sum(r["coperti"] for r in assegnazioni if r["turno"] == n) for n in nomi}
    comp = {
        "non_sistemate": {"numero": len(non_sistemate), "costo": pesi["non_sistemata"] * len(non_sistemate)},
        "posti_vuoti": {"posti": vuoti, "costo": pesi["posto_vuoto"] * vuoti},
        "spostamenti": {"quarti_d_ora": 0, "costo": 0},
        "accostamenti": {"moduli_oltre_il_primo": 0, "costo": 0},
        "picco_cucina": {"coperti_oltre_soglia": 0, "soglia": 0, "costo": 0, "coperti_per_orario": per_turno,
                         "disattivato": "turni"},
        "divisioni_blocchi": {"numero": div, "costo": pesi["divisione_blocco"] * div},
        "riallestimenti": {"numero": camb, "costo": pesi["riallestimento"] * camb},
    }
    comp["totale"] = sum(v["costo"] for v in comp.values())
    return comp


def posti_vuoti(assegnazioni: list, lunghi: dict[str, int]) -> int:
    """Posti vuoti ai tavoli usati; il lungo conta i suoi posti meno tutti i coperti seduti nel turno."""
    vuoti = sum(r["posti_tavolo"] - r["coperti"] for r in assegnazioni if r["tavolo"] not in lunghi)
    usati: dict[tuple, int] = {}
    for r in assegnazioni:
        if r["tavolo"] in lunghi:
            usati[(r["tavolo"], r["turno"])] = usati.get((r["tavolo"], r["turno"]), 0) + r["coperti"]
    return vuoti + sum(lunghi[t] - c for (t, _), c in usati.items())


def impossibile_per_conteggio_piantina(ist: Istanza, accettate: list[_Voce], pr, st: int) -> bool:
    """Condizione SUFFICIENTE di impossibilità: nel turno, per qualche soglia c, le prenotazioni da almeno c coperti
    sono più delle unità da almeno c posti che possono esserci insieme (tavoli, gruppi del lungo, pezzi dei blocchi)."""
    k = ist.turno_da_passo(st)
    cop = [v.pr.coperti for v in accettate if ist.turno_da_passo(v.opzioni[0][1]) == k] + [pr.coperti]
    pia: Piantina = ist.piantina
    return any(sum(1 for x in cop if x >= c) > pia.max_unita(c) for c in set(cop))
