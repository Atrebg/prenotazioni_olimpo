"""Decisore dell'Olimpo per i casi in cui il passo 1 di `assegna-tavoli` non trova un'unità libera.

CP-SAT esatto nel turno chiesto, con tutte le confermate del turno (più le mosse di tavoli confermate) e il gruppo
nuovo: prima il minor numero di cambi di tavolo a chi è già confermato, poi accessibilità, costo e spareggi del passo
1. Se non entra prova l'altro turno (proposta) o rifiuta. Scrive il file della serata e il registro come la skill
`stato-serata` (`deciso_da` "python"), rilegge e controlla. Stampa una riga JSON e sotto la risposta per il
proprietario. Unità, soglie e versione della piantina vengono da `agente/catalogo.md`, le zone da `agente/regole.md`.

Uso, dalla cartella del fork:
  .venv/Scripts/python.exe motore/decidi.py --serata serate/AAAA-MM-GG.json --nome X --coperti N
      --turno primo|secondo --oggi AAAA-MM-GG [--orario HH:MM] [--note "..."] [--n N]
      [--consenti-cambi | --senza-cambi] [--prova] [--tempo S]
--n: la riga che c'è già (risposta a una domanda o a una proposta, modifica). --prova: decide senza scrivere, con la
risposta di una disponibilità. Esito "decisore" (exit 2): non decide, il messaggio passa a decisore-sala.
"""
import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date

FORK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TURNI = {"primo": "20:00", "secondo": "21:30"}
ALTRO = {"primo": "secondo", "secondo": "primo"}
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
CAMPI = ["n", "id", "nome", "coperti", "orario", "turno_chiesto", "turno", "stato", "unita", "proposta", "domanda",
         "note", "motivo", "ricevuta_il"]
MOBILITA = re.compile(r"carrozzin|rotelle|anzian|cammin|deambul|stampell|disabil|bastone", re.I)
BIMBI = re.compile(r"seggiolon|passeggin", re.I)
FESTA = re.compile(r"compleann|festa|anniversar|laurea|tranquill", re.I)
ZONE = {"vicino all'ingresso": "ingresso", "in fondo": "angolo", "saletta": "saletta", "lato destro": "destro",
        "contro una parete": "parete", "percorso dei camerieri": "camerieri", "passaggio dei bagni": "bagni"}


class Decisore(Exception):
    """Caso che lo script non decide: passa a decisore-sala."""


@dataclass(eq=False)
class Unita:
    nome: str
    posti: int
    pezzi: frozenset
    tagli: frozenset = frozenset()
    cosa: str = ""
    ordine: int = 0
    tavoli: frozenset = field(init=False)
    lungo: str = field(init=False)  # "intero", "prima", "seconda" o None
    l_posti: int = 0  # lungo: posti dell'intero, posti di una metà, nome della prima metà
    l_meta: int = 0
    l_prima: str = ""

    def __post_init__(self):
        self.tavoli = frozenset(re.sub(r"(-\d+|[a-z]+)$", "", p) for p in self.pezzi)
        self.tagli = frozenset((min(self.tavoli), t) for t in self.tagli)
        c = self.cosa.lower()
        self.unione, self.intero, self.alto = "unione" in c, "blocco separabile" in c, "alto" in c or "sgabell" in c
        self.lungo = ("intero" if "lungo, un gruppo" in c else "prima" if "prima metà" in c
                      else "seconda" if "seconda metà" in c else None)


# ---------- letture: catalogo, zone, piantina, serata, registro ----------

def leggi_catalogo():
    testo = open(os.path.join(FORK, "agente", "catalogo.md"), encoding="utf-8").read()
    versione = {"aggiornata": re.search(r'"aggiornata": "([^"]+)"', testo).group(1),
                "righe_storico": int(re.search(r"(\d+) righe di `storico`", testo).group(1))}
    us = {}
    for riga in testo.split("## Unità", 1)[1].split("\n## ", 1)[0].splitlines():
        celle = [c.strip() for c in re.split(r"(?<!\\)\|", riga)[1:-1]]
        if len(celle) == 5 and re.match(r"\d", celle[0]):
            for nome in celle[0].split(", "):
                usa = [nome] if celle[2].startswith("sé") else celle[2].split()
                tagli = [t.strip() for t in celle[3].replace("\\|", "|").split(",") if "|" in t]
                us[nome] = Unita(nome, int(re.match(r"\d+", celle[1]).group()), frozenset(usa), frozenset(tagli),
                                 celle[4], len(us))
    for u in us.values():
        if u.lungo:
            fam = [v for v in us.values() if v.lungo and v.tavoli == u.tavoli]
            u.l_posti = next(v.posti for v in fam if v.lungo == "intero")
            u.l_meta = max(v.posti for v in fam if v.lungo != "intero")
            u.l_prima = next(v.nome for v in fam if v.lungo == "prima")
    try:  # soglie per turno: servono solo a scrivere il motivo di un "pieno"
        col = re.search(r"\| famiglia di pezzi \|(.*)\|", testo).group(1).split("|")
        ob = re.search(r"Obbligato se c'è un gruppo da (\d+) in su, oppure\s+almeno due gruppi da (\d+) in su", testo)
        totale = re.search(r"\| \*\*totale per turno\*\* \|(.*)\|", testo).group(1)
        soglie = {"inizi": [1 if "≤" in c else int(re.match(r"\s*(\d+)", c).group(1)) for c in col],
                  "totale": [int(x) for x in re.findall(r"\*\*(\d+)\*\*", totale)],
                  "lungo": [int(x) for x in re.search(r"\*\*Lungo a un gruppo\*\*: ([\d, ]+)", testo).group(1)
                            .strip(" ,").split(", ")],
                  "obbligato": (int(ob.group(1)), int(ob.group(2))),
                  "posti": int(re.search(r"\*\*(\d+) posti al massimo\*\*", testo).group(1))}
    except (AttributeError, ValueError):
        soglie = None
    return versione, us, soglie


def leggi_zone():
    zone = {}
    try:
        testo = open(os.path.join(FORK, "agente", "regole.md"), encoding="utf-8").read()
    except OSError:
        return zone
    for riga in testo.splitlines():
        celle = [c.strip() for c in riga.split("|")[1:-1]]
        chiave = next((v for k, v in ZONE.items() if len(celle) == 3 and celle[0].startswith(k)), None)
        if chiave:
            zone[chiave] = {t for a, b in re.findall(r"(\d+[A-Z]?)(?:-(\d+))?", celle[1])
                            for t in ([str(i) for i in range(int(a), int(b) + 1)] if b and a.isdigit() else [a])}
    return zone


def versione_piantina():
    testo = open(os.path.join(FORK, "olimpo", "piantina.html"), encoding="utf-8").read()
    sala = json.loads(re.search(r'<script type="application/json" id="sala">\s*(\{.*?\})\s*</script>', testo,
                                re.S).group(1))
    return {"aggiornata": sala.get("aggiornata"), "righe_storico": len(sala.get("storico") or [])}


def leggi_registro(cartella, st):
    righe = list(st.get("registro") or [])  # file vecchi: le loro righe vengono prima della cartella
    if os.path.isdir(cartella):
        righe += [json.load(open(os.path.join(cartella, f), encoding="utf-8"))
                  for f in sorted(os.listdir(cartella)) if f.endswith(".json")]
    return righe


def unita_turno(cat, st, T):
    """Unità del catalogo più quelle delle mosse confermate valide nel turno T."""
    us = dict(cat)
    for mo in st.get("mosse") or []:
        if mo.get("stato") == "confermata" and T in (mo.get("turni") or []):
            pezzi = frozenset().union(*(cat[x].pezzi if x in cat else {x} for x in mo["usa"]))
            us[mo["unita"]] = Unita(mo["unita"], int(mo["posti"]), pezzi, ordine=len(us))
    return us


# ---------- regole: taglia, posti vuoti, accessibilità, spareggi ----------

def turno_di(orario):
    h, m = map(int, orario.split(":"))
    d1, d2 = abs(h * 60 + m - 1200), abs(h * 60 + m - 1290)
    return None if min(d1, d2) > 45 else "primo" if d1 <= d2 else "secondo"


def vicino(orario):
    h, m = map(int, orario.split(":"))
    return "primo" if abs(h * 60 + m - 1200) <= abs(h * 60 + m - 1290) else "secondo"


def adatta(u, c):  # posti e limiti di taglia: chi sta in una metà del lungo non va sul lungo intero
    return u.posti >= c and not (u.lungo == "intero" and c <= u.l_meta)


def vuoti(u, c):  # sul lungo intero e sulla prima metà si apparecchia tutto il lungo
    return (u.l_posti if u.lungo in ("intero", "prima") else u.posti) - c


def disagio(note, u, zone):
    """Regola di buonsenso 1 (filtro del passo 1): 0 = va bene, di più = peggio. Mai un tavolo alto a chi cammina
    male: è l'ultima scelta."""
    d = 0
    if MOBILITA.search(note or ""):
        evitare = zone.get("camerieri", set()) | zone.get("bagni", set()) | zone.get("saletta", set())
        d += 3 if u.alto else 0 if u.tavoli <= zone.get("ingresso", set()) else 2 if u.tavoli & evitare else 1
    if BIMBI.search(note or ""):
        d += 1 if u.tavoli & (zone.get("camerieri", set()) | zone.get("bagni", set())) else 0
    return d


def riserva(u, occupati, us):
    """Spareggio 2: True se usa tavoli di un'unione ancora libera (tutti e due i tavoli liberi) o è un blocco
    separabile intero."""
    return u.intero or any(v.unione and v is not u and v.tavoli & u.tavoli and not v.pezzi & occupati
                           for v in us.values())


def zona(c, note, u, zone):  # spareggio 3: feste e gruppi da 8 in su in fondo, coppie contro una parete
    if c >= 8 or FESTA.search(note or ""):
        return next((i for i, z in enumerate(("angolo", "saletta", "destro")) if u.tavoli <= zone.get(z, set())), 3)
    return (0 if u.tavoli <= zone.get("parete", set()) else 1) if c <= 2 else 0


def valida(us, occ, lungo=True):
    """Errori dell'assegnazione di un turno: unità, posti, pezzi in comune, seconda metà del lungo senza la prima
    (questa solo con lungo=True: togliendo una prenotazione che si modifica la seconda metà può restare sola)."""
    err, usati, nomi = [], {}, {p["unita"] for p in occ}
    for p in occ:
        u = us.get(p["unita"])
        if not u:
            err.append(f"n {p['n']}: unità {p['unita']} inesistente")
            continue
        if (p.get("coperti") or 0) > u.posti:
            err.append(f"n {p['n']}: {p['coperti']} coperti su {u.nome} da {u.posti}")
        for pz in u.pezzi:
            if pz in usati:
                err.append(f"n {p['n']} ({u.nome}) e n {usati[pz]} usano tutti e due {pz}")
            usati[pz] = p["n"]
        if lungo and u.lungo == "seconda" and u.l_prima not in nomi:
            err.append(f"n {p['n']}: seconda metà del lungo senza la prima")
    return "; ".join(err)


def passo1(us, occ, c, note, zone):
    """Passo 1 di assegna-tavoli: miglior incastro tra le unità libere (filtro, costo, spareggi), senza cambi."""
    occupati = set().union(*(us[p["unita"]].pezzi for p in occ))
    tagli = set().union(*(us[p["unita"]].tagli for p in occ))
    cand = [u for u in us.values() if adatta(u, c) and not u.pezzi & occupati
            and (u.lungo != "seconda" or us[u.l_prima].pezzi & occupati)]
    return min(cand, default=None, key=lambda u: (
        disagio(note, u, zone), 10 * vuoti(u, c) + 4 * len(u.tagli - tagli), u.unione, riserva(u, occupati, us),
        zona(c, note, u, zone), u.ordine))


def perche_pieno(cop, us, soglie, con_mosse):
    """Motivo di un "pieno" (il CP-SAT l'ha già dimostrato): il conteggio del catalogo superato, se c'è."""
    grande = max(u.posti for u in us.values())
    if max(cop) > grande:
        return f"{max(cop)} coperti, il tavolo più grande ne ha {grande}"
    if soglie and not con_mosse:
        o11, o9 = soglie["obbligato"]
        uno = any(x >= o11 for x in cop) or sum(x >= o9 for x in cop) >= 2
        tot = soglie["lungo"] + soglie["totale"][len(soglie["lungo"]):] if uno else soglie["totale"]
        for i in reversed(range(len(tot))):
            k = sum(x >= soglie["inizi"][i] for x in cop)
            if k > tot[i]:
                chi = "prenotazioni" if soglie["inizi"][i] == 1 else f"gruppi da {soglie['inizi'][i]} in su"
                lungo = " con il lungo a un gruppo solo" if uno and i < len(soglie["lungo"]) else ""
                return f"{k} {chi}, al massimo {tot[i]}{lungo}"
        if sum(cop) > soglie["posti"]:
            return f"{sum(cop)} coperti, al massimo {soglie['posti']}"
    return f"nessuna disposizione possibile dei {len(cop)} gruppi del turno, verifica esatta"


def importa_cp_model():
    """cp_model importa pandas (circa 5 s su questo PC) solo per le funzioni a serie, che qui non servono: se pandas
    non è già caricato, al suo posto va un modulo vuoto con Index e Series; se non basta, import normale."""
    import types
    finto = "pandas" not in sys.modules
    if finto:
        sys.modules["pandas"] = types.ModuleType("pandas")
        sys.modules["pandas"].Index = sys.modules["pandas"].Series = type("NonUsato", (), {})
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        raise Decisore("manca ortools: uv pip install -r requirements.txt --python .venv/Scripts/python.exe")
    except AttributeError:
        del sys.modules["pandas"]
        finto = False
        from ortools.sat.python import cp_model
    finally:
        if finto:
            sys.modules.pop("pandas", None)
    return cp_model


def assegna(us, occ, c, note, zone, tempo, soglie, T, con_mosse):
    """Esito del gruppo (c, note) nel turno T: passo 1, poi CP-SAT con i cambi di tavolo."""
    sola = any(us[p["unita"]].lungo == "seconda" and us[p["unita"]].l_prima not in {q["unita"] for q in occ}
               for p in occ)  # seconda metà del lungo rimasta sola (modifica): la sistema il CP-SAT
    u = None if sola else passo1(us, occ, c, note, zone)
    if u:
        return {"entra": True, "unita": u.nome, "cambi": [], "disagio": disagio(note, u, zone)}
    pieno = {"entra": False, "dimostrato": True, "provati": None}
    cop = [p["coperti"] for p in occ] + [c]
    if not any(adatta(v, c) for v in us.values()):
        return pieno | {"motivo": f"{T} turno: pieno (dimostrato: {perche_pieno(cop, us, soglie, con_mosse)})"}
    cp_model = importa_cp_model()
    gr = occ + [{"coperti": c, "note": note, "unita": None}]
    G, m, x = len(occ), cp_model.CpModel(), {}
    for g, p in enumerate(gr):
        scelte = [v for v in us.values() if adatta(v, p["coperti"]) or v.nome == p["unita"]]
        for v in scelte:
            x[g, v.nome] = m.NewBoolVar(f"x{g}_{v.nome}")
        m.AddExactlyOne(x[g, v.nome] for v in scelte)
    per_pezzo, y = {}, {}
    for (g, nu), val in x.items():
        for pz in us[nu].pezzi:
            per_pezzo.setdefault(pz, []).append(val)
        for t in us[nu].tagli:
            y.setdefault(t, m.NewBoolVar(f"t{t}"))
            m.AddImplication(val, y[t])
    for vs in per_pezzo.values():
        m.AddAtMostOne(vs)
    for v in us.values():  # la seconda metà del lungo solo se c'è la prima
        if v.lungo == "seconda":
            m.Add(sum(val for (g, nu), val in x.items() if nu == v.nome)
                  <= sum(val for (g, nu), val in x.items() if nu == v.l_prima))
    occupati = set().union(*(us[p["unita"]].pezzi for p in occ))
    rango = {v.nome: i for i, v in enumerate(sorted(
        (v for v in us.values() if (G, v.nome) in x),
        key=lambda v: (v.unione, riserva(v, occupati, us), zona(c, note, v, zone), v.ordine)))}
    stadi = [  # in ordine: cambi, accessibilità, costo (10 a posto vuoto, 4 a taglio), spareggi, ordine fisso
        sum(1 - x[g, p["unita"]] for g, p in enumerate(occ)),
        sum(disagio(gr[g]["note"], us[nu], zone) * val for (g, nu), val in x.items()),
        sum(10 * vuoti(us[nu], gr[g]["coperti"]) * val for (g, nu), val in x.items()) + 4 * sum(y.values()),
        sum(rango[nu] * val for (g, nu), val in x.items() if g == G),
        sum(us[nu].ordine * (g + 1) * val for (g, nu), val in x.items())]
    s = cp_model.CpSolver()
    s.parameters.num_workers = 8
    fine, sol, ottimo = time.time() + tempo, None, True
    for k, ob in enumerate(stadi):
        if isinstance(ob, int) and sol:
            continue
        if not isinstance(ob, int):
            m.Minimize(ob)
        s.parameters.max_time_in_seconds = max(fine - time.time(), 0.001 if k == 0 else 0.2)
        r = s.Solve(m)
        if r == cp_model.INFEASIBLE and sol is None:
            return pieno | {"motivo": f"{T} turno: pieno (dimostrato: {perche_pieno(cop, us, soglie, con_mosse)})"}
        if r not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if sol is None:
                return {"entra": False, "dimostrato": False, "motivo": f"{T} turno: non trovo posto (non dimostrato)",
                        "provati": f"{T}: passo 1 nessuna unità libera; CP-SAT esatto su tutte le disposizioni dei "
                                   f"{G + 1} gruppi del turno, cambi di tavolo ammessi: tempo scaduto ({tempo:g} s) "
                                   f"senza una disposizione e senza la prova che non c'è"}
            ottimo = False  # tempo scaduto dopo una disposizione valida: si tiene la migliore trovata
            break
        ottimo = ottimo and r == cp_model.OPTIMAL
        sol = {g: nu for (g, nu), val in x.items() if s.Value(val)}
        if not isinstance(ob, int):
            m.Add(ob <= s.Value(ob))
        m.ClearHints()
        for val in x.values():
            m.AddHint(val, s.Value(val))
    cambi = [{"n": p["n"], "nome": p["nome"], "coperti": p["coperti"], "da": p["unita"], "a": sol[g]}
             for g, p in enumerate(occ) if sol[g] != p["unita"]]
    return {"entra": True, "unita": sol[G], "cambi": cambi, "disagio": disagio(note, us[sol[G]], zone),
            "ottimo": ottimo}


# ---------- controllo (C1-C15 di controllo-serata; C2-C3 sono il confronto delle versioni) ----------

def controlla(st, reg, cat):
    err, pr = [], st.get("prenotazioni", [])
    err += [f"C1 manca {k}" for k in ("serata", "piantina", "prenotazioni", "mosse") if k not in st]
    for p in pr:
        manca = [k for k in CAMPI if k not in p and k != "domanda"]
        if manca:
            err.append(f"C1 n {p.get('n')}: mancano {', '.join(manca)}")
    if len({p.get("n") for p in pr}) != len(pr):
        err.append("C4 n ripetuti")
    for T in TURNI:
        e = valida(unita_turno(cat, st, T), [p for p in pr if p.get("stato") == "confermata" and p.get("turno") == T])
        if e:
            err.append(f"C6 {T} turno: {e}")
    eventi = {}
    for r in reg:
        eventi.setdefault(r.get("n"), []).append(r)
    for p in pr:
        n, s, ev = p.get("n"), p.get("stato"), eventi.get(p.get("n"), [])
        nomi = {r.get("evento") for r in ev}
        if not ev:
            err.append(f"C11 n {n}: nessuna riga di registro")
        if s == "confermata":
            if p.get("turno") not in TURNI or p.get("coperti") is None or p.get("domanda"):
                err.append(f"C5 n {n}: turno, coperti o domanda")
            if p.get("proposta") and p["proposta"].get("turno") != p.get("turno"):
                err.append(f"C10 n {n}: turno diverso dalla proposta")
            prom = [r for r in ev if r.get("evento") in ("confermata", "accettata su proposta", "modifica")]
            ult = [r.get("a") if r.get("evento") == "cambio tavolo" else r.get("unita") for r in ev
                   if r.get("evento") in ("confermata", "accettata su proposta", "modifica", "cambio tavolo")]
            if not prom or prom[-1].get("turno") != p.get("turno") or ult[-1] != p.get("unita"):
                err.append(f"C9 n {n}: turno o unità diversi dal registro")
        elif s == "in_attesa":
            if p.get("unita") or p.get("turno") or not (p.get("proposta") or p.get("domanda")):
                err.append(f"C7 n {n}: in_attesa")
        elif s == "rifiutata":
            if p.get("unita") or p.get("turno") or not p.get("motivo"):
                err.append(f"C7 n {n}: rifiutata")
            if nomi & {"confermata", "accettata su proposta"}:
                err.append(f"C8 n {n}: era dentro ed è rifiutata")
        elif s == "annullata":
            if p.get("unita") or not p.get("motivo") or "annullata" not in nomi:
                err.append(f"C7/C8 n {n}: annullata")
        else:
            err.append(f"C1 n {n}: stato {s}")
    primi = list(dict.fromkeys(r.get("n") for r in reg if isinstance(r.get("n"), int)))
    if primi != sorted(primi):
        err.append("C11 le prime righe del registro non sono in ordine di n")
    for r in reg:
        if (r.get("evento") in ("proposta", "rifiutata") and "non trovo posto" in (r.get("motivo") or "")
                and not r.get("provati")):
            err.append(f"C15 n {r.get('n')}: manca provati")
    for mo in st.get("mosse") or []:
        if mo.get("stato") == "confermata" and not set(mo.get("usa") or []) <= set().union(
                *(u.pezzi for u in cat.values()), cat):
            err.append(f"C13 mossa {mo.get('id')}: pezzi inesistenti")
    return err


# ---------- scrittura ----------

def canonico(st, a_capo):
    """Il file nel formato di stato-serata: 2 spazi, una prenotazione (o mossa) per riga."""
    out, chiavi = ["{"], list(st)
    for i, k in enumerate(chiavi):
        v, fine = st[k], "," if i < len(chiavi) - 1 else ""
        if isinstance(v, list) and v and all(isinstance(e, dict) for e in v):
            out += [f'  "{k}": ['] + [f"    {json.dumps(e, ensure_ascii=False)}" + ("," if j < len(v) - 1 else "")
                                      for j, e in enumerate(v)] + [f"  ]{fine}"]
        else:
            out.append(f'  "{k}": {json.dumps(v, ensure_ascii=False)}{fine}')
    return a_capo.join(out + ["}"]) + a_capo


def testo_nuovo(testo, st, toccate):
    """Cambia solo le righe toccate (riga per riga); se il file non è nel formato solito, lo riscrive canonico."""
    a_capo = "\r\n" if testo and "\r\n" in testo else "\n"
    if not testo:
        return canonico(st, a_capo)
    righe = testo.splitlines()
    try:
        for p in toccate:
            nuova = "    " + json.dumps(p, ensure_ascii=False)
            i = next((k for k, r in enumerate(righe) if r.startswith(f'    {{"n": {p["n"]}, ')), None)
            if i is not None:
                righe[i] = nuova + ("," if righe[i].rstrip().endswith(",") else "")
                continue
            k = next(k for k, r in enumerate(righe) if r.strip().startswith('"prenotazioni": ['))
            if righe[k].strip() == '"prenotazioni": [],':
                righe[k:k + 1] = ['  "prenotazioni": [', nuova, "  ],"]
            else:
                j = next(j for j in range(k + 1, len(righe)) if righe[j].strip() in ("],", "]"))
                righe[j - 1] += "" if righe[j - 1].rstrip().endswith(",") else ","
                righe.insert(j, nuova)
        nuovo = a_capo.join(righe) + a_capo
        if json.loads(nuovo) == st:
            return nuovo
    except (StopIteration, ValueError):
        pass
    return canonico(st, a_capo)


def scrivi(path, testo, st, toccate, eventi, cartella):
    """File della serata (atomico) e una riga di registro per file; in caso di errore rimette tutto com'era."""
    os.makedirs(cartella, exist_ok=True)
    esistenti = [f for f in os.listdir(cartella) if f.endswith(".json")]
    nnn = max([len(esistenti)] + [int(f[:3]) for f in esistenti if f[:3].isdigit()])
    scritti = []
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(testo_nuovo(testo, st, toccate))
        os.replace(tmp, path)
        for ev in eventi:
            nnn += 1
            nome = f"{nnn:03d}-n{ev['n']}-{ev['evento'].replace(' ', '-')}.json"
            with open(os.path.join(cartella, nome), "x", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            scritti.append(nome)
    except Exception:
        annulla(path, testo, cartella, scritti)
        raise
    return scritti


def annulla(path, testo, cartella, scritti):
    for nome in scritti:
        os.remove(os.path.join(cartella, nome))
    if testo is None:
        if os.path.exists(path):
            os.remove(path)
    else:
        with open(path + ".tmp", "w", encoding="utf-8", newline="") as f:
            f.write(testo)
        os.replace(path + ".tmp", path)


# ---------- decisione ----------

def decidi(a):
    versione, cat, soglie = leggi_catalogo()
    if versione_piantina() != versione:
        raise Decisore(f"la piantina ({versione_piantina()}) è diversa dal catalogo ({versione}): "
                       "il catalogo va rigenerato (skill sala)")
    zone, path = leggi_zone(), a.serata
    testo = open(path, encoding="utf-8").read() if os.path.exists(path) else None
    if testo is None:
        d = date.fromisoformat(re.search(r"(\d{4}-\d\d-\d\d)\.json$", path).group(1))
        st = {"serata": d.isoformat(), "giorno": GIORNI[d.weekday()], "piantina": dict(versione),
              "prenotazioni": [], "mosse": []}
    else:
        st = json.loads(testo)
    if st.get("piantina") != versione:
        raise Decisore(f"la serata è assegnata sulla piantina {st.get('piantina')}, il catalogo è {versione}")
    if st["serata"] < a.oggi:
        raise Decisore("la serata è già passata")
    cartella = os.path.join(os.path.dirname(path), f"registro-{st['serata']}")
    reg, pr = leggi_registro(cartella, st), st["prenotazioni"]
    riga = next((p for p in pr if p["n"] == a.n), None) if a.n is not None else None
    if a.n is not None and (not riga or riga["stato"] in ("rifiutata", "annullata")):
        raise Decisore(f"la prenotazione n {a.n} non c'è o non è aperta ({riga and riga['stato']})")
    doppi = [p for p in pr if a.n is None and not a.prova and a.nome and p["nome"].lower() == a.nome.lower()
             and p["stato"] in ("confermata", "in_attesa")]
    if doppi:
        raise Decisore(f"c'è già {doppi[0]['nome']} (n {doppi[0]['n']}, {doppi[0]['stato']}): va chiesto se è "
                       "un'altra prenotazione o la stessa, poi si rilancia con --n")
    r0 = riga or {}
    nome, c, orario = a.nome or r0.get("nome") or "", a.coperti or r0.get("coperti"), a.orario or r0.get("orario")
    note = a.note if a.note is not None else (r0.get("note") or "")
    if not c or (orario and not re.fullmatch(r"\d\d:\d\d", orario)):
        raise Decisore("mancano i coperti, o l'orario non è HH:MM")
    prop = r0.get("proposta") if r0.get("stato") == "in_attesa" else None
    tipo = ("modifica" if r0.get("stato") == "confermata" else
            "si" if prop and prop.get("turno") in TURNI and a.turno in (None, prop["turno"]) else "nuova")
    fuori = tipo == "nuova" and bool(orario) and turno_di(orario) is None and a.turno in (None, vicino(orario))
    if tipo == "si":
        T = prop["turno"]
    elif a.turno or a.orario:
        T = a.turno or turno_di(a.orario) or vicino(a.orario)
    else:
        T = r0.get("turno") if tipo == "modifica" else (turno_di(orario) or vicino(orario)) if orario else None

    def prova(t):  # esito nel turno t, senza la prenotazione stessa (modifica)
        us = unita_turno(cat, st, t)
        occ = [p for p in pr if p["stato"] == "confermata" and p["turno"] == t and p is not riga]
        err = valida(us, occ, lungo=False)
        if err:
            raise Decisore(f"il {t} turno del file non è valido: {err}")
        if tipo == "modifica" and t == riga["turno"] and c <= riga["coperti"]:
            return {"entra": True, "unita": riga["unita"], "cambi": [], "disagio": 0}  # meno coperti: resta dov'è
        return assegna(us, occ, c, note, zone, a.tempo, soglie, t, len(us) > len(cat))

    d = date.fromisoformat(st["serata"])
    giorno = f"{['lun', 'mar', 'mer', 'gio', 'ven', 'sab', 'dom'][d.weekday()]} {d:%d/%m}"
    gruppo = f"{nome} ×{c}"

    def quanti(k):
        return f"{k} prenotazione già confermata" if k == 1 else f"{k} prenotazioni già confermate"

    def capito(t):
        parti = [nome, f"{c} persona" if c == 1 else f"{c} persone", giorno, f"{t} turno ({TURNI[t]})" if t else orario]
        return "✓ " + " · ".join(x for x in parti if x)

    def frase(t, e, maiuscola=True):
        s = (f"il {t} turno è pieno" if e.get("dimostrato") else
             f"nel {t} turno c'è posto solo spostando chi è già confermato" if e.get("negato") else
             f"nel {t} turno non trovo posto")
        return s[0].upper() + s[1:] if maiuscola else s

    def due(t, e, e2):  # tutti e due i turni senza posto
        if e.get("dimostrato") and e2.get("dimostrato"):
            return f"{frase(t, e, False)}, e anche il {ALTRO[t]}"
        if not any(x.get(k) for x in (e, e2) for k in ("dimostrato", "negato")):
            return f"{frase(t, e, False)}, e neanche nel {ALTRO[t]}"
        return f"{frase(t, e, False)}, e {frase(ALTRO[t], e2, False)}"

    if a.prova:  # disponibilità: decide senza scrivere
        esiti = {t: prova(t) for t in ([T] if T else TURNI)}
        if T and not esiti[T]["entra"]:
            esiti[ALTRO[T]] = prova(ALTRO[T])
        righe = [capito(T)]
        for t, e in esiti.items():
            k = len(e.get("cambi") or [])
            if e["entra"] and T and t != T:
                righe.append(f"Nel {t} ({TURNI[t]}) sì" + (", cambiando di tavolo chi è già confermato." if k else "."))
            elif e["entra"]:
                righe.append(f"Sì, nel {t} turno ({TURNI[t]}), cambiando di tavolo {quanti(k)}." if k
                             else f"Sì: nel {t} turno ({TURNI[t]}) c'è posto per {c}.")
            else:
                righe.append(f"No: il {t} turno è pieno per {c}." if e.get("dimostrato")
                             else f"Nel {t} turno non trovo posto per {c}.")
        attesa = [p for p in pr if p["stato"] == "in_attesa" and p is not riga and p.get("coperti")
                  and ((p.get("proposta") or {}).get("turno") or p.get("turno_chiesto")) in esiti]
        if attesa:
            righe.append("C'è anche una richiesta in attesa di risposta (" + ", ".join(
                f"{p['nome']} ×{p['coperti']}" for p in attesa) + "): se dice sì, il posto si riduce.")
        return {"esito": "disponibilità", "n": a.n, "turni": esiti, "scritto": False,
                "risposta": "\n".join(righe + ["Non ho registrato niente."])}

    if T not in TURNI:
        raise Decisore("manca il turno (né --turno né --orario)")
    e = prova(T)
    if e["entra"] and e["cambi"] and not fuori:  # per la serata di oggi non si sposta nessuno senza chiederlo
        k, chi = len(e["cambi"]), ", ".join(f"{x['nome']} ×{x['coperti']}" for x in e["cambi"])
        if a.senza_cambi:
            e = {"entra": False, "negato": True,
                 "motivo": f"{T} turno: posto solo cambiando tavolo a {quanti(k)}, non accettato dal proprietario"}
        elif st["serata"] == a.oggi and not a.consenti_cambi:
            return {"esito": "chiedi cambi", "n": a.n, "turno": T, "unita": e["unita"], "cambi": e["cambi"],
                    "scritto": False, "risposta": f"{capito(T)}\nNel {T} turno c'è posto solo cambiando tavolo a "
                                                  f"{quanti(k)} ({chi}). Lo faccio?"}
    n = riga["n"] if riga else max([p["n"] for p in pr] + [0]) + 1
    base = dict(riga) if riga else {"n": n, "id": None, "nome": nome, "coperti": c, "orario": orario,
                                    "turno_chiesto": None, "turno": None, "stato": "in_attesa", "unita": None,
                                    "proposta": None, "domanda": None, "note": note, "motivo": None,
                                    "ricevuta_il": a.oggi}
    if tipo == "nuova":  # nuova, o risposta a una domanda: si aggiorna la riga che c'è
        base.update(nome=nome, coperti=c, orario=orario, note=note, domanda=None, proposta=None,
                    turno_chiesto=None if fuori else T)
    toccate, eventi, domanda = [], [], None
    esito = {"esito": None, "n": n, "turno": None, "unita": None, "cambi": [], "motivo": None, "provati": None}

    def ev(nn, evento, **k):
        return {"quando": a.oggi, "n": nn, "evento": evento, **k, "deciso_da": "python"}

    if e["entra"] and not fuori:  # conferma, sì a una proposta o modifica, con gli eventuali cambi
        diff = [s for s in (f"{r0.get('coperti')} → {c} coperti" if c != r0.get("coperti") else "",
                            f"{r0.get('turno')} → {T} turno" if T != r0.get("turno") else "",
                            f"{r0.get('orario')} → {orario}" if orario != r0.get("orario") else "",
                            f"note: {note or 'nessuna'}" if note != (r0.get("note") or "") else "") if s]
        if tipo == "modifica" and not diff:
            return {"esito": "non modificata", "n": n, "scritto": False,
                    "risposta": f"{capito(T)}\nNessun cambiamento: la prenotazione è già così."}
        for x in e["cambi"]:
            toccate.append(dict(next(p for p in pr if p["n"] == x["n"]), unita=x["a"]))
            eventi.append(ev(x["n"], "cambio tavolo", turno=T, da=x["da"], a=x["a"], motivo=f"per far posto a {gruppo}",
                             testo=f"{x['nome']} ×{x['coperti']}: da {x['da']} a {x['a']}"))
        if tipo == "modifica":
            base.update(coperti=c, orario=orario, note=note, turno_chiesto=T, turno=T, unita=e["unita"],
                        proposta=base["proposta"] if T == riga["turno"] else None)
            eventi.append(ev(n, "modifica", turno=T, unita=e["unita"], testo=f"{nome}: {', '.join(diff)}"))
            esito["esito"], seconda = "modificata", "Modificata."
        else:
            base.update(stato="confermata", turno=T, unita=e["unita"], motivo=None, domanda=None)
            eventi.append(ev(n, "accettata su proposta" if tipo == "si" else "confermata", turno=T, unita=e["unita"],
                             testo=f"{gruppo}: sì alla proposta, {T} turno ({TURNI[T]})" if tipo == "si" else gruppo))
            esito["esito"], seconda = ("accettata" if tipo == "si" else "confermata"), "Confermata."
        esito.update(turno=T, unita=e["unita"], cambi=e["cambi"], ottimo=e.get("ottimo", True))
        righe = [capito(T), seconda]
        if e.get("disagio"):
            u = unita_turno(cat, st, T)[e["unita"]]
            righe.append(f"{nome} ({note}) " + ("è a un tavolo alto" if u.alto and MOBILITA.search(note) else
                                                "non è vicino all'ingresso" if MOBILITA.search(note) else
                                                "è vicino al percorso dei camerieri o al passaggio dei bagni")
                         + ": non c'era un posto migliore.")
        if e["cambi"]:
            righe.append(f"Ho cambiato tavolo a {quanti(len(e['cambi']))} dello stesso turno (lo vedi nel riepilogo).")
    elif tipo == "modifica":  # non entra: non cambia niente
        e2 = prova(ALTRO[T])
        righe = [capito(T), f"{frase(T, e)} per {c}: resta la prenotazione di prima ({r0['coperti']} persone, "
                            f"{r0['turno']} turno)."]
        if e2["entra"] and (ALTRO[T] != r0["turno"] or c > r0["coperti"]):  # non ripropone la prenotazione com'è
            righe.append(f"Nel {ALTRO[T]} turno c'è posto per {c}: la modifico lì?")
        return {"esito": "non modificata", "n": n, "turno": T, "motivo": e["motivo"], "scritto": False,
                "risposta": "\n".join(righe)}
    else:  # proposta (orario fuori turno, o turno senza posto) oppure rifiuto
        e2 = {"entra": True} if fuori and e["entra"] else prova(ALTRO[T])
        motivo = "; ".join(([f"alle {orario} non c'è un turno"] if fuori else [])
                           + ([] if e["entra"] else [e["motivo"]]))
        provati = "; ".join(x for x in (e.get("provati"), e2.get("provati")) if x) or None
        con_provati = {"provati": provati} if provati else {}
        if e["entra"] or e2["entra"]:
            T2 = T if e["entra"] else ALTRO[T]
            base.update(stato="in_attesa", turno=None, unita=None, motivo="aspetta il sì alla proposta",
                        proposta={"turno": T2, "motivo": motivo})
            eventi.append(ev(n, "proposta", turno=T2, motivo=motivo, **con_provati,
                             testo=f"{gruppo}: proposto il {T2} turno ({TURNI[T2]})"))
            seconda = (f"Alle {orario} non c'è un turno. Il più vicino è il {T}, alle {TURNI[T]}." if e["entra"] else
                       f"Alle {orario} non c'è un turno, e {frase(T, e, False)}." if fuori else
                       f"Nel frattempo {frase(T, e, False)}." if tipo == "si" else f"{frase(T, e)}.")
            if not e["entra"]:
                seconda += f" Posso nel {T2}, alle {TURNI[T2]}."
            esito.update(esito="proposta", turno=T2, motivo=motivo, provati=provati)
            domanda = "Va bene?"
        else:
            motivo = "; ".join(x for x in (motivo, e2["motivo"]) if x)
            base.update(stato="rifiutata", turno=None, unita=None, motivo=motivo, domanda=None)
            eventi.append(ev(n, "rifiutata", motivo=motivo, **con_provati,
                             testo=f"{gruppo}: rifiutata, nessuno dei due turni ha posto"))
            seconda = ("Rifiutata: " + (f"alle {orario} non c'è un turno; " if fuori else
                                        "nel frattempo " if tipo == "si" else "") + f"{due(T, e, e2)}.")
            esito.update(esito="rifiutata", motivo=motivo, provati=provati)
        righe = [capito(None if fuori else T), seconda]
    toccate.append(base)

    # scrittura, rilettura e controllo: se la scrittura aggiunge un errore, il file torna com'era
    nuovo = dict(st, prenotazioni=[next((t for t in toccate if t["n"] == p["n"]), p) for p in pr]
                 + [t for t in toccate if t["n"] not in {p["n"] for p in pr}])
    prima = set(controlla(st, reg, cat))
    scritti = scrivi(path, testo, nuovo, toccate, eventi, cartella)
    st2 = json.load(open(path, encoding="utf-8"))
    dopo = controlla(st2, leggi_registro(cartella, st2), cat)
    nuovi = [x for x in dopo if x not in prima]
    if st2 != nuovo or nuovi:
        annulla(path, testo, cartella, scritti)
        raise Decisore(f"controllo FAIL dopo la scrittura, file rimesso com'era: {'; '.join(nuovi) or 'file diverso'}")
    righe.append("Controllo: PASS" if not dopo else f"Controllo: FAIL (già nel file prima: {'; '.join(dopo[:3])})")
    return esito | {"scritto": True, "registro": scritti, "controllo": "PASS" if not dopo else dopo,
                    "risposta": "\n".join(righe + ([domanda] if domanda else []))}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--serata", required=True)
    p.add_argument("--oggi", required=True)
    p.add_argument("--nome")
    p.add_argument("--coperti", type=int)
    p.add_argument("--turno", choices=list(TURNI))
    p.add_argument("--orario")
    p.add_argument("--note")
    p.add_argument("--n", type=int)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--consenti-cambi", action="store_true")
    g.add_argument("--senza-cambi", action="store_true")
    p.add_argument("--prova", action="store_true")
    p.add_argument("--tempo", type=float, default=20.0, help="secondi al massimo per il CP-SAT di un turno")
    a = p.parse_args()
    t0 = time.time()
    try:
        out = decidi(a)
    except Decisore as ex:
        out = {"esito": "decisore", "motivo": str(ex), "scritto": False, "risposta": ""}
    except Exception as ex:  # noqa: BLE001 - qualsiasi errore: niente decisione, passa a decisore-sala
        out = {"esito": "decisore", "motivo": f"errore dello script: {ex!r}", "scritto": False, "risposta": ""}
    out["secondi"] = round(time.time() - t0, 2)
    print(json.dumps(out, ensure_ascii=False))
    if out.get("risposta"):
        print(out["risposta"])
    sys.exit(2 if out["esito"] == "decisore" else 0)


if __name__ == "__main__":
    main()
