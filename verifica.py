"""Verificatore INDIPENDENTE della soluzione.

Non importa nulla del pacchetto `ristorante`: rilegge sala, prenotazioni e soluzione dai JSON e rifà i
controlli con geometria in centimetri e aritmetica dei minuti proprie (niente griglia del solver).
Copre la disposizione "fissa" e "variabile" (tavoli con esistenza [esiste_dal, esiste_al)), il registro
dell'accettazione in ordine di arrivo e la modalità a turni (turni della sala; ogni prenotazione occupa il tavolo per
tutto il suo turno, al più una per turno su ogni tavolo, turno finale = turno promesso, in "fissa" gli stessi tavoli in
tutti i turni). Con la sala vera (`--sala olimpo/piantina.html`) legge da sé il blocco `id="sala"` della piantina e
controlla tavoli, pezzi dei blocchi, tavolo lungo e turni (vedi `verifica_piantina`). Stampa PASS/FAIL per controllo con
i conteggi; exit code 0 se tutto PASS.

Limite dichiarato: il verificatore controlla che la soluzione sia AMMISSIBILE e coerente; non può dimostrare
che un rifiuto fosse inevitabile né che la piantina sia ottima.

Uso:
    python verifica.py --sala dati/sala_esempio.json --prenotazioni dati/sabato_pieno.json --soluzione out/soluzione.json
"""
from __future__ import annotations

import argparse
import json
import sys
from html.parser import HTMLParser
from dataclasses import dataclass, field
from datetime import datetime

M_TROPPO_GRANDE = "nessun tavolo componibile abbastanza grande"
M_SALA_PIENA = "sala piena nella fascia richiesta"
M_SALA_PIENA_ACC = "sala piena nella fascia richiesta, con le prenotazioni già accettate"
M_FUORI_ORARIO = "nessun orario ammesso entro la chiusura del servizio"
M_TEMPO = "spazio non trovato entro il tempo limite"
M_NESSUNA_SOL = "nessuna soluzione trovata entro il tempo limite"
M_PROPOSTA_RIFIUTATA = "proposta non accettata dal cliente"
M_TURNO_PIENO = "turno pieno, con le prenotazioni già accettate"
M_TURNI_PIENI = "tutti i turni pieni, con le prenotazioni già accettate"
ACCETTATE = ("accettata", "accettata su proposta")
LUNGO_DUE_GRUPPI = 8           # tavolo lungo: "un gruppo fino a 20 oppure due gruppi fino a 8"


class _BloccoSala(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.dentro, self.testo, self.n = False, [], 0

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "sala":
            self.dentro, self.n = True, self.n + 1

    def handle_endtag(self, tag):
        if tag == "script":
            self.dentro = False

    def handle_data(self, data):
        if self.dentro:
            self.testo.append(data)


def leggi_sala(percorso: str) -> dict:
    """La sala: JSON, oppure il blocco <script id="sala"> di una piantina .html (letto qui, senza il motore)."""
    with open(percorso, encoding="utf-8") as fh:
        testo = fh.read()
    if not percorso.lower().endswith((".html", ".htm")):
        return json.loads(testo)
    b = _BloccoSala()
    b.feed(testo)
    if b.n != 1:
        raise ValueError(f"{percorso}: atteso un blocco <script id=\"sala\">, trovati {b.n}")
    return json.loads("".join(b.testo))


def _e_piantina(sala: dict) -> bool:
    return "inventario" not in sala and isinstance(sala.get("tavoli"), list)


def _turni(sala: dict) -> list[tuple[str, int, int]]:
    return [(str(t["nome"]), _min(t["inizio"]), _min(t["fine"])) for t in sala.get("turni") or []]


def _turno_chiesto(p: dict, turni: list, a_parita: str) -> str | None:
    """Turno chiesto da una prenotazione in ingresso: quello esplicito, altrimenti il più vicino all'orario
    (distanza dall'inizio; a metà strada il turno prima, o quello dopo se `a_parita` = "dopo")."""
    if p.get("turno"):
        return str(p["turno"])
    if not turni:
        return None
    o = _min(p["orario"])
    dopo = a_parita == "dopo"
    k = min(range(len(turni)), key=lambda k: (abs(turni[k][1] - o), -k if dopo else k))
    return turni[k][0]


def _m_nessun_orario(n: int) -> str:
    return f"nessun orario libero entro {n} min"


def _politica(sol: dict, sala: dict) -> tuple[str, int | None]:
    """Politica dichiarata nella soluzione: ('mai'|'sempre'|'entro', N). Se manca (soluzioni precedenti alle
    proposte) vale 'mai'."""
    pol = sol.get("modalita", {}).get("cliente_accetta_proposta", "mai")
    if pol in ("mai", "sempre"):
        return pol, None
    parti = str(pol).split("_")
    if len(parti) == 3 and parti[0] == "entro" and parti[1].isdigit() and parti[2] == "min":
        return "entro", int(parti[1])
    return f"sconosciuta: {pol}", None


@dataclass
class Esito:
    nome: str
    ok: bool = True
    dettaglio: str = ""
    errori: list[str] = field(default_factory=list)

    def errore(self, msg: str) -> None:
        self.ok = False
        self.errori.append(msg)


# --------------------------------------------------------------------------- utilità

def _min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(minuti: int) -> str:
    return f"{minuti // 60:02d}:{minuti % 60:02d}"


def _durata(sala: dict, coperti: int) -> int:
    for riga in sala["durate"]:
        if riga.get("fino_a_coperti") is None or coperti <= riga["fino_a_coperti"]:
            return int(riga["minuti"])
    raise ValueError(f"nessuna durata per {coperti} coperti")


def _interseca(a: tuple, b: tuple) -> bool:
    """Intersezione con area positiva tra rettangoli (x0, y0, x1, y1): il contatto è ammesso."""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _rett(d: dict) -> tuple:
    return (d["x0"], d["y0"], d["x1"], d["y1"])


def _ingombro(t: dict, margine: int) -> tuple:
    return (t["x_cm"] - margine, t["y_cm"] - margine,
            t["x_cm"] + t["larghezza_cm"] + margine, t["y_cm"] + t["altezza_cm"] + margine)


def _entra_in_sala_vuota(lw: int, lh: int, sala: dict) -> bool:
    """Un rettangolo lw x lh sta da qualche parte nella sala vuota (solo ostacoli e corsie)?
    Se esiste una posizione valida ne esiste una con x in {0} ∪ {bordi destri dei fissi} e y in
    {0} ∪ {bordi inferiori dei fissi} (si spinge il rettangolo a sinistra e in alto): basta provare quelle."""
    W, H = sala["larghezza_cm"], sala["altezza_cm"]
    fissi = [_rett(o) for o in sala.get("ostacoli", [])] + [_rett(c) for c in sala.get("corsie", [])]
    for x in {0} | {f[2] for f in fissi}:
        for y in {0} | {f[3] for f in fissi}:
            r = (x, y, x + lw, y + lh)
            if r[2] <= W and r[3] <= H and not any(_interseca(r, f) for f in fissi):
                return True
    return False


def _capienza_massima_possibile(sala: dict) -> int:
    inv, m = sala["inventario"], sala["margine_sedie_cm"]
    mod = inv["moduli"]
    best = 0
    for k in range(1, min(mod["max_per_blocco"], mod["quantita"]) + 1):
        cap = mod.get("posti_per_modulo", 2) * k + mod.get("posti_testate", 2)
        for lw, lh in ((mod["lato_cm"] * k, mod["lato_cm"]), (mod["lato_cm"], mod["lato_cm"] * k)):
            if _entra_in_sala_vuota(lw + 2 * m, lh + 2 * m, sala):
                best = max(best, cap)
    t = inv.get("tondi", {})
    if t.get("quantita", 0) > 0 and _entra_in_sala_vuota(t["diametro_cm"] + 2 * m, t["diametro_cm"] + 2 * m, sala):
        best = max(best, t["capienza"])
    return best


# --------------------------------------------------------------------------- verifica

def verifica(sala: dict, prenotazioni: dict, sol: dict) -> list[Esito]:
    if _e_piantina(sala) and sol.get("modalita", {}).get("disposizione") == "libera":
        if "variante" in sol:
            return verifica_variante(sala, prenotazioni, sol)
        return verifica_libera(sala, prenotazioni, sol)
    if _e_piantina(sala):
        return verifica_piantina(sala, prenotazioni, sol)
    esiti: list[Esito] = []
    margine = sala["margine_sedie_cm"]
    W, H = sala["larghezza_cm"], sala["altezza_cm"]
    inv = sala["inventario"]
    mod = inv["moduli"]
    tondo = inv.get("tondi", {"quantita": 0})
    inizio, fine = _min(sala["servizio"]["inizio"]), _min(sala["servizio"]["fine"])
    passo = sala.get("passo_orari_min", 15)
    riapp = sala.get("riapparecchiatura_min", 0)
    ammessi = set(sala["spostamenti_ammessi_min"])
    tavoli = sol.get("tavoli", [])
    ass = sol.get("assegnazioni", [])
    nons = sol.get("non_sistemate", [])
    registro = sol.get("registro")
    modalita = sol.get("modalita", {})
    in_ordine = modalita.get("accettazione") == "ordine_di_arrivo" or registro is not None
    prop_max = int(sala.get("proposta_max_distanza_min", 120))
    su_proposta = {r["id"] for r in (registro or []) if r.get("esito") == "accettata su proposta"}
    input_pr = {p["id"]: p for p in prenotazioni["prenotazioni"]}
    turni = _turni(sala)
    a_turni = bool(turni) or bool(modalita.get("turni"))
    per_nome_turno = {t[0]: t for t in turni}
    t_parita = sala.get("turno_a_parita", "prima")
    per_id_tav = {t["id"]: t for t in tavoli}
    # esistenza in minuti: [dal, al). Default (soluzioni senza i campi): tutta la serata
    esist = {t["id"]: (_min(t.get("esiste_dal", sala["servizio"]["inizio"])),
                       _min(t["esiste_al"]) if "esiste_al" in t else fine + riapp) for t in tavoli}

    # 1. struttura
    e = Esito("struttura (id tavoli unici, riferimenti validi)")
    if len(per_id_tav) != len(tavoli):
        e.errore("id tavolo duplicati")
    for r in ass:
        if r.get("tavolo") not in per_id_tav:
            e.errore(f"{r.get('id')}: tavolo inesistente {r.get('tavolo')!r}")
    e.dettaglio = f"{len(tavoli)} tavoli, {len(ass)} assegnazioni, {len(nons)} non sistemate"
    esiti.append(e)

    if a_turni:
        e = Esito("turni (consecutivi, senza sovrapposizioni, dentro il servizio, gli stessi della sala)")
        dichiarati = [(str(t["nome"]), _min(t["inizio"]), _min(t["fine"])) for t in modalita.get("turni") or []]
        if dichiarati != turni:
            e.errore(f"turni dichiarati nella soluzione {dichiarati} diversi da quelli della sala {turni}")
        for i, (nome, a, b) in enumerate(turni):
            if not (inizio <= a < b <= fine):
                e.errore(f"turno {nome}: {_hhmm(a)}-{_hhmm(b)} fuori dal servizio")
            if (a - inizio) % passo or (b - inizio) % passo:
                e.errore(f"turno {nome}: fuori griglia di {passo} min")
            if i and a < turni[i - 1][2]:
                e.errore(f"turno {nome} comincia alle {_hhmm(a)}, prima della fine del turno {turni[i - 1][0]}")
        if len({t[0] for t in turni}) != len(turni):
            e.errore("nomi dei turni duplicati")
        e.dettaglio = ", ".join(f"{n} {_hhmm(a)}-{_hhmm(b)}" for n, a, b in turni)
        esiti.append(e)

    # 2. ogni prenotazione esattamente una volta, dati coerenti con l'input
    e = Esito("ogni prenotazione presente esattamente una volta")
    conteggio: dict[str, int] = {}
    for r in ass + nons:
        conteggio[r["id"]] = conteggio.get(r["id"], 0) + 1
    for pid, n in conteggio.items():
        if pid not in input_pr:
            e.errore(f"{pid}: non è tra le prenotazioni in ingresso")
        elif n != 1:
            e.errore(f"{pid}: compare {n} volte")
    for pid in input_pr:
        if pid not in conteggio:
            e.errore(f"{pid}: manca (né seduta né non sistemata)")
    for r in ass + nons:
        p = input_pr.get(r["id"])
        if p is None:
            continue
        if r["coperti"] != p["coperti"] or r["nome"] != p["nome"] or _min(r["orario_richiesto"]) != _min(p["orario"]):
            e.errore(f"{r['id']}: nome/coperti/orario richiesto diversi dall'ingresso")
    e.dettaglio = f"{len(input_pr)} in ingresso = {len(ass)} sedute + {len(nons)} non sistemate"
    esiti.append(e)

    # 3. forme e capienze dei tavoli coerenti con l'inventario
    e = Esito("forme e capienze dei tavoli")
    for t in tavoli:
        if t["tipo"] == "moduli":
            k = t["moduli"]
            if not (1 <= k <= mod["max_per_blocco"]):
                e.errore(f"{t['id']}: {k} moduli fuori da 1..{mod['max_per_blocco']}")
            lato = mod["lato_cm"]
            attese = {"orizzontale": (lato * k, lato), "verticale": (lato, lato * k)}.get(t["orientamento"])
            if attese is None:
                e.errore(f"{t['id']}: orientamento {t['orientamento']!r} non valido")
            elif (t["larghezza_cm"], t["altezza_cm"]) != attese:
                e.errore(f"{t['id']}: dimensioni {t['larghezza_cm']}x{t['altezza_cm']} invece di {attese}")
            cap = mod.get("posti_per_modulo", 2) * k + mod.get("posti_testate", 2)
            if t["capienza"] != cap:
                e.errore(f"{t['id']}: capienza {t['capienza']} invece di {cap}")
        elif t["tipo"] == "tondo":
            d = tondo.get("diametro_cm")
            if (t["larghezza_cm"], t["altezza_cm"]) != (d, d):
                e.errore(f"{t['id']}: tondo di {t['larghezza_cm']}x{t['altezza_cm']} invece di Ø{d}")
            if t["capienza"] != tondo.get("capienza"):
                e.errore(f"{t['id']}: capienza {t['capienza']} invece di {tondo.get('capienza')}")
        else:
            e.errore(f"{t['id']}: tipo {t['tipo']!r} sconosciuto")
    e.dettaglio = f"{len(tavoli)} tavoli controllati"
    esiti.append(e)

    # 4. esistenza dei tavoli
    e = Esito("esistenza dei tavoli (griglia, servizio, disposizione)")
    fissa = modalita.get("disposizione", "fissa") == "fissa"
    if a_turni and turni:
        inizi, fini = {t[1] for t in turni}, {t[2] for t in turni}
        for tid, (dal, al) in esist.items():
            if dal not in inizi or al not in fini or al <= dal:
                e.errore(f"{tid}: esistenza {_hhmm(dal)}-{_hhmm(al)} non fatta di turni interi")
            serviti = [t[0] for t in turni if dal <= t[1] and t[2] <= al]
            if "turni" in per_id_tav[tid] and per_id_tav[tid]["turni"] != serviti:
                e.errore(f"{tid}: turni dichiarati {per_id_tav[tid]['turni']} invece di {serviti}")
        montati = sum(1 for dal, _ in esist.values() if dal > turni[0][1])
        e.dettaglio = f"{len(esist)} tavoli, {montati} montati dopo il primo turno"
        esiti.append(e)
        e = Esito("disposizione fissa: stessi tavoli e stessi accostamenti in tutti i turni" if fissa else
                  "disposizione variabile: tavoli rifatti tra un turno e l'altro")
        if fissa:
            for tid, (dal, al) in esist.items():
                if (dal, al) != (turni[0][1], turni[-1][2]):
                    e.errore(f"{tid}: disposizione fissa ma il tavolo c'è solo {_hhmm(dal)}-{_hhmm(al)} "
                             f"(accostamento cambiato tra i turni)")
        e.dettaglio = (f"{len(esist)} tavoli presenti in tutti i {len(turni)} turni" if fissa else
                       f"{montati} tavoli montati a servizio iniziato")
    for tid, (dal, al) in ([] if a_turni else esist.items()):
        if not (inizio <= dal < al <= fine + riapp):
            e.errore(f"{tid}: esistenza {_hhmm(dal)}-{_hhmm(al)} fuori da {_hhmm(inizio)}-{_hhmm(fine + riapp)}")
        if (dal - inizio) % passo or (al - inizio) % passo:
            e.errore(f"{tid}: esistenza {_hhmm(dal)}-{_hhmm(al)} fuori griglia di {passo} min")
        if fissa and (dal, al) != (inizio, fine + riapp):
            e.errore(f"{tid}: disposizione fissa ma il tavolo esiste solo {_hhmm(dal)}-{_hhmm(al)}")
    if a_turni and turni:
        montati = sum(1 for dal, _ in esist.values() if dal > turni[0][1])
    else:
        montati = sum(1 for dal, _ in esist.values() if dal > inizio)
        e.dettaglio = f"{len(esist)} tavoli, {montati} montati a servizio iniziato"
    esiti.append(e)

    # 5. inventario in ogni istante
    e = Esito("inventario in ogni istante (moduli e tondi in uso)")
    istanti = sorted({dal for dal, _ in esist.values()})
    picco_m = picco_t = 0
    for tau in istanti:   # l'uso cambia solo quando un tavolo compare: basta controllare quegli istanti
        vivi = [t for t in tavoli if esist[t["id"]][0] <= tau < esist[t["id"]][1]]
        um = sum(t["moduli"] for t in vivi if t["tipo"] == "moduli")
        ut = sum(1 for t in vivi if t["tipo"] == "tondo")
        picco_m, picco_t = max(picco_m, um), max(picco_t, ut)
        if um > mod["quantita"]:
            e.errore(f"alle {_hhmm(tau)}: {um} moduli in uso > {mod['quantita']}")
        if ut > tondo.get("quantita", 0):
            e.errore(f"alle {_hhmm(tau)}: {ut} tondi in uso > {tondo.get('quantita', 0)}")
    e.dettaglio = (f"massimo in uso: moduli {picco_m}/{mod['quantita']}, tondi {picco_t}/{tondo.get('quantita', 0)} "
                   f"({len(istanti)} istanti controllati)")
    esiti.append(e)

    ingombri = {t["id"]: _ingombro(t, margine) for t in tavoli}

    # 6. ingombri dentro la sala
    e = Esito("ingombri (tavolo + sedie) dentro la sala")
    for tid, r in ingombri.items():
        if r[0] < 0 or r[1] < 0 or r[2] > W or r[3] > H:
            e.errore(f"{tid}: ingombro {r} esce dalla sala {W}x{H}")
    e.dettaglio = f"{len(ingombri)} ingombri"
    esiti.append(e)

    # 7-8. ingombri disgiunti da ostacoli e corsie (esistono sempre)
    for chiave, nome in (("ostacoli", "ingombri disgiunti dagli ostacoli"), ("corsie", "ingombri disgiunti dalle corsie")):
        e = Esito(nome)
        fissi = sala.get(chiave, [])
        for tid, r in ingombri.items():
            for f in fissi:
                if _interseca(r, _rett(f)):
                    e.errore(f"{tid}: ingombro {r} interseca {f.get('nome', '?')} {_rett(f)}")
        e.dettaglio = f"{len(ingombri)} ingombri x {len(fissi)} {chiave}"
        esiti.append(e)

    # 9. ingombri disgiunti tra loro nello spazio-tempo
    e = Esito("ingombri disgiunti tra loro nello spazio-tempo")
    ids = list(ingombri)
    coppie = stesso_spazio = 0
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            coppie += 1
            if _interseca(ingombri[ids[i]], ingombri[ids[j]]):
                stesso_spazio += 1
                (d1, a1), (d2, a2) = esist[ids[i]], esist[ids[j]]
                if not (a1 <= d2 or a2 <= d1):
                    e.errore(f"{ids[i]} ({_hhmm(d1)}-{_hhmm(a1)}) e {ids[j]} ({_hhmm(d2)}-{_hhmm(a2)}) "
                             f"occupano lo stesso spazio nello stesso momento")
    e.dettaglio = f"{coppie} coppie, {stesso_spazio} nello stesso spazio in momenti diversi"
    esiti.append(e)

    # 10. capienza
    e = Esito("capienza >= coperti")
    for r in ass:
        t = per_id_tav.get(r["tavolo"])
        if t is not None and t["capienza"] < r["coperti"]:
            e.errore(f"{r['id']}: {r['coperti']} coperti su {t['id']} da {t['capienza']}")
    e.dettaglio = f"{len(ass)} assegnazioni"
    esiti.append(e)

    if a_turni:
        esiti += _controlli_turni(ass, input_pr, su_proposta, turni, per_nome_turno, t_parita, esist)
    # 11. orari: spostamento ammesso, griglia, durata, servizio
    e = Esito("orari (spostamenti ammessi, durata, entro il servizio)")
    spostate = 0
    for r in ([] if a_turni else ass):
        rich, asg = _min(r["orario_richiesto"]), _min(r["orario_assegnato"])
        sp = asg - rich
        spostate += sp != 0
        if r["id"] in su_proposta:
            if sp in ammessi or abs(sp) > prop_max:
                e.errore(f"{r['id']}: accettata su proposta con spostamento {sp} min (atteso fuori da "
                         f"{sorted(ammessi)} ed entro {prop_max} min)")
        elif sp not in ammessi:
            e.errore(f"{r['id']}: spostamento {sp} min non ammesso {sorted(ammessi)}")
        if r.get("spostamento_min") != sp:
            e.errore(f"{r['id']}: spostamento_min {r.get('spostamento_min')} incoerente con gli orari ({sp})")
        if (asg - inizio) % passo:
            e.errore(f"{r['id']}: orario {r['orario_assegnato']} fuori griglia di {passo} min")
        if asg < inizio:
            e.errore(f"{r['id']}: inizia alle {r['orario_assegnato']}, prima dell'apertura")
        fine_attesa = asg + _durata(sala, r["coperti"])
        if _min(r["fine"]) != fine_attesa:
            e.errore(f"{r['id']}: fine {r['fine']} invece di {_hhmm(fine_attesa)}")
        if fine_attesa > fine:
            e.errore(f"{r['id']}: finisce alle {_hhmm(fine_attesa)}, dopo la chiusura")
    e.dettaglio = f"{len(ass)} assegnazioni, {spostate} spostate, {len(su_proposta)} su proposta"
    esiti.append(e)

    if a_turni:
        esiti.pop()                        # il controllo degli orari è sostituito da quello dei turni
    # 12. nessuna sovrapposizione temporale sullo stesso tavolo (con riapparecchiatura)
    e = Esito("nessuna sovrapposizione sullo stesso tavolo (con riapparecchiatura)")
    per_tav: dict[str, list] = {}
    for r in ([] if a_turni else ass):
        a = _min(r["orario_assegnato"])
        per_tav.setdefault(r["tavolo"], []).append((a, a + _durata(sala, r["coperti"]), r["id"]))
    confronti = 0
    for tid, lst in per_tav.items():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                confronti += 1
                a0, a1, ia = lst[i]
                b0, b1, ib = lst[j]
                if not (a1 + riapp <= b0 or b1 + riapp <= a0):
                    e.errore(f"{tid}: {ia} ({_hhmm(a0)}-{_hhmm(a1)}) e {ib} ({_hhmm(b0)}-{_hhmm(b1)}) "
                             f"si sovrappongono (riapparecchiatura {riapp} min)")
    e.dettaglio = f"{confronti} coppie sullo stesso tavolo"
    esiti.append(e)

    if a_turni:
        esiti.pop()
    # 13. prenotazioni dentro l'esistenza del loro tavolo (riapparecchiatura compresa)
    e = Esito("prenotazioni dentro l'esistenza del loro tavolo")
    for r in ([] if a_turni else ass):
        if r["tavolo"] not in esist:
            continue
        dal, al = esist[r["tavolo"]]
        a = _min(r["orario_assegnato"])
        b = a + _durata(sala, r["coperti"]) + riapp
        if a < dal or b > al:
            e.errore(f"{r['id']} ({_hhmm(a)}-{_hhmm(b)} con riapparecchiatura) fuori dall'esistenza di "
                     f"{r['tavolo']} ({_hhmm(dal)}-{_hhmm(al)})")
    e.dettaglio = f"{len(ass)} assegnazioni"
    esiti.append(e)

    if a_turni:
        esiti.pop()
    # 14. motivi delle non sistemate
    e = Esito("motivi delle non sistemate coerenti")
    capmax = _capienza_massima_possibile(sala)
    n_tempo = 0
    for r in nons:
        mot = r.get("motivo", "")
        if mot == M_NESSUNA_SOL and sol.get("solver", {}).get("stato") == "UNKNOWN":
            continue
        p = input_pr.get(r["id"], {})
        orario = _min(p.get("orario", r["orario_richiesto"]))
        d = _durata(sala, r["coperti"])
        ha_orari = any(inizio <= orario + s and orario + s + d <= fine for s in ammessi)
        if r["coperti"] > capmax:
            attesi = {M_TROPPO_GRANDE}
        elif a_turni:
            pol, _ = _politica(sol, sala)
            if not in_ordine:
                attesi = {M_SALA_PIENA}
            elif pol == "mai":
                attesi = {M_TURNO_PIENO, M_TEMPO}
            else:
                attesi = {M_TURNI_PIENI, M_TEMPO} | ({M_PROPOSTA_RIFIUTATA} if pol == "entro" else set())
        elif not ha_orari and not (in_ordine and _politica(sol, sala)[0] != "mai"):
            attesi = {M_FUORI_ORARIO}
        elif in_ordine:
            pol, _ = _politica(sol, sala)
            if pol == "mai":
                attesi = {M_SALA_PIENA_ACC, M_TEMPO}   # il verificatore non può decidere quale dei due
            else:
                attesi = {_m_nessun_orario(prop_max), M_TEMPO} | ({M_PROPOSTA_RIFIUTATA} if pol == "entro" else set())
        else:
            attesi = {M_SALA_PIENA}
        n_tempo += mot == M_TEMPO
        if mot not in attesi:
            e.errore(f"{r['id']}: motivo {mot!r}, atteso uno tra {sorted(attesi)} (capienza massima possibile {capmax})")
    e.dettaglio = f"{len(nons)} non sistemate ({n_tempo} per tempo scaduto), capienza massima possibile {capmax}"
    esiti.append(e)

    # 15. componenti dell'obiettivo ricalcolate
    e = Esito("componenti dell'obiettivo ricalcolate")
    pesi = sala["pesi"]
    soglia = sala.get("picco_cucina_soglia_coperti", 30)
    vuoti = sum(per_id_tav[r["tavolo"]]["capienza"] - r["coperti"] for r in ass if r["tavolo"] in per_id_tav)
    c_sp = 0 if a_turni else sum(
        round(pesi["spostamento_per_quarto"] * abs(_min(r["orario_assegnato"]) - _min(r["orario_richiesto"])) / 15)
        for r in ass)
    extra = sum(t["moduli"] - 1 for t in tavoli if t["tipo"] == "moduli")
    partenze: dict[int, int] = {}
    for r in ass:
        partenze[_min(r["orario_assegnato"])] = partenze.get(_min(r["orario_assegnato"]), 0) + r["coperti"]
    oltre = 0 if a_turni else sum(max(0, v - soglia) for v in partenze.values())   # a turni: picco disattivato
    atteso = {
        "non_sistemate": pesi["non_sistemata"] * len(nons),
        "posti_vuoti": pesi["posto_vuoto"] * vuoti,
        "spostamenti": c_sp,
        "accostamenti": pesi["accostamento_per_modulo"] * extra,
        "picco_cucina": pesi["picco_cucina_per_coperto"] * oltre,
        "riallestimenti": pesi.get("riallestimento", 20) * montati,
    }
    totale = sum(atteso.values())
    comp = sol.get("obiettivo_componenti", {})
    for k, v in atteso.items():
        riportato = comp.get(k, {}).get("costo", 0 if k == "riallestimenti" else None)
        if riportato != v:
            e.errore(f"{k}: riportato {riportato}, ricalcolato {v}")
    if comp.get("totale") != totale:
        e.errore(f"totale: riportato {comp.get('totale')}, ricalcolato {totale}")
    ob = sol.get("solver", {}).get("obiettivo")
    if ob is not None and ob != totale:
        e.errore(f"obiettivo del solver {ob} diverso dal totale ricalcolato {totale}")
    e.dettaglio = f"totale ricalcolato {totale} (" + ", ".join(f"{k} {v}" for k, v in atteso.items()) + ")"
    esiti.append(e)

    esiti += _controlli_registro(sol, sala, registro, in_ordine, input_pr, ass, nons, a_turni, turni, t_parita,
                                 ammessi, prop_max, inizio, passo, fine)
    return esiti


def _controlli_registro(sol, sala, registro, in_ordine, input_pr, ass, nons, a_turni, turni, t_parita, ammessi,
                        prop_max, inizio, passo, fine) -> list[Esito]:
    """Registro dell'accettazione in ordine di arrivo: ordine, orari/turni promessi, coerenza con sedute e rifiuti,
    proposte e politica del cliente."""
    esiti: list[Esito] = []
    # 16-18. registro dell'accettazione in ordine di arrivo
    if in_ordine:
        reg = registro or []
        e = Esito("registro in ordine di prenotazione")
        ids_reg = [r["id"] for r in reg]
        if sorted(ids_reg) != sorted(input_pr) or len(set(ids_reg)) != len(ids_reg):
            e.errore("il registro non contiene ogni prenotazione esattamente una volta")
        ricevute = []
        for r in reg:
            p = input_pr.get(r["id"], {})
            if "prenotata_il" not in p:
                e.errore(f"{r['id']}: prenotata_il assente nell'ingresso")
                continue
            ricevuta = datetime.fromisoformat(p["prenotata_il"])
            if datetime.fromisoformat(r["prenotata_il"]) != ricevuta:
                e.errore(f"{r['id']}: prenotata_il {r['prenotata_il']} diversa dall'ingresso {p['prenotata_il']}")
            ricevute.append((ricevuta, r["id"]))
        for (t1, i1), (t2, i2) in zip(ricevute, ricevute[1:]):
            if t2 < t1:
                e.errore(f"{i2} (ricevuta {t2:%d/%m %H:%M}) è registrata dopo {i1} (ricevuta {t1:%d/%m %H:%M})")
        e.dettaglio = f"{len(reg)} voci"
        esiti.append(e)

        e = Esito("orari finali uguali a quelli promessi nel registro")
        per_id_ass = {r["id"]: r for r in ass}
        n_prom = 0
        for r in reg:
            if r.get("esito") not in ACCETTATE:
                continue
            n_prom += 1
            a = per_id_ass.get(r["id"])
            if a is None:
                e.errore(f"{r['id']}: accettata nel registro ma non seduta nella piantina")
            elif a["orario_assegnato"] != r.get("orario_promesso"):
                e.errore(f"{r['id']}: promessa alle {r.get('orario_promesso')}, seduta alle {a['orario_assegnato']}")
            elif a_turni and a.get("turno") != r.get("turno_promesso"):
                e.errore(f"{r['id']}: promessa nel turno {r.get('turno_promesso')}, seduta nel turno {a.get('turno')}")
        e.dettaglio = f"{n_prom} orari promessi"
        if a_turni:
            e.nome = "turno finale = turno promesso (e orari uguali a quelli promessi)"
            e.dettaglio = f"{n_prom} turni promessi"
        esiti.append(e)

        e = Esito("registro coerente con sedute e rifiuti")
        per_id_ns = {r["id"]: r for r in nons}
        for r in reg:
            if r.get("esito") in ACCETTATE:
                if r["id"] in per_id_ns:
                    e.errore(f"{r['id']}: accettata nel registro ma tra le non sistemate")
                if r.get("orario_promesso") is None:
                    e.errore(f"{r['id']}: accettata senza orario promesso")
                elif r.get("esito") == "accettata" and a_turni:
                    chiesto = _turno_chiesto(input_pr.get(r["id"], {}), turni, t_parita)
                    if r.get("turno_promesso") != chiesto or r.get("turno_richiesto") != chiesto:
                        e.errore(f"{r['id']}: accettata nel turno {r.get('turno_promesso')}, ma il turno chiesto è {chiesto}")
                elif r.get("esito") == "accettata" and \
                        _min(r["orario_promesso"]) - _min(r["orario_richiesto"]) not in ammessi:
                    e.errore(f"{r['id']}: orario promesso {r.get('orario_promesso')} non tra gli spostamenti ammessi")
                elif r.get("esito") == "accettata su proposta" and r.get("orario_promesso") != r.get("proposta_principale"):
                    e.errore(f"{r['id']}: accettata su proposta alle {r.get('orario_promesso')}, ma la proposta "
                             f"principale era {r.get('proposta_principale')}")
            elif r.get("esito") == "rifiutata":
                if r["id"] in per_id_ass:
                    e.errore(f"{r['id']}: rifiutata nel registro ma seduta nella piantina")
                elif r["id"] not in per_id_ns or per_id_ns[r["id"]]["motivo"] != r.get("motivo") or not r.get("motivo"):
                    e.errore(f"{r['id']}: rifiutata ma motivo assente o diverso dalle non sistemate")
            else:
                e.errore(f"{r['id']}: esito {r.get('esito')!r} non valido")
        e.dettaglio = (f"{sum(r.get('esito') == 'accettata' for r in reg)} accettate, "
                       f"{sum(r.get('esito') == 'accettata su proposta' for r in reg)} su proposta, "
                       f"{sum(r.get('esito') == 'rifiutata' for r in reg)} rifiutate")
        esiti.append(e)

        # 19. proposte: entro la distanza massima, fuori dagli spostamenti ammessi, dentro il servizio
        e = Esito("proposte entro la distanza massima e fuori dagli spostamenti ammessi")
        n_prop = 0
        if a_turni:
            e = _proposte_turni(reg, input_pr, turni, t_parita, sala.get("proposta_a_parita", "prima"))
            esiti.append(e)
        for r in ([] if a_turni else reg):
            rich = _min(r["orario_richiesto"])
            d = _durata(sala, r["coperti"])
            prima, dopo = r.get("proposta_prima"), r.get("proposta_dopo")
            for nome, val, segno in (("prima", prima, -1), ("dopo", dopo, 1)):
                if val is None:
                    continue
                n_prop += 1
                sp = _min(val) - rich
                if sp * segno <= 0:
                    e.errore(f"{r['id']}: proposta {nome} {val} non è {nome} dell'orario richiesto {r['orario_richiesto']}")
                if abs(sp) > prop_max:
                    e.errore(f"{r['id']}: proposta {nome} {val} a {abs(sp)} min, oltre il massimo di {prop_max}")
                if sp in ammessi:
                    e.errore(f"{r['id']}: proposta {nome} {val} è uno spostamento già ammesso")
                if (_min(val) - inizio) % passo or _min(val) < inizio or _min(val) + d > fine:
                    e.errore(f"{r['id']}: proposta {nome} {val} fuori griglia o fuori dal servizio")
            if prima or dopo:
                cand = [v for v in (prima, dopo) if v]
                attesa = min(cand, key=lambda v: (abs(_min(v) - rich),
                                                  (_min(v) > rich) != (sala.get("proposta_a_parita", "prima") == "dopo")))
                if r.get("proposta_principale") != attesa:
                    e.errore(f"{r['id']}: proposta principale {r.get('proposta_principale')}, attesa {attesa} (la più vicina)")
            elif r.get("proposta_principale"):
                e.errore(f"{r['id']}: proposta principale senza proposte")
        if not a_turni:
            e.dettaglio = f"{n_prop} proposte, massimo {prop_max} min"
            esiti.append(e)

        # 20. esiti coerenti con la politica del cliente
        pol, entro = _politica(sol, sala)
        e = Esito(f"esiti coerenti con la politica del cliente ({sol.get('modalita', {}).get('cliente_accetta_proposta', pol)})")
        if pol.startswith("sconosciuta"):
            e.errore(f"politica {pol}")
        for r in reg:
            ha_prop = bool(r.get("proposta_prima") or r.get("proposta_dopo"))
            esito, mot = r.get("esito"), r.get("motivo")
            if pol == "mai":
                if esito == "accettata su proposta" or ha_prop or mot in (M_PROPOSTA_RIFIUTATA,) or \
                        (mot or "").startswith("nessun orario libero"):
                    e.errore(f"{r['id']}: proposte o esiti da proposta con la politica 'mai'")
            elif esito == "rifiutata" and ha_prop:
                dist = abs(_min(r["proposta_principale"]) - _min(r["orario_richiesto"])) if r.get("proposta_principale") else None
                if pol == "sempre" or mot != M_PROPOSTA_RIFIUTATA or dist is None or dist <= entro:
                    e.errore(f"{r['id']}: rifiutata pur avendo una proposta (a {dist} min) accettabile dalla politica")
            elif esito == "rifiutata" and mot == M_PROPOSTA_RIFIUTATA:
                e.errore(f"{r['id']}: 'proposta non accettata' senza proposte")
            elif esito == "accettata su proposta" and pol == "entro":
                dist = abs(_min(r["orario_promesso"]) - _min(r["orario_richiesto"]))
                if dist > entro:
                    e.errore(f"{r['id']}: accettata su proposta a {dist} min, oltre la tolleranza di {entro} min")
            if pol != "mai" and esito == "rifiutata" and mot == M_SALA_PIENA_ACC:
                e.errore(f"{r['id']}: rifiutata senza cercare proposte, ma la politica le prevede")
        e.dettaglio = (f"{sum(r.get('esito') == 'accettata su proposta' for r in reg)} accettate su proposta, "
                       f"{sum(r.get('motivo') == M_PROPOSTA_RIFIUTATA for r in reg)} proposte rifiutate dal cliente")
        esiti.append(e)
    return esiti


def _posti_pezzo(t: dict, a: int, b: int, separato: int) -> int:
    k = int(t["moduli"])
    if (a, b) == (0, k - 1):
        return int(t["posti"])
    j = b - a + 1
    if int(t["posti"]) == 2 * k:                   # blocco senza sedie in testa: 2 per quadrato, anche da solo
        return 2 * j
    return 2 * j + 2 if j >= 2 else separato


def verifica_piantina(dati: dict, prenotazioni: dict, sol: dict) -> list[Esito]:
    """Sala vera dalla piantina: tavoli fermi; per turno, ogni prenotazione su un tavolo o su un pezzo contiguo di un
    blocco; il lungo con un gruppo fino ai suoi posti o due gruppi fino a 8; mai due prenotazioni sullo stesso quadrato
    nello stesso turno; turni e registro come nella modalità a turni."""
    esiti: list[Esito] = []
    modalita = sol.get("modalita", {})
    ass, nons, registro = sol.get("assegnazioni", []), sol.get("non_sistemate", []), sol.get("registro")
    in_ordine = modalita.get("accettazione") == "ordine_di_arrivo" or registro is not None
    input_pr = {p["id"]: p for p in prenotazioni["prenotazioni"]}
    su_proposta = {r["id"] for r in (registro or []) if r.get("esito") == "accettata su proposta"}
    piantina = {str(t["id"]): t for t in dati["tavoli"]}
    separato = int(dati.get("posti_quadrato_separato", 4))
    turni = [(str(t["nome"]), _min(t["inizio"]), _min(t["fine"])) for t in modalita.get("turni") or []]
    per_nome = {t[0]: t for t in turni}
    t_parita = modalita.get("turno_a_parita", "prima")

    e = Esito("turni (quelli della piantina, consecutivi)")
    inizi = [_min(x) for x in dati.get("turni") or []]
    if [t[1] for t in turni] != inizi:
        e.errore(f"inizi dei turni dichiarati {[_hhmm(t[1]) for t in turni]} diversi dalla piantina {dati.get('turni')}")
    for (n1, a1, b1), (n2, a2, b2) in zip(turni, turni[1:]):
        if b1 != a2:
            e.errore(f"il turno {n1} finisce alle {_hhmm(b1)}, il {n2} comincia alle {_hhmm(a2)}")
    for n, a, b in turni:
        if b <= a:
            e.errore(f"turno {n}: fine {_hhmm(b)} non dopo l'inizio {_hhmm(a)}")
    e.dettaglio = ", ".join(f"{n} {_hhmm(a)}-{_hhmm(b)}" for n, a, b in turni)
    esiti.append(e)

    e = Esito("tavoli uguali a quelli della piantina")
    sol_tav = {str(t["id"]): t for t in sol.get("tavoli", [])}
    if set(sol_tav) != set(piantina):
        e.errore(f"tavoli diversi: in più {sorted(set(sol_tav) - set(piantina))}, mancano {sorted(set(piantina) - set(sol_tav))}")
    for tid, t in sol_tav.items():
        q = piantina.get(tid)
        if q is not None and (t.get("tipo"), t.get("posti")) != (q["tipo"], q["posti"]):
            e.errore(f"{tid}: {t.get('tipo')} da {t.get('posti')} invece di {q['tipo']} da {q['posti']}")
    for r in ass:
        if str(r.get("tavolo")) not in piantina:
            e.errore(f"{r['id']}: tavolo {r.get('tavolo')!r} inesistente")
    e.dettaglio = f"{len(piantina)} tavoli, {sum(int(t['posti']) for t in piantina.values())} posti per turno"
    esiti.append(e)

    e = Esito("ogni prenotazione presente esattamente una volta")
    conteggio: dict[str, int] = {}
    for r in ass + nons:
        conteggio[r["id"]] = conteggio.get(r["id"], 0) + 1
    for pid, n in conteggio.items():
        if pid not in input_pr:
            e.errore(f"{pid}: non è tra le prenotazioni in ingresso")
        elif n != 1:
            e.errore(f"{pid}: compare {n} volte")
    for pid, p in input_pr.items():
        if pid not in conteggio:
            e.errore(f"{pid}: manca (né seduta né non sistemata)")
    for r in ass + nons:
        p = input_pr.get(r["id"])
        if p is not None and (r["coperti"] != p["coperti"] or r["nome"] != p["nome"]
                              or _min(r["orario_richiesto"]) != _min(p["orario"])):
            e.errore(f"{r['id']}: nome/coperti/orario richiesto diversi dall'ingresso")
    e.dettaglio = f"{len(input_pr)} in ingresso = {len(ass)} sedute + {len(nons)} non sistemate"
    esiti.append(e)

    e = Esito("partizioni dei blocchi contigue, per turno")
    n_div = 0
    for tid, q in piantina.items():
        if q["tipo"] != "blocco":
            continue
        k = int(q["moduli"])
        part = (sol_tav.get(tid) or {}).get("partizioni") or {}
        for n, _, _ in turni:
            pezzi = sorted(tuple(x) for x in part.get(n, [[0, k - 1]]))
            atteso = 0
            for a, b in pezzi:
                if a != atteso or b < a:
                    e.errore(f"{tid} nel turno {n}: pezzi {pezzi} non contigui o non coprono i {k} quadrati")
                    break
                atteso = b + 1
            if atteso != k:
                e.errore(f"{tid} nel turno {n}: pezzi {pezzi} non coprono i {k} quadrati")
            if len(pezzi) > 1 and not q.get("separabile"):
                e.errore(f"{tid}: diviso nel turno {n} ma non è separabile")
            n_div += len(pezzi) - 1
    e.dettaglio = f"{n_div} divisioni in tutto"
    esiti.append(e)

    e = Esito("posti: ogni prenotazione su un tavolo o pezzo del suo turno, coperti <= posti")
    occupati: dict[tuple, str] = {}            # (tavolo, turno, quadrato | "t" | gruppo) -> prenotazione
    lungo: dict[tuple, list] = {}
    vuoti = 0
    for r in ass:
        q = piantina.get(str(r.get("tavolo")))
        if q is None or r.get("turno") not in per_nome:
            continue
        tid, n = str(q["id"]), r["turno"]
        if q["tipo"] == "blocco":
            qq = r.get("quadrati")
            k = int(q["moduli"])
            pezzi = [tuple(x) for x in ((sol_tav.get(tid) or {}).get("partizioni") or {}).get(n, [[0, k - 1]])]
            if not qq or tuple(qq) not in pezzi:
                e.errore(f"{r['id']}: quadrati {qq} di {tid} non sono un pezzo della partizione del turno {n} {pezzi}")
                continue
            posti = _posti_pezzo(q, qq[0], qq[1], separato)
            chiavi = [(tid, n, x) for x in range(qq[0], qq[1] + 1)]
        elif q["tipo"] == "lungo":
            g = r.get("gruppo")
            if g not in (1, 2):
                e.errore(f"{r['id']}: sul lungo {tid} senza gruppo 1 o 2")
                continue
            posti = int(q["posti"]) if g == 1 else min(LUNGO_DUE_GRUPPI, int(q["posti"]))
            chiavi = [(tid, n, f"g{g}")]
            lungo.setdefault((tid, n), []).append(r)
        else:
            if r.get("quadrati") or r.get("gruppo"):
                e.errore(f"{r['id']}: {tid} è un tavolo semplice ma ha quadrati/gruppo")
            posti = int(q["posti"])
            chiavi = [(tid, n, "t")]
        if r.get("posti_tavolo") != posti:
            e.errore(f"{r['id']}: posti_tavolo {r.get('posti_tavolo')} invece di {posti}")
        if r["coperti"] > posti:
            e.errore(f"{r['id']}: {r['coperti']} coperti su {posti} posti ({tid})")
        vuoti += posti - r["coperti"] if q["tipo"] != "lungo" else 0
        for c in chiavi:
            if c in occupati:
                e.errore(f"{tid} nel turno {n}: {occupati[c]} e {r['id']} sullo stesso posto ({c[2]})")
            occupati[c] = r["id"]
    e.dettaglio = f"{len(ass)} assegnazioni"
    esiti.append(e)

    e = Esito("tavolo lungo: un gruppo fino ai suoi posti, oppure due gruppi fino a 8")
    for (tid, n), lst in lungo.items():
        vuoti += int(piantina[tid]["posti"]) - sum(r["coperti"] for r in lst)    # il lungo: posti meno tutti i seduti
        if any(r.get("gruppo") == 2 for r in lst) and not any(r.get("gruppo") == 1 for r in lst):
            e.errore(f"{tid} nel turno {n}: c'è il secondo gruppo senza il primo")
        if len(lst) > 2:
            e.errore(f"{tid} nel turno {n}: {len(lst)} gruppi")
        if len(lst) == 2 and any(r["coperti"] > LUNGO_DUE_GRUPPI for r in lst):
            e.errore(f"{tid} nel turno {n}: due gruppi ma uno supera {LUNGO_DUE_GRUPPI} ({[r['coperti'] for r in lst]})")
    e.dettaglio = " · ".join(f"{n}: " + " + ".join(str(r["coperti"]) for r in lst) for (_, n), lst in sorted(lungo.items())) or "non usato"
    esiti.append(e)

    tutto = {tid: (turni[0][1], turni[-1][2]) for tid in piantina} if turni else {}
    esiti.append(_controlli_turni(ass, input_pr, su_proposta, turni, per_nome, t_parita, tutto)[0])

    e = Esito("motivi delle non sistemate coerenti")
    capmax = max([int(t["posti"]) for t in piantina.values()] + [0])
    pol, _ = _politica(sol, dati)
    for r in nons:
        mot = r.get("motivo", "")
        if r["coperti"] > capmax:
            attesi = {M_TROPPO_GRANDE}
        elif not in_ordine:
            attesi = {M_SALA_PIENA}
        elif pol == "mai":
            attesi = {M_TURNO_PIENO, M_TEMPO}
        else:
            attesi = {M_TURNI_PIENI, M_TEMPO} | ({M_PROPOSTA_RIFIUTATA} if pol == "entro" else set())
        if mot not in attesi:
            e.errore(f"{r['id']}: motivo {mot!r}, atteso uno tra {sorted(attesi)}")
    e.dettaglio = f"{len(nons)} non sistemate, capienza massima {capmax}"
    esiti.append(e)

    e = Esito("componenti dell'obiettivo ricalcolate (posti vuoti, divisioni, cambi di partizione)")
    comp = sol.get("obiettivo_componenti", {})
    nomi = [t[0] for t in turni]
    cambi = sum(1 for t in sol.get("tavoli", []) if t.get("partizioni")
                for a, b in zip(nomi, nomi[1:])
                if sorted(map(tuple, t["partizioni"].get(a, []))) != sorted(map(tuple, t["partizioni"].get(b, []))))
    for chiave, campo, valore in (("non_sistemate", "numero", len(nons)), ("posti_vuoti", "posti", vuoti),
                                  ("divisioni_blocchi", "numero", n_div), ("riallestimenti", "numero", cambi)):
        if comp.get(chiave, {}).get(campo) != valore:
            e.errore(f"{chiave}: riportato {comp.get(chiave, {}).get(campo)}, ricalcolato {valore}")
    totale = sum(v.get("costo", 0) for k, v in comp.items() if isinstance(v, dict))
    if comp.get("totale") != totale:
        e.errore(f"totale {comp.get('totale')} diverso dalla somma dei costi {totale}")
    ob = sol.get("solver", {}).get("obiettivo")
    if ob is not None and sol.get("solver", {}).get("origine", "solver") == "solver" and ob != comp.get("totale"):
        e.errore(f"obiettivo del solver {ob} diverso dal totale {comp.get('totale')}")
    e.dettaglio = f"posti vuoti {vuoti}, divisioni {n_div}, cambi di partizione {cambi}, totale {comp.get('totale')}"
    esiti.append(e)

    esiti += _controlli_registro(sol, dati, registro, in_ordine, input_pr, ass, nons, True, turni, t_parita,
                                 set(), 0, 0, 1, 24 * 60)
    return esiti


def _controlli_turni(ass, input_pr, su_proposta, turni, per_nome, t_parita, esist) -> list[Esito]:
    """Ogni prenotazione è in un turno (quello chiesto, o l'altro se accettata su proposta), con orario e fine del
    turno; su ogni tavolo al più una prenotazione per turno; il turno sta dentro l'esistenza del tavolo."""
    e1 = Esito("turni delle prenotazioni (turno chiesto, orari del turno)")
    per_turno: dict[str, list] = {}
    for r in ass:
        t = per_nome.get(r.get("turno"))
        if t is None:
            e1.errore(f"{r['id']}: turno {r.get('turno')!r} non definito")
            continue
        per_turno.setdefault(t[0], []).append(r)
        if (_min(r["orario_assegnato"]), _min(r["fine"])) != (t[1], t[2]):
            e1.errore(f"{r['id']}: {r['orario_assegnato']}-{r['fine']} invece del turno {t[0]} {_hhmm(t[1])}-{_hhmm(t[2])}")
        if r.get("spostamento_min") != 0:
            e1.errore(f"{r['id']}: spostamento_min {r.get('spostamento_min')} (a turni deve essere 0)")
        chiesto = _turno_chiesto(input_pr.get(r["id"], {}), turni, t_parita)
        if r.get("turno_richiesto") != chiesto:
            e1.errore(f"{r['id']}: turno richiesto {r.get('turno_richiesto')}, ma per l'orario {r['orario_richiesto']} "
                      f"è {chiesto}")
        if r["id"] in su_proposta:
            if t[0] == chiesto:
                e1.errore(f"{r['id']}: accettata su proposta ma nel turno chiesto {chiesto}")
        elif t[0] != chiesto:
            e1.errore(f"{r['id']}: seduta nel turno {t[0]} invece di quello chiesto {chiesto}")
    e1.dettaglio = " · ".join(f"{n}: {len(per_turno.get(n, []))} prenotazioni, "
                              f"{sum(r['coperti'] for r in per_turno.get(n, []))} coperti" for n, _, _ in turni)
    e2 = Esito("al più una prenotazione per turno su ogni tavolo")
    visti: dict[tuple, str] = {}
    for r in ass:
        chiave = (r["tavolo"], r.get("turno"))
        if chiave in visti:
            e2.errore(f"{r['tavolo']}: {visti[chiave]} e {r['id']} nello stesso turno {r.get('turno')}")
        visti[chiave] = r["id"]
    e2.dettaglio = f"{len(ass)} assegnazioni su {len({r['tavolo'] for r in ass})} tavoli"
    e3 = Esito("prenotazioni dentro l'esistenza del loro tavolo (turno intero)")
    for r in ass:
        t = per_nome.get(r.get("turno"))
        if t is None or r["tavolo"] not in esist:
            continue
        dal, al = esist[r["tavolo"]]
        if t[1] < dal or t[2] > al:
            e3.errore(f"{r['id']} (turno {t[0]}) fuori dall'esistenza di {r['tavolo']} ({_hhmm(dal)}-{_hhmm(al)})")
    e3.dettaglio = f"{len(ass)} assegnazioni"
    return [e1, e2, e3]


def _proposte_turni(reg, input_pr, turni, t_parita, p_parita) -> Esito:
    """Le proposte sono inizi di altri turni (prima / dopo il turno chiesto); la principale è la più vicina
    all'orario chiesto."""
    e = Esito("proposte: altri turni, la principale è la più vicina all'orario chiesto")
    inizi = {t[1]: i for i, t in enumerate(turni)}
    n_prop = 0
    for r in reg:
        chiesto = _turno_chiesto(input_pr.get(r["id"], {}), turni, t_parita)
        kc = next((i for i, t in enumerate(turni) if t[0] == chiesto), None)
        rich = _min(r["orario_richiesto"])
        cand = []
        for nome, segno in (("proposta_prima", -1), ("proposta_dopo", 1)):
            val = r.get(nome)
            if val is None:
                continue
            n_prop += 1
            k = inizi.get(_min(val))
            if k is None:
                e.errore(f"{r['id']}: {nome} {val} non è l'inizio di un turno")
            elif kc is None or (k - kc) * segno <= 0:
                e.errore(f"{r['id']}: {nome} {val} non è un turno {'prima' if segno < 0 else 'dopo'} del turno chiesto {chiesto}")
            elif r.get("turno_proposto") is not None and r.get("proposta_principale") == val \
                    and r["turno_proposto"] != turni[k][0]:
                e.errore(f"{r['id']}: turno proposto {r['turno_proposto']} diverso da {turni[k][0]} ({val})")
            cand.append(val)
        if cand:
            attesa = min(cand, key=lambda v: (abs(_min(v) - rich), (_min(v) > rich) != (p_parita == "dopo")))
            if r.get("proposta_principale") != attesa:
                e.errore(f"{r['id']}: proposta principale {r.get('proposta_principale')}, attesa {attesa} (la più vicina)")
        elif r.get("proposta_principale"):
            e.errore(f"{r['id']}: proposta principale senza proposte")
    e.dettaglio = f"{n_prop} proposte di turno"
    return e


def _rifiuti_inevitabili_turni(sala: dict, prenotazioni: dict, sol: dict) -> tuple[list[str], int]:
    """A turni: un rifiuto era inevitabile (in qualunque disposizione) se in ogni turno che si poteva dare, con le
    prenotazioni accettate prima in quel turno più lei, i moduli minimi superano l'inventario."""
    reg = sol.get("registro") or []
    inp = {p["id"]: p for p in prenotazioni["prenotazioni"]}
    mod, tondi = sala["inventario"]["moduli"], sala["inventario"].get("tondi", {"quantita": 0, "capienza": 0})
    ppm, pt = mod.get("posti_per_modulo", 2), mod.get("posti_testate", 2)
    turni = _turni(sala)
    pol = _politica(sol, sala)[0]

    def kmin(c):
        return max(1, -(-(c - pt) // ppm))

    def moduli_minimi(cop):
        risp = sorted((kmin(c) for c in cop if c <= tondi.get("capienza", 0)), reverse=True)
        return sum(kmin(c) for c in cop) - sum(risp[:tondi.get("quantita", 0)])

    dimostrati, rifiuti = [], 0
    for r in reg:
        if r.get("esito") != "rifiutata" or r.get("motivo") not in (M_TURNO_PIENO, M_TURNI_PIENI, M_TEMPO):
            continue
        rifiuti += 1
        chiesto = _turno_chiesto(inp[r["id"]], turni, sala.get("turno_a_parita", "prima"))
        possibili = [t[0] for t in turni] if pol != "mai" else [chiesto]
        if all(moduli_minimi([inp[q["id"]]["coperti"] for q in reg if q["ordine"] < r["ordine"]
                              and q.get("esito") in ACCETTATE and q.get("turno_promesso") == tn] + [r["coperti"]])
               > mod["quantita"] for tn in possibili):
            dimostrati.append(r["id"])
    return dimostrati, rifiuti


def rifiuti_inevitabili_per_inventario(sala: dict, prenotazioni: dict, sol: dict) -> tuple[list[str], int]:
    """Condizione SUFFICIENTE (non necessaria) perché un rifiuto in ordine di arrivo fosse inevitabile in
    qualunque disposizione: per ogni orario ammesso esiste un istante in cui le prenotazioni attive (accettate
    prima, con l'orario promesso, più lei) richiedono più moduli dell'inventario anche usando al meglio i tondi.
    Ignora la geometria, quindi un rifiuto non dimostrato qui non è per questo evitabile."""
    if sala.get("turni"):
        return _rifiuti_inevitabili_turni(sala, prenotazioni, sol)
    reg = sol.get("registro") or []
    inp = {p["id"]: p for p in prenotazioni["prenotazioni"]}
    mod, tondi = sala["inventario"]["moduli"], sala["inventario"].get("tondi", {"quantita": 0, "capienza": 0})
    ppm, pt = mod.get("posti_per_modulo", 2), mod.get("posti_testate", 2)
    inizio, fine = _min(sala["servizio"]["inizio"]), _min(sala["servizio"]["fine"])
    riapp, passo = sala.get("riapparecchiatura_min", 0), sala.get("passo_orari_min", 15)

    def kmin(c):
        return max(1, -(-(c - pt) // ppm))

    def moduli_minimi(cop):
        risp = sorted((kmin(c) for c in cop if c <= tondi.get("capienza", 0)), reverse=True)
        return sum(kmin(c) for c in cop) - sum(risp[:tondi.get("quantita", 0)])

    dimostrati, rifiuti = [], 0
    for r in reg:
        motivo = r.get("motivo") or ""
        if r.get("esito") != "rifiutata" or not (motivo in (M_SALA_PIENA_ACC, M_TEMPO)
                                                 or motivo.startswith("nessun orario libero")):
            continue
        rifiuti += 1
        prima = [(_min(q["orario_promesso"]), inp[q["id"]]["coperti"]) for q in reg
                 if q["ordine"] < r["ordine"] and q.get("esito") in ACCETTATE]
        c, d = r["coperti"], _durata(sala, r["coperti"])
        ok = True
        spost = list(sala["spostamenti_ammessi_min"])
        if motivo.startswith("nessun orario libero") or (motivo == M_TEMPO and r.get("esiti_proposte")):
            n = int(sala.get("proposta_max_distanza_min", 120))
            spost += [k for k in range(-n, n + 1, passo)]
        for s in sorted(set(spost)):
            a = _min(r["orario_richiesto"]) + s
            if a < inizio or a + d > fine:
                continue
            if not any(moduli_minimi([cc for t, cc in prima if t <= tau < t + _durata(sala, cc) + riapp] + [c])
                       > mod["quantita"] for tau in range(a, a + d + riapp, passo)):
                ok = False
                break
        if ok:
            dimostrati.append(r["id"])
    return dimostrati, rifiuti


# --------------------------------------------------------------------------- disposizione libera sulla sala vera
# Geometria propria, esatta in cm (poligono della sala con la curva, rettangoli ruotati, cerchi), senza la griglia del
# modello. Soglie dell'editor della piantina: lato del quadrato = 32 unità, sedie 50 cm, "si toccano" sotto 1 unità.

V_LATO_U, V_SEDIE_CM, V_TOLL_U = 32, 50.0, 1.0
V_PORTATA_EXTRA_CM = 20         # il personale arriva fino a mezzo corridoio + 20 cm dalla zona di un tavolo


def _g_ruota(px, py, cx, cy, gradi):
    import math
    a = math.radians(gradi or 0)
    return cx + (px - cx) * math.cos(a) - (py - cy) * math.sin(a), cy + (px - cx) * math.sin(a) + (py - cy) * math.cos(a)


def _g_rett(cx, cy, w, h, rot=0.0):
    return [_g_ruota(cx + sx * w / 2, cy + sy * h / 2, cx, cy, rot) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def _g_box(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _g_dentro(p, poli) -> bool:
    c, j = False, len(poli) - 1
    for i in range(len(poli)):
        (xi, yi), (xj, yj) = poli[i], poli[j]
        if (yi > p[1]) != (yj > p[1]) and p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def _g_dps(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ll)) if ll else 0.0
    return ((p[0] - a[0] - t * dx) ** 2 + (p[1] - a[1] - t * dy) ** 2) ** 0.5


def _g_incrocio(a, b, c, d) -> bool:
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def _g_dss(a, b, c, d) -> float:
    if _g_incrocio(a, b, c, d):
        return 0.0
    return min(_g_dps(a, c, d), _g_dps(b, c, d), _g_dps(c, a, b), _g_dps(d, a, b))


def _g_lati(poli, chiuso=True):
    n = len(poli)
    return [(poli[i], poli[(i + 1) % n]) for i in range(n if chiuso else n - 1)]


def _g_dist(A: dict, B: dict) -> float:
    """Distanza tra due forme {"poli": [...]} (convesso), {"cerchio": (cx, cy, r)}, {"linea": [...], "meta": m}.
    Per una linea (muro) è la distanza dalla sua faccia."""
    if "cerchio" in A and "cerchio" not in B:
        A, B = B, A
    if "linea" in A:
        A, B = B, A
    if "cerchio" in B:
        cx, cy, r = B["cerchio"]
        if "cerchio" in A:
            ax, ay, ar = A["cerchio"]
            return max(0.0, ((ax - cx) ** 2 + (ay - cy) ** 2) ** 0.5 - ar - r)
        P = A["poli"]
        d = 0.0 if _g_dentro((cx, cy), P) else min(_g_dps((cx, cy), a, b) for a, b in _g_lati(P))
        return max(0.0, d - r)
    if "linea" in B:
        P, L = A["poli"], B["linea"]
        if any(_g_dentro(p, P) for p in L):
            return 0.0
        return max(0.0, min(_g_dss(a, b, c, d) for a, b in _g_lati(P) for c, d in _g_lati(L, False)) - B.get("meta", 0.0))
    P, Q = A["poli"], B["poli"]
    if any(_g_dentro(p, Q) for p in P) or any(_g_dentro(q, P) for q in Q):
        return 0.0
    return min(_g_dss(a, b, c, d) for a, b in _g_lati(P) for c, d in _g_lati(Q))


def _g_sovrapposti(A: dict, B: dict, eps: float = 1e-6) -> bool:
    """Le due forme hanno interni che si sovrappongono (toccarsi sul bordo non conta)."""
    if "cerchio" in A and "cerchio" in B:
        (ax, ay, ar), (bx, by, br) = A["cerchio"], B["cerchio"]
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 < ar + br - eps
    if "cerchio" in A:
        A, B = B, A
    if "cerchio" in B:
        cx, cy, r = B["cerchio"]
        P = A["poli"]
        return _g_dentro((cx, cy), P) or min(_g_dps((cx, cy), a, b) for a, b in _g_lati(P)) < r - eps
    P, Q = A["poli"], B["poli"]
    for poli in (P, Q):              # assi separatori (poligoni convessi)
        for a, b in _g_lati(poli):
            nx, ny = b[1] - a[1], a[0] - b[0]
            pa = [nx * x + ny * y for x, y in P]
            pb = [nx * x + ny * y for x, y in Q]
            norma = (nx * nx + ny * ny) ** 0.5 or 1.0
            if max(pa) <= min(pb) + eps * norma or max(pb) <= min(pa) + eps * norma:
                return False
    return True


def _g_bbox(f: dict):
    """Riquadro della forma (con l'eventuale fascia "margine" intorno a un poligono)."""
    if "cerchio" in f:
        cx, cy, r = f["cerchio"]
        return cx - r, cy - r, cx + r, cy + r
    pts = f.get("poli") or f.get("linea")
    m = f.get("meta", 0.0) + f.get("margine", 0.0)
    return min(p[0] for p in pts) - m, min(p[1] for p in pts) - m, max(p[0] for p in pts) + m, max(p[1] for p in pts) + m


def _g_dpunto(p, f: dict) -> float:
    """Distanza di un punto da una forma; un poligono con "margine" è il poligono con la fascia intorno (angoli tondi)."""
    if f.get("margine"):
        return max(0.0, _g_dpunto(p, {"poli": f["poli"]}) - f["margine"])
    if "cerchio" in f:
        cx, cy, r = f["cerchio"]
        return max(0.0, ((p[0] - cx) ** 2 + (p[1] - cy) ** 2) ** 0.5 - r)
    if "linea" in f:
        return max(0.0, min(_g_dps(p, a, b) for a, b in _g_lati(f["linea"], False)) - f.get("meta", 0.0))
    if _g_dentro(p, f["poli"]):
        return 0.0
    return min(_g_dps(p, a, b) for a, b in _g_lati(f["poli"]))


def _sala_libera_cm(dati: dict) -> dict:
    """Sala, muri, cose vietate e tavoli fissi della piantina, in cm."""
    lato = float((dati.get("scala") or {}).get("lato_quadrato_cm") or 80)
    cpu = lato / V_LATO_U
    muri = []
    for m in dati.get("muri") or []:
        if isinstance(m, dict) and len(m.get("punti") or []) >= 2:
            muri.append({"linea": [(float(p[0]) * cpu, float(p[1]) * cpu) for p in m["punti"]],
                         "meta": float(m.get("spessore_cm") if m.get("spessore_cm") is not None else 10) / 2})

    def area(pts):
        return abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                       for i in range(len(pts)))) / 2
    per = max(muri, key=lambda m: area(m["linea"]))
    stanza = per["linea"][:-1] if per["linea"][0] == per["linea"][-1] else per["linea"]

    def zona(o):
        if not all(k in o for k in ("x", "y", "w", "h")):
            return None
        x, y, w, h = (float(o[k]) * cpu for k in ("x", "y", "w", "h"))
        if o.get("forma") == "tondo":       # ellisse: poligono circoscritto
            import math
            kk = 1 / math.cos(math.pi / 24)
            return {"poli": [_g_ruota(x + w / 2 + kk * w / 2 * math.cos(i * math.pi / 12),
                                      y + h / 2 + kk * h / 2 * math.sin(i * math.pi / 12), x + w / 2, y + h / 2,
                                      float(o.get("rot") or 0)) for i in range(24)]}
        return {"poli": _g_rett(x + w / 2, y + h / 2, w, h, float(o.get("rot") or 0))}

    def aperture(p):
        """Zone davanti e dietro una porta o l'ingresso (come aperture() dell'editor)."""
        import math
        s = float(90 if p.get("spazio_libero_cm") is None else p["spazio_libero_cm"])
        if s <= 0:
            return []
        x, y, w, h = (float(p[k]) * cpu for k in ("x", "y", "w", "h"))
        cx, cy, rot = x + w / 2, y + h / 2, float(p.get("rot") or 0)
        orizz, a = w >= h, math.radians(rot)
        out = []
        for v in (-1, 1):
            lx, ly = (0.0, v * (h / 2 + s / 2)) if orizz else (v * (w / 2 + s / 2), 0.0)
            out.append({"poli": _g_rett(cx + lx * math.cos(a) - ly * math.sin(a), cy + lx * math.sin(a) + ly * math.cos(a),
                                        w if orizz else s, s if orizz else h, rot)})
        return out

    ostacoli = [(str(o.get("nome") or o.get("tipo") or "ostacolo"), z) for o in dati.get("ostacoli") or []
                if (z := zona(o))]
    vietate = list(ostacoli)
    porte = {}
    for p in dati.get("porte") or []:
        z = zona(p)
        if not z:
            continue
        nome = str(p.get("nome") or "porta")
        vietate.append((nome, z))
        ap = aperture(p)
        vietate += [(f"davanti a {nome}", a) for a in ap]
        porte[nome] = [a for a in ap if _g_dentro(_g_centro(a), stanza)
                       and not any(_g_dpunto(_g_centro(a), o) == 0 for _, o in ostacoli)]
    sorgente = None
    ing = dati.get("ingresso")
    if isinstance(ing, dict) and zona(ing):
        vietate.append(("ingresso", zona(ing)))
        for a in aperture(ing):
            vietate.append(("davanti all'ingresso", a))
            if _g_dentro(_g_centro(a), stanza):
                sorgente = a
    for p in dati.get("passaggi") or []:
        z = zona(p)
        if z:
            vietate.append((str(p.get("nome") or "passaggio"), z))
            if p.get("spazio_libero_cm") is not None:       # passaggio con lo spazio da lasciare davanti (come una porta)
                vietate += [(f"davanti a {p.get('nome') or 'passaggio'}", a) for a in aperture(p)]
    fissi, mobili = {}, 0
    for t in dati.get("tavoli") or []:
        if t.get("tipo") in ("quadrato", "blocco") and not t.get("fisso"):
            mobili += int(t.get("moduli") or 1) if t["tipo"] == "blocco" else 1
            continue
        cx, cy = float(t["x"]) * cpu, float(t["y"]) * cpu
        if t.get("tipo") == "tondo":
            corpo = {"cerchio": (cx, cy, float(t.get("r") if t.get("r") is not None else 16) * cpu)}
        else:
            if t.get("tipo") == "blocco":
                k = int(t.get("moduli") or 1)
                lungo_u = k * V_LATO_U + (k - 1) * 2
                w, h = (lungo_u, V_LATO_U) if t.get("verso") == "orizzontale" else (V_LATO_U, lungo_u)
            else:
                w, h = float(t.get("w") or V_LATO_U), float(t.get("h") or V_LATO_U)
            corpo = {"poli": _g_rett(cx, cy, w * cpu, h * cpu, float(t.get("rot") or 0))}
        fissi[str(t["id"])] = {"tavolo": t, "corpo": corpo}
    s = dati.get("sala") or {}
    contorno = (float(s.get("x", 0)) * cpu, float(s.get("y", 0)) * cpu,
                (float(s.get("x", 0)) + float(s.get("w", 0))) * cpu, (float(s.get("y", 0)) + float(s.get("h", 0))) * cpu)
    return {"cpu": cpu, "lato": lato, "muri": muri, "stanza": stanza, "vietate": vietate, "ostacoli": ostacoli,
            "porte": porte, "sorgente": sorgente, "fissi": fissi, "quadrati_mobili": mobili, "contorno": contorno}


def _g_oltre_un_muro(a: dict, b: dict, muri: list) -> bool:
    """Le due forme sono da parti opposte di un muro: il segmento fra i loro centri taglia un muro (le sedie di un
    tavolo non stanno dall'altra parte di un muro)."""
    ca, cb = _g_centro(a), _g_centro(b)
    return any(_g_dss(ca, cb, p, q) <= m["meta"] for m in muri for p, q in _g_lati(m["linea"], False))


def _g_centro(f):
    x0, y0, x1, y1 = _g_bbox(f)
    return (x0 + x1) / 2, (y0 + y1) / 2


def _fila_cm(t: dict, lato: float, sedie_cm: float) -> tuple[dict, list]:
    """Corpo e zone delle sedie (presenti) di una fila della soluzione: [(nome del lato, forma)]."""
    x, y, k = float(t["x_cm"]), float(t["y_cm"]), int(t["moduli"])
    vert = t.get("orientamento") == "verticale"
    w, h = (lato, k * lato) if vert else (k * lato, lato)
    corpo = {"poli": _g_box(x, y, x + w, y + h)}
    s = t.get("sedie") or {}
    la, lb = _lati_lunghi(t)
    zone = []
    for q in range(k):
        if la[q]:
            zone.append((f"lato a {q + 1}", _g_box(x - sedie_cm, y + q * lato, x, y + (q + 1) * lato) if vert
                         else _g_box(x + q * lato, y - sedie_cm, x + (q + 1) * lato, y)))
        if lb[q]:
            zone.append((f"lato b {q + 1}", _g_box(x + w, y + q * lato, x + w + sedie_cm, y + (q + 1) * lato) if vert
                         else _g_box(x + q * lato, y + h, x + (q + 1) * lato, y + h + sedie_cm)))
    if s.get("testa"):
        zone.append(("testa", _g_box(x, y - sedie_cm, x + w, y) if vert else _g_box(x - sedie_cm, y, x, y + h)))
    if s.get("coda"):
        zone.append(("coda", _g_box(x, y + h, x + w, y + h + sedie_cm) if vert else _g_box(x + w, y, x + w + sedie_cm, y + h)))
    return corpo, [(n, {"poli": p}) for n, p in zone]


def _lati_lunghi(t: dict) -> tuple[list, list]:
    """Sedie dei due lati lunghi, una per quadrato (allungate con zeri se la soluzione ne dà meno)."""
    s, k = t.get("sedie") or {}, int(t["moduli"])
    return [(list(s.get(n) or []) + [0] * k)[:k] for n in ("lato_a", "lato_b")]


def _sedie_pezzo(t: dict, a: int, b: int) -> int:
    s, k = t.get("sedie") or {}, int(t["moduli"])
    la, lb = _lati_lunghi(t)
    return sum(int(la[q]) + int(lb[q]) for q in range(a, b + 1)) + (int(s.get("testa") or 0) if a == 0 else 0) + \
        (int(s.get("coda") or 0) if b == k - 1 else 0)


def _cammino_libero(G: dict, ostacoli_extra: list[dict], regioni: dict[str, list], corridoio: float,
                    passo: float = 5.0) -> tuple[set, dict]:
    """Flood fill su una griglia di punti ogni `passo` cm: un punto è di corridoio se dista almeno corridoio/2 da muri,
    ostacoli, tavoli e zone delle sedie (e sta dentro la sala). Si parte dai punti davanti all'ingresso. Restituisce
    (nomi raggiunti, info) per tavoli (regioni) e porte."""
    import math
    from collections import deque
    x0, y0, x1, y1 = G["contorno"]
    x0, y0 = math.floor(x0 / passo) * passo, math.floor(y0 / passo) * passo      # punti sui multipli del passo
    na, nb = int(math.ceil((x1 - x0) / passo)) + 1, int(math.ceil((y1 - y0) / passo)) + 1
    r = corridoio / 2
    bloccato = [[False] * na for _ in range(nb)]
    stanza = G["stanza"]
    for b in range(nb):                                   # fuori dal poligono della sala
        y = y0 + b * passo
        xs = sorted(p1[0] + (y - p1[1]) * (p2[0] - p1[0]) / (p2[1] - p1[1]) for p1, p2 in _g_lati(stanza)
                    if (p1[1] > y) != (p2[1] > y))
        riga = bloccato[b]
        dentro_ = [False] * na
        for i in range(0, len(xs) - 1, 2):
            for a in range(max(0, int(math.ceil((xs[i] - x0) / passo))), min(na, int((xs[i + 1] - x0) // passo) + 1)):
                dentro_[a] = True
        for a in range(na):
            riga[a] = not dentro_[a]
    forme = [m for m in G["muri"]] + [o for _, o in G["ostacoli"]] + ostacoli_extra + \
        [f for lst in regioni.values() for f in lst]
    for f in forme:
        bx0, by0, bx1, by1 = _g_bbox(f)
        for b in range(max(0, int((by0 - r - y0) // passo)), min(nb, int((by1 + r - y0) // passo) + 2)):
            riga = bloccato[b]
            for a in range(max(0, int((bx0 - r - x0) // passo)), min(na, int((bx1 + r - x0) // passo) + 2)):
                if not riga[a] and _g_dpunto((x0 + a * passo, y0 + b * passo), f) < r - 1e-6:
                    riga[a] = True
    vis = [[False] * na for _ in range(nb)]
    coda = deque()
    if G["sorgente"] is not None:
        sx0, sy0, sx1, sy1 = _g_bbox(G["sorgente"])
        for b in range(max(0, int((sy0 - y0) // passo)), min(nb, int((sy1 - y0) // passo) + 2)):
            for a in range(max(0, int((sx0 - x0) // passo)), min(na, int((sx1 - x0) // passo) + 2)):
                if not bloccato[b][a] and _g_dentro((x0 + a * passo, y0 + b * passo), G["sorgente"]["poli"]):
                    vis[b][a] = True
                    coda.append((a, b))
    n_sorgenti = len(coda)
    while coda:
        a, b = coda.popleft()
        for c, d in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
            if 0 <= c < na and 0 <= d < nb and not vis[d][c] and not bloccato[d][c]:
                vis[d][c] = True
                coda.append((c, d))
    portata = r + V_PORTATA_EXTRA_CM
    raggiunti = set()
    for nome, lst in regioni.items():
        ok = False
        for f in lst:
            bx0, by0, bx1, by1 = _g_bbox(f)
            for b in range(max(0, int((by0 - portata - y0) // passo)), min(nb, int((by1 + portata - y0) // passo) + 2)):
                for a in range(max(0, int((bx0 - portata - x0) // passo)), min(na, int((bx1 + portata - x0) // passo) + 2)):
                    if vis[b][a] and _g_dpunto((x0 + a * passo, y0 + b * passo), f) <= portata:
                        ok = True
                        break
                if ok:
                    break
            if ok:
                break
        if ok:
            raggiunti.add(nome)
    for nome, zone in G["porte"].items():
        for z in zone:
            zx0, zy0, zx1, zy1 = _g_bbox(z)
            if any(vis[b][a] and _g_dentro((x0 + a * passo, y0 + b * passo), z["poli"])
                   for b in range(max(0, int((zy0 - y0) // passo)), min(nb, int((zy1 - y0) // passo) + 2))
                   for a in range(max(0, int((zx0 - x0) // passo)), min(na, int((zx1 - x0) // passo) + 2))):
                raggiunti.add(f"porta {nome}")
    return raggiunti, {"sorgenti": n_sorgenti}


def _mobili_v(dati: dict) -> dict:
    return {str(t["id"]): t for t in dati.get("tavoli") or [] if t.get("tipo") in ("quadrato", "blocco") and not t.get("fisso")}


def _moduli_v(t: dict) -> int:
    return int(t.get("moduli") or 1) if t.get("tipo") == "blocco" else 1


def _corpo_v(t: dict, cpu: float, spazio_u: float = 0) -> dict:
    """Il piano di un pezzo in cm: quadrati accostati, k·32 u (IPOTESI: i 2 u dell'editor sono solo grafici)."""
    k = _moduli_v(t)
    lu = k * V_LATO_U + (k - 1) * spazio_u
    wu, hu = (lu, V_LATO_U) if t.get("verso") == "orizzontale" or t.get("tipo") == "quadrato" else (V_LATO_U, lu)
    return {"poli": _g_rett(float(t["x"]) * cpu, float(t["y"]) * cpu, wu * cpu, hu * cpu, float(t.get("rot") or 0))}


def verifica_variante(dati: dict, prenotazioni: dict, sol: dict) -> list[Esito]:
    """Disposizione libera a partire dal disegno, con le mosse proposte dal motore. Il disegno così com'è è ammesso per
    definizione; si rifà da sé la piantina della disposizione (i pezzi della soluzione al posto dei mobili del
    disegno) e la si controlla come la sala vera a tavoli fermi; in più: i 29 quadrati tutti in sala e ognuno da un
    pezzo del disegno; i pezzi lasciati "come nel disegno" uguali al disegno; i pezzi accorciati dentro il pezzo da cui
    vengono; i tavoli nuovi dentro i muri, fuori dalle cose vietate e a 50 cm dagli altri tavoli con le loro sedie;
    nessun tavolo o porta che col disegno si raggiungeva diventa irraggiungibile."""
    import copy as _copy
    var = sol.get("variante") or {}
    pezzi = var.get("pezzi") or []
    mobili = _mobili_v(dati)
    G = _sala_libera_cm(dati)
    cpu, lato = G["cpu"], G["lato"]
    d = _copy.deepcopy(dati)
    d["tavoli"] = [t for t in d["tavoli"] if str(t["id"]) not in mobili]
    for p in pezzi:
        t = {"id": str(p["id"]), "tipo": p["tipo"], "x": float(p["x"]), "y": float(p["y"]), "rot": float(p.get("rot") or 0),
             "posti": int(p.get("posti") or 0), "fisso": False, "separabile": bool(p.get("separabile"))}
        if p["tipo"] == "blocco":
            t.update(moduli=int(p["moduli"]), verso=p.get("verso"))
        if p.get("stato") == "disegno" and str(p["id"]) in mobili:
            t = _copy.deepcopy(mobili[str(p["id"])])
        d["tavoli"].append(t)
    esiti = verifica_piantina(d, prenotazioni, sol)

    e = Esito("tutti i quadrati del disegno in sala (spostati, uniti o divisi, mai tolti)")
    totale = sum(_moduli_v(t) for t in mobili.values())
    in_sala = sum(int(t.get("moduli") or 1) if t.get("tipo") == "blocco" else 1 for t in sol.get("tavoli", [])
                  if t.get("tipo") in ("quadrato", "blocco") and str(t.get("id")) not in G["fissi"])
    if in_sala != totale:
        e.errore(f"{in_sala} quadrati nei tavoli della soluzione, il disegno ne ha {totale}")
    nei_pezzi = sum(int(p.get("moduli") or 1) for p in pezzi)
    if nei_pezzi != totale:
        e.errore(f"{nei_pezzi} quadrati nei pezzi della disposizione, il disegno ne ha {totale}")
    da_chi: dict[str, int] = {}
    for p in pezzi:
        da = {str(o): int(q) for o, q in (p.get("da") or {}).items()}
        if sum(da.values()) != int(p.get("moduli") or 1):
            e.errore(f"{p['id']}: {p.get('moduli')} quadrati, ma ne vengono {sum(da.values())} dai pezzi del disegno")
        for o, q in da.items():
            da_chi[o] = da_chi.get(o, 0) + q
    for o, q in da_chi.items():
        if o not in mobili:
            e.errore(f"quadrati da {o}, che non è un tavolo mobile del disegno")
        elif q != _moduli_v(mobili[o]):
            e.errore(f"il {o} ha {_moduli_v(mobili[o])} quadrati nel disegno, nella disposizione ne usa {q}")
    for o in mobili:
        if o not in da_chi:
            e.errore(f"i quadrati del {o} non sono in nessun pezzo")
    nuovi = [p for p in pezzi if p.get("stato") == "nuovo"]
    e.dettaglio = (f"{in_sala}/{totale} quadrati in sala, {len(nuovi)} tavoli nuovi, "
                   f"{sum(1 for p in pezzi if p.get('stato') == 'accorciato')} pezzi accorciati")
    esiti.append(e)

    e = Esito("pezzi cambiati: dentro i muri, fuori dalle cose vietate, a 50 cm dagli altri tavoli, raggiungibili")
    corpi = {}
    allungati = []
    for p in pezzi:
        if p.get("stato") == "nuovo":
            continue
        src = mobili.get(str(p["id"]))
        if src is None:
            e.errore(f"{p['id']}: «{p.get('stato')}» ma non è un pezzo del disegno")
            continue
        if p.get("stato") == "disegno":
            if any(abs(float(p.get(c) or 0) - float(src.get(c) or 0)) > 1e-6 for c in ("x", "y", "rot")) or \
                    int(p.get("moduli") or 1) != _moduli_v(src) or int(p.get("posti") or 0) != int(src.get("posti") or 0):
                e.errore(f"{p['id']}: dichiarato come nel disegno, ma posizione, quadrati o posti sono diversi")
        elif p.get("stato") == "allungato":
            allungati.append((p, src))
        elif p.get("stato") == "accorciato":
            # il pezzo che resta sta dentro l'impronta del disegno coi quadrati accostati (la più stretta)
            fuori = [q for q in _corpo_v(p, cpu, 0)["poli"] if not _g_dentro_tol(q, _corpo_v(src, cpu, 0)["poli"], 1.0)]
            if fuori or int(p.get("moduli") or 1) >= _moduli_v(src):
                e.errore(f"{p['id']}: accorciato, ma non sta dentro il pezzo del disegno o non è più corto")
            if int(p.get("posti") or 0) > int(src.get("posti") or 0):
                e.errore(f"{p['id']}: accorciato con {p.get('posti')} posti, nel disegno ne aveva {src.get('posti')}")
            if int(src.get("posti") or 0) == 2 * _moduli_v(src) and int(p.get("posti") or 0) > 2 * int(p.get("moduli") or 1):
                e.errore(f"{p['id']}: senza sedie in testa nel disegno, accorciato a {p.get('moduli')} quadrati con "
                         f"{p.get('posti')} posti (al massimo {2 * int(p.get('moduli') or 1)})")
        corpi[str(p["id"])] = _corpo_v(p, cpu)
    for p, src in allungati:                 # 140 cm fra i corpi, o non meno di quanta ce n'era nel disegno
        c = _corpo_v(p, cpu)
        if not all(_g_dentro(q, G["stanza"]) for q in c["poli"]):
            e.errore(f"{p['id']}: allungato, esce dalla sala")
        for m in G["muri"]:
            if _g_dist(c, {"linea": m["linea"]}) - m["meta"] < -1e-6:
                e.errore(f"{p['id']}: allungato, sul muro")
        for nv, z in G["vietate"]:
            if _g_sovrapposti(c, z):
                e.errore(f"{p['id']}: allungato · {nv}: ci sta sopra")
        if int(p.get("posti") or 0) > 2 * int(p.get("moduli") or 1) + 2:
            e.errore(f"{p['id']}: {p.get('posti')} posti per {p.get('moduli')} quadrati")
        c0 = _corpo_v(src, cpu)
        altri = [(fid, fx["corpo"]) for fid, fx in G["fissi"].items()] + \
            [(o, cc) for o, cc in corpi.items() if o != str(p["id"])] + \
            [(str(q["id"]), _fila_cm(q, lato, V_SEDIE_CM)[0]) for q in nuovi]
        for oid, cc in altri:
            serve = min(140.0, _g_dist(c0, cc))
            if _g_dist(c, cc) < serve - 1.5:
                e.errore(f"{p['id']}: allungato, a {_g_dist(c, cc):.0f} cm da {oid} (servono {serve:.0f} cm)")
    forme = {}
    spalliere = float((sol.get("geometria") or {}).get("spalliere_cm") or 40)
    for p in nuovi:
        corpo, zone = _fila_cm(p, lato, V_SEDIE_CM)
        forme[str(p["id"])] = (corpo, zone)
        sedie = sum(p["sedie"]["lato_a"]) + sum(p["sedie"]["lato_b"]) + p["sedie"]["testa"] + p["sedie"]["coda"]
        if int(p.get("posti") or 0) > sedie:
            e.errore(f"{p['id']}: {p.get('posti')} posti ma {sedie} sedie")
    for fid, (corpo, zone) in forme.items():
        for nome, fo in [("tavolo", corpo)] + [(f"sedia {n}", z) for n, z in zone]:
            if not all(_g_dentro(q, G["stanza"]) for q in fo["poli"]):
                e.errore(f"{fid} ({nome}): esce dalla sala")
            for m in G["muri"]:
                if _g_dist(fo, {"linea": m["linea"]}) - m["meta"] < -1e-6:
                    e.errore(f"{fid} ({nome}): sul muro")
            for nv, z in G["vietate"]:
                if _g_sovrapposti(fo, z):
                    e.errore(f"{fid} ({nome}) · {nv}: ci sta sopra")
            for oid, c in list(G["fissi"].items()) + list(corpi.items()):     # sedie altrui non note: 50 cm dal corpo
                cc = c["corpo"] if "corpo" in c else c
                if _g_dist(fo, cc) < V_SEDIE_CM - 1e-6 and not _g_oltre_un_muro(fo, cc, G["muri"]):
                    e.errore(f"{fid} ({nome}): dentro la zona delle sedie di {oid}")
            for oid, (c2, z2) in forme.items():          # due tavoli nuovi: le sedie sono note, 40 cm fra le zone
                if oid == fid:
                    continue
                for nome2, fo2 in [("tavolo", c2)] + [(f"sedia {n}", z) for n, z in z2]:
                    if _g_dist(fo, fo2) < spalliere - 1e-6 and not _g_oltre_un_muro(fo, fo2, G["muri"]):
                        e.errore(f"{fid} ({nome}): a meno di {spalliere:g} cm da {oid} ({nome2})")
    if nuovi or any(p.get("stato") == "accorciato" for p in pezzi):
        corr = float((sol.get("geometria") or {}).get("corridoio_cm") or 60)
        fissi = {}
        for fid, fx in G["fissi"].items():
            cc = fx["corpo"]
            fissi[fid] = [{"cerchio": (cc["cerchio"][0], cc["cerchio"][1], cc["cerchio"][2] + V_SEDIE_CM)}] if "cerchio" in cc \
                else [{"poli": cc["poli"], "margine": V_SEDIE_CM}]
        prima_reg = fissi | {o: [{"poli": _corpo_v(t, cpu)["poli"], "margine": V_SEDIE_CM}] for o, t in mobili.items()}
        dopo_reg = fissi | {o: [{"poli": c["poli"], "margine": V_SEDIE_CM}] for o, c in corpi.items()} | \
            {o: [c] + [z for _, z in zz] for o, (c, zz) in forme.items()}
        prima, _ = _cammino_libero(G, [], prima_reg, corr)
        dopo, _ = _cammino_libero(G, [], dopo_reg, corr)
        for x in sorted(x for x in prima - dopo if x in dopo_reg or x.startswith("porta")):
            e.errore(f"{x}: col disegno si raggiungeva, con la disposizione no")
        for p in nuovi:
            if str(p["id"]) not in dopo and any(str(o) in prima for o in (p.get("da") or {})):
                e.errore(f"{p['id']}: non si raggiunge, e i pezzi da cui viene col disegno si raggiungevano")
    e.dettaglio = (f"{len(nuovi)} tavoli nuovi; i pezzi rimasti come nel disegno sono ammessi così come sono; "
                   f"raggiungibilità col personale largo {(sol.get('geometria') or {}).get('corridoio_cm') or 60} cm, "
                   f"confrontata con il disegno")
    esiti.append(e)
    return esiti


def _g_dentro_tol(q, poli, tol: float) -> bool:
    """Il punto q sta nel poligono (convesso) o a meno di `tol` cm dal suo bordo."""
    if _g_dentro(q, poli):
        return True
    return _g_dist({"poli": [q, q, q]}, {"poli": poli}) <= tol


def verifica_libera(dati: dict, prenotazioni: dict, sol: dict) -> list[Esito]:
    """Sala vera con i tavoli mobili liberi: geometria esatta (inventario, dentro i muri, niente sopra cose vietate,
    sedie libere, corridoi e raggiungibilità), posti dei pezzi, turni, componenti e registro."""
    esiti: list[Esito] = []
    modalita = sol.get("modalita", {})
    ass, nons, registro = sol.get("assegnazioni", []), sol.get("non_sistemate", []), sol.get("registro")
    in_ordine = modalita.get("accettazione") == "ordine_di_arrivo" or registro is not None
    input_pr = {p["id"]: p for p in prenotazioni["prenotazioni"]}
    su_proposta = {r["id"] for r in (registro or []) if r.get("esito") == "accettata su proposta"}
    turni = [(str(t["nome"]), _min(t["inizio"]), _min(t["fine"])) for t in modalita.get("turni") or []]
    per_nome = {t[0]: t for t in turni}
    t_parita = modalita.get("turno_a_parita", "prima")
    geo = sol.get("geometria") or {}
    G = _sala_libera_cm(dati)
    lato, cpu = G["lato"], G["cpu"]
    toll = V_TOLL_U * cpu
    corridoio = float(geo.get("corridoio_cm") or 60)
    k_max = int(geo.get("k_max") or 4)

    e = Esito("turni (quelli della piantina, consecutivi)")
    inizi = [_min(x) for x in dati.get("turni") or []]
    if [t[1] for t in turni] != inizi:
        e.errore(f"inizi dei turni dichiarati {[_hhmm(t[1]) for t in turni]} diversi dalla piantina {dati.get('turni')}")
    for (n1, a1, b1), (n2, a2, b2) in zip(turni, turni[1:]):
        if b1 != a2:
            e.errore(f"il turno {n1} finisce alle {_hhmm(b1)}, il {n2} comincia alle {_hhmm(a2)}")
    e.dettaglio = ", ".join(f"{n} {_hhmm(a)}-{_hhmm(b)}" for n, a, b in turni)
    esiti.append(e)

    # ---- inventario
    e = Esito("inventario: quadrati delle file entro quelli della piantina, tavoli fissi uguali alla piantina")
    sol_tav = {str(t["id"]): t for t in sol.get("tavoli", [])}
    file = {tid: t for tid, t in sol_tav.items() if t.get("tipo") == "fila"}
    fissi_sol = {tid: t for tid, t in sol_tav.items() if t.get("tipo") != "fila"}
    if set(fissi_sol) != set(G["fissi"]):
        e.errore(f"tavoli fissi diversi: in più {sorted(set(fissi_sol) - set(G['fissi']))}, "
                 f"mancano {sorted(set(G['fissi']) - set(fissi_sol))}")
    for tid, t in fissi_sol.items():
        q = G["fissi"].get(tid, {}).get("tavolo")
        if q is not None and (t.get("tipo"), t.get("posti")) != (q["tipo"], q["posti"]):
            e.errore(f"{tid}: {t.get('tipo')} da {t.get('posti')} invece di {q['tipo']} da {q['posti']}")
    usati = 0
    for tid, t in file.items():
        k = int(t.get("moduli") or 0)
        usati += k
        if not 1 <= k <= k_max:
            e.errore(f"{tid}: fila di {k} quadrati (ammesse da 1 a {k_max})")
        if t.get("orientamento") not in ("orizzontale", "verticale"):
            e.errore(f"{tid}: orientamento {t.get('orientamento')!r} (ammessi orizzontale e verticale)")
        w, h = (lato, k * lato) if t.get("orientamento") == "verticale" else (k * lato, lato)
        if abs(float(t.get("larghezza_cm", 0)) - w) > 1e-6 or abs(float(t.get("altezza_cm", 0)) - h) > 1e-6:
            e.errore(f"{tid}: misure {t.get('larghezza_cm')} × {t.get('altezza_cm')} cm invece di {w:g} × {h:g}")
        s = t.get("sedie") or {}
        if len(s.get("lato_a") or []) != k or len(s.get("lato_b") or []) != k:
            e.errore(f"{tid}: le sedie dei lati lunghi non sono una per quadrato ({k} quadrati)")
        if t.get("posti") != _sedie_pezzo(t, 0, k - 1):
            e.errore(f"{tid}: posti {t.get('posti')} diversi dalle sedie disegnate ({_sedie_pezzo(t, 0, k - 1)})")
        if int(t.get("posti") or 0) > 2 * k + 2:
            e.errore(f"{tid}: {t.get('posti')} posti, oltre 2k+2 = {2 * k + 2}")
    if usati > G["quadrati_mobili"]:
        e.errore(f"{usati} quadrati nelle file, la piantina ne ha {G['quadrati_mobili']}")
    for r in ass:
        if str(r.get("tavolo")) not in sol_tav:
            e.errore(f"{r['id']}: tavolo {r.get('tavolo')!r} inesistente")
    e.dettaglio = (f"{len(file)} file con {usati}/{G['quadrati_mobili']} quadrati mobili, {len(fissi_sol)} tavoli fissi "
                   f"(lato del quadrato {lato:g} cm)")
    esiti.append(e)

    # ---- geometria delle file
    forme = {tid: _fila_cm(t, lato, V_SEDIE_CM) for tid, t in file.items()}
    e1 = Esito("tavoli e sedie dentro i muri (curva compresa) e dentro il contorno della sala")
    e2 = Esito("niente sopra ostacoli, porte (con lo spazio davanti), passaggi e ingresso")
    e3 = Esito("zone delle sedie libere da altri tavoli e dalle loro sedie, tavoli che non si toccano")
    cx0, cy0, cx1, cy1 = G["contorno"]
    n_zone = 0
    for tid, (corpo, zone) in forme.items():
        n_zone += len(zone)
        for nome, f, minimo in [("tavolo", corpo, toll)] + [(f"sedia {n}", z, 0.0) for n, z in zone]:
            if not all(_g_dentro(p, G["stanza"]) for p in f["poli"]) or \
                    any(_g_incrocio(a, b, c, d) for a, b in _g_lati(f["poli"]) for c, d in _g_lati(G["stanza"])):
                e1.errore(f"{tid} ({nome}): esce dal poligono della sala")
            if any(p[0] < cx0 or p[0] > cx1 or p[1] < cy0 or p[1] > cy1 for p in f["poli"]):
                e1.errore(f"{tid} ({nome}): esce dal contorno della sala")
            for m in G["muri"]:
                d = _g_dist(f, {"linea": m["linea"]}) - m["meta"]          # dalla faccia del muro (< 0: dentro il muro)
                if d < minimo - 1e-6:
                    e1.errore(f"{tid} ({nome}): a {d:.1f} cm dalla faccia del muro (minimo {minimo:g})")
                    break
            for nv, z in G["vietate"]:
                if minimo > 0:
                    d = _g_dist(f, z)
                    if d < minimo - 1e-6:
                        e2.errore(f"{tid} ({nome}) · {nv}: a {d:.1f} cm (minimo {minimo:g} cm)")
                elif _g_sovrapposti(f, z):
                    e2.errore(f"{tid} ({nome}) · {nv}: ci sta sopra")
            for fid, fx in G["fissi"].items():
                c = fx["corpo"]
                zona_fissa = ({"cerchio": (c["cerchio"][0], c["cerchio"][1], c["cerchio"][2] + V_SEDIE_CM)} if "cerchio" in c
                              else None)
                d = _g_dist(f, c)
                if d < V_SEDIE_CM - 1e-6 and (zona_fissa is None or _g_sovrapposti(f, zona_fissa)) and                         not _g_oltre_un_muro(f, c, G["muri"]):
                    e3.errore(f"{tid} ({nome}): a {d:.1f} cm dal tavolo fisso {fid}, dentro la zona delle sue sedie "
                              f"({V_SEDIE_CM:g} cm)")
    ids = sorted(forme)
    dist_min = None
    for i, a in enumerate(ids):
        ca, za = forme[a]
        for b in ids[i + 1:]:
            cb, zb = forme[b]
            d = _g_dist(ca, cb)
            if d < toll - 1e-6:
                e3.errore(f"{a} e {b}: i tavoli si toccano ({d:.1f} cm)")
            for na, fa in [("tavolo", ca)] + za:
                for nb, fb in [("tavolo", cb)] + zb:
                    if (na, nb) != ("tavolo", "tavolo") and _g_sovrapposti(fa, fb):
                        e3.errore(f"{a} ({na}) e {b} ({nb}): si sovrappongono")
            dr = min(_g_dist(fa, fb) for fa in [ca] + [z for _, z in za] for fb in [cb] + [z for _, z in zb])
            dist_min = dr if dist_min is None else min(dist_min, dr)
    e1.dettaglio = f"{len(forme)} file, {n_zone} zone delle sedie, muri spessi {', '.join(f'{2 * m['meta']:g}' for m in G['muri'])} cm"
    e2.dettaglio = f"{len(G['vietate'])} cose vietate (ostacoli, porte e spazio davanti, ingresso, passaggi), distanza minima {toll:g} cm"
    e3.dettaglio = (f"sedie {V_SEDIE_CM:g} cm; zona dei fissi {V_SEDIE_CM:g} cm su tutti i lati; tra due file almeno "
                    f"{dist_min:.0f} cm" if dist_min is not None else f"sedie {V_SEDIE_CM:g} cm")
    esiti += [e1, e2, e3]

    # ---- corridoi e raggiungibilità
    e = Esito(f"corridoi: ogni tavolo e ogni porta raggiungibili dall'ingresso (corridoio di {corridoio:g} cm)")
    import math
    reg_fissi = {}               # zona di un fisso: i punti a meno di 50 cm dal tavolo (fascia con gli angoli tondi)
    for fid, fx in G["fissi"].items():
        c = fx["corpo"]
        if "cerchio" in c:
            reg_fissi[fid] = [{"cerchio": (c["cerchio"][0], c["cerchio"][1], c["cerchio"][2] + V_SEDIE_CM)}]
        else:
            reg_fissi[fid] = [{"poli": c["poli"], "margine": V_SEDIE_CM}]
    reg_mobili = {tid: [c] + [z for _, z in zz] for tid, (c, zz) in forme.items()}
    base, _ = _cammino_libero(G, [], reg_fissi, corridoio)                       # sala senza file
    raggiunti, info = _cammino_libero(G, [], reg_fissi | reg_mobili, corridoio)
    gia_fuori = sorted(x for x in list(G["fissi"]) + [f"porta {p}" for p in G["porte"]] if x not in base)
    for tid in sorted(reg_mobili):
        if tid not in raggiunti:
            e.errore(f"{tid}: non si raggiunge dall'ingresso con un corridoio di {corridoio:g} cm")
    for x in list(G["fissi"]) + [f"porta {p}" for p in G["porte"]]:
        if x in base and x not in raggiunti:
            e.errore(f"{'tavolo fisso ' if not x.startswith('porta') else ''}{x}: le file lo chiudono, "
                     f"non si raggiunge più dall'ingresso")
    e.dettaglio = (f"{len(reg_mobili)} file e {len(G['fissi'])} fissi, {len(G['porte'])} porte, griglia di 5 cm, "
                   f"personale fino a {corridoio / 2 + V_PORTATA_EXTRA_CM:g} cm dalla zona di un tavolo, "
                   f"{info['sorgenti']} punti di partenza davanti all'ingresso"
                   + (f"; già irraggiungibili nella sala senza file (dalla piantina): {', '.join(gia_fuori)}" if gia_fuori else ""))
    esiti.append(e)

    # ---- prenotazioni, pezzi, posti
    e = Esito("ogni prenotazione presente esattamente una volta")
    conteggio: dict[str, int] = {}
    for r in ass + nons:
        conteggio[r["id"]] = conteggio.get(r["id"], 0) + 1
    for pid, n in conteggio.items():
        if pid not in input_pr:
            e.errore(f"{pid}: non è tra le prenotazioni in ingresso")
        elif n != 1:
            e.errore(f"{pid}: compare {n} volte")
    for pid in input_pr:
        if pid not in conteggio:
            e.errore(f"{pid}: manca (né seduta né non sistemata)")
    for r in ass + nons:
        p = input_pr.get(r["id"])
        if p is not None and (r["coperti"] != p["coperti"] or r["nome"] != p["nome"]
                              or _min(r["orario_richiesto"]) != _min(p["orario"])):
            e.errore(f"{r['id']}: nome/coperti/orario richiesto diversi dall'ingresso")
    e.dettaglio = f"{len(input_pr)} in ingresso = {len(ass)} sedute + {len(nons)} non sistemate"
    esiti.append(e)

    e = Esito("partizioni delle file contigue, per turno")
    n_div = 0
    for tid, t in file.items():
        k = int(t["moduli"])
        for n, _, _ in turni:
            pezzi = sorted(tuple(x) for x in (t.get("partizioni") or {}).get(n, [[0, k - 1]]))
            atteso = 0
            for a, b in pezzi:
                if a != atteso or b < a:
                    e.errore(f"{tid} nel turno {n}: pezzi {pezzi} non contigui")
                    break
                atteso = b + 1
            if atteso != k:
                e.errore(f"{tid} nel turno {n}: pezzi {pezzi} non coprono i {k} quadrati")
            n_div += len(pezzi) - 1
    e.dettaglio = f"{n_div} divisioni in tutto"
    esiti.append(e)

    e = Esito("posti: ogni prenotazione su un tavolo o pezzo del suo turno, coperti <= sedie")
    occupati: dict[tuple, str] = {}
    lungo: dict[tuple, list] = {}
    vuoti = 0
    for r in ass:
        tid, n = str(r.get("tavolo")), r.get("turno")
        if tid not in sol_tav or n not in per_nome:
            continue
        if tid in file:
            t = file[tid]
            k = int(t["moduli"])
            qq = r.get("quadrati")
            pezzi = [tuple(x) for x in (t.get("partizioni") or {}).get(n, [[0, k - 1]])]
            if not qq or tuple(qq) not in pezzi or not 0 <= qq[0] <= qq[1] < k:
                e.errore(f"{r['id']}: quadrati {qq} di {tid} non sono un pezzo della partizione del turno {n} {pezzi}")
                continue
            posti = _sedie_pezzo(t, qq[0], qq[1])
            nominali = 2 * (qq[1] - qq[0] + 1) + 2          # posti nominali del pezzo, come nel modo a tavoli fermi
            chiavi = [(tid, n, x) for x in range(qq[0], qq[1] + 1)]
            vuoti += nominali - r["coperti"]
        else:
            q = G["fissi"][tid]["tavolo"]
            if q["tipo"] == "lungo":
                g = r.get("gruppo")
                if g not in (1, 2):
                    e.errore(f"{r['id']}: sul lungo {tid} senza gruppo 1 o 2")
                    continue
                posti = int(q["posti"]) if g == 1 else min(LUNGO_DUE_GRUPPI, int(q["posti"]))
                chiavi = [(tid, n, f"g{g}")]
                lungo.setdefault((tid, n), []).append(r)
            else:
                posti = int(q["posti"])
                chiavi = [(tid, n, "t")]
                vuoti += posti - r["coperti"]
        if r.get("posti_tavolo") != posti:
            e.errore(f"{r['id']}: posti_tavolo {r.get('posti_tavolo')} invece di {posti}")
        if r["coperti"] > posti:
            e.errore(f"{r['id']}: {r['coperti']} coperti su {posti} posti ({tid})")
        for c in chiavi:
            if c in occupati:
                e.errore(f"{tid} nel turno {n}: {occupati[c]} e {r['id']} sullo stesso posto")
            occupati[c] = r["id"]
    e.dettaglio = f"{len(ass)} assegnazioni"
    esiti.append(e)

    e = Esito("tavolo lungo: un gruppo fino ai suoi posti, oppure due gruppi fino a 8")
    for (tid, n), lst in lungo.items():
        vuoti += int(G["fissi"][tid]["tavolo"]["posti"]) - sum(r["coperti"] for r in lst)
        if any(r.get("gruppo") == 2 for r in lst) and not any(r.get("gruppo") == 1 for r in lst):
            e.errore(f"{tid} nel turno {n}: c'è il secondo gruppo senza il primo")
        if len(lst) > 2:
            e.errore(f"{tid} nel turno {n}: {len(lst)} gruppi")
        if len(lst) == 2 and any(r["coperti"] > LUNGO_DUE_GRUPPI for r in lst):
            e.errore(f"{tid} nel turno {n}: due gruppi ma uno supera {LUNGO_DUE_GRUPPI}")
    e.dettaglio = " · ".join(f"{n}: " + " + ".join(str(r["coperti"]) for r in lst) for (_, n), lst in sorted(lungo.items())) or "non usato"
    esiti.append(e)

    tutto = {tid: (turni[0][1], turni[-1][2]) for tid in sol_tav} if turni else {}
    esiti.append(_controlli_turni(ass, input_pr, su_proposta, turni, per_nome, t_parita, tutto)[0])

    e = Esito("motivi delle non sistemate coerenti")
    capmax = max([int(fx["tavolo"]["posti"]) for fx in G["fissi"].values()] + [2 * k_max + 2])
    pol, _ = _politica(sol, dati)
    for r in nons:
        mot = r.get("motivo", "")
        if r["coperti"] > capmax:
            attesi = {M_TROPPO_GRANDE}
        elif pol == "mai":
            attesi = {M_TURNO_PIENO, M_TEMPO}
        else:
            attesi = {M_TURNI_PIENI, M_TEMPO} | ({M_PROPOSTA_RIFIUTATA} if pol == "entro" else set())
        if mot not in attesi:
            e.errore(f"{r['id']}: motivo {mot!r}, atteso uno tra {sorted(attesi)}")
    e.dettaglio = f"{len(nons)} non sistemate, capienza massima {capmax}"
    esiti.append(e)

    e = Esito("componenti dell'obiettivo ricalcolate (posti vuoti nominali, divisioni, cambi di partizione)")
    comp = sol.get("obiettivo_componenti", {})
    nomi = [t[0] for t in turni]
    cambi = sum(1 for t in file.values() for a, b in zip(nomi, nomi[1:])
                if sorted(map(tuple, t["partizioni"].get(a, []))) != sorted(map(tuple, t["partizioni"].get(b, []))))
    for chiave, campo, valore in (("non_sistemate", "numero", len(nons)), ("posti_vuoti", "posti", vuoti),
                                  ("divisioni_blocchi", "numero", n_div), ("riallestimenti", "numero", cambi)):
        if comp.get(chiave, {}).get(campo) != valore:
            e.errore(f"{chiave}: riportato {comp.get(chiave, {}).get(campo)}, ricalcolato {valore}")
    totale = sum(v.get("costo", 0) for v in comp.values() if isinstance(v, dict))
    if comp.get("totale") != totale:
        e.errore(f"totale {comp.get('totale')} diverso dalla somma dei costi {totale}")
    ob = sol.get("solver", {}).get("obiettivo")
    if ob is not None and str(sol.get("solver", {}).get("origine", "solver")).startswith("solver") and ob != comp.get("totale"):
        e.errore(f"obiettivo del solver {ob} diverso dal totale {comp.get('totale')}")
    e.dettaglio = f"posti vuoti {vuoti}, divisioni {n_div}, cambi di partizione {cambi}, totale {comp.get('totale')}"
    esiti.append(e)

    esiti += _controlli_registro(sol, dati, registro, in_ordine, input_pr, ass, nons, True, turni, t_parita,
                                 set(), 0, 0, 1, 24 * 60)
    return esiti


def tavoli_vuoti(sol: dict) -> list[str]:
    usati = {r["tavolo"] for r in sol.get("assegnazioni", [])}
    return [t["id"] for t in sol.get("tavoli", []) if t["id"] not in usati]


def stampa(esiti: list[Esito], sol: dict, out=sys.stdout, sala: dict | None = None,
           prenotazioni: dict | None = None) -> bool:
    tutti_ok = all(e.ok for e in esiti)
    for e in esiti:
        print(f"{'PASS' if e.ok else 'FAIL'}  {e.nome} — {e.dettaglio}", file=out)
        for msg in e.errori[:20]:
            print(f"        - {msg}", file=out)
        if len(e.errori) > 20:
            print(f"        ... altri {len(e.errori) - 20} errori", file=out)
    vuoti = tavoli_vuoti(sol)
    if vuoti:
        print(f"INFO  tavoli senza prenotazioni: {', '.join(vuoti)}", file=out)
    if sol.get("non_sistemate"):
        print("INFO  il verificatore controlla l'ammissibilità e la coerenza dei motivi, ma in generale non può "
              "dimostrare che un rifiuto fosse inevitabile", file=out)
        if sol.get("registro") and sala is not None and prenotazioni is not None and not _e_piantina(sala):
            dim, n = rifiuti_inevitabili_per_inventario(sala, prenotazioni, sol)
            print(f"INFO  rifiuti per sala piena dimostrati inevitabili dal solo conteggio dei moduli (in qualunque "
                  f"disposizione): {len(dim)}/{n}" + (f" ({', '.join(dim)})" if dim else "")
                  + ("; per gli altri non è dimostrabile qui" if len(dim) < n else ""), file=out)
    if any(r.get("proposta_prima") or r.get("proposta_dopo") for r in sol.get("registro") or []):
        print("INFO  il verificatore controlla che le proposte siano ammesse e coerenti, ma non può dimostrare che "
              "siano le più vicine possibili", file=out)
    n_ok = sum(e.ok for e in esiti)
    print(f"ESITO: {'PASS' if tutti_ok else 'FAIL'} ({n_ok}/{len(esiti)} controlli superati)", file=out)
    return tutti_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verificatore indipendente della serata")
    ap.add_argument("--sala", required=True)
    ap.add_argument("--prenotazioni", required=True)
    ap.add_argument("--soluzione", required=True)
    a = ap.parse_args(argv)
    sala = leggi_sala(a.sala)
    with open(a.prenotazioni, encoding="utf-8") as fh:
        pren = json.load(fh)
    with open(a.soluzione, encoding="utf-8") as fh:
        sol = json.load(fh)
    print(f"Verifica indipendente di {a.soluzione}")
    return 0 if stampa(verifica(sala, pren, sol), sol, sala=sala, prenotazioni=pren) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
