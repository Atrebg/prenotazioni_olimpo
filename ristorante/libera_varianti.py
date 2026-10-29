"""Disposizione libera a partire dal disegno: i 29 quadrati restano sempre tutti in sala, le mosse le propone il motore.

Regola di Giacomo (28/10/2026): i tavoli non spariscono mai, al massimo si dividono o si uniscono. Il disegno della
piantina, così com'è (posizioni, rotazioni, posti decisi da lui), è una soluzione ammessa per definizione e fa da
variante 0: con quella la serata è esattamente il modo a tavoli fermi.

Mosse (`proponi_mosse`): quando una richiesta non entra in nessun turno con la disposizione corrente, il motore cerca un
tavolo nuovo da k quadrati (il più piccolo che ha i posti: 2 = 6, 3 = 8, 4 = 10, contate le sedie che ci stanno
davvero) in ogni posizione della sala dove rispetta le regole rispetto a muri, cose vietate (strettoia, 90 cm davanti
all'apertura, ingresso) e tavoli fissi; i pezzi mobili che gli danno fastidio (corpo, sedie da 50 cm, 40 cm fra le zone
delle sedie, il lato d'accesso da 60 cm) si smontano e danno i loro quadrati; se non bastano, si stacca un quadrato da
un altro pezzo (che resta dov'è, più corto); i quadrati che avanzano diventano un tavolo nuovo dove le regole lo
permettono. Il personale deve arrivare dall'ingresso a ogni tavolo e alle due porte con la disposizione effettiva
(niente strade riservate). Si provano le mosse con meno pezzi toccati e più posti, ognuna con tutte le accettate.

Accettazione in ordine di arrivo con il modello a tavoli fermi (`modello_piantina.py`) sulla disposizione corrente: il
turno chiesto, poi l'altro turno; solo se la richiesta verrebbe rifiutata si provano le mosse (turno chiesto, poi
l'altro). Le accettate restano accettate e nel loro turno, ma il tavolo può cambiare fino alla cena: il registro dice
chi ha cambiato tavolo. La disposizione fisica è una per serata (si prepara prima delle 20:00); fra un turno e l'altro
cambiano solo le divisioni dei blocchi, come nel modo a tavoli fermi. Se le mosse hanno fatto perdere qualcosa dopo, si
tiene la serata col solo disegno (riserva): mai peggio del modo a tavoli fermi.
"""
from __future__ import annotations

import copy
import math
import re
import time
from typing import Callable

from .dati import (MAI, MOTIVO_PROPOSTA_RIFIUTATA, MOTIVO_TEMPO_SCADUTO, MOTIVO_TROPPO_GRANDE, MOTIVO_TURNI_PIENI,
                   MOTIVO_TURNO_PIENO, ORDINE_DI_ARRIVO, Istanza, costruisci_istanza, min_a_hhmm)
from .modello import (_costruisci, _estrai, _impossibile_per_conteggio, _non_sistemata, _parametri, _risolvi_modello,
                      _Voce, calcola_componenti, modalita_turni)
from .modello_libero import (_allarga, _libero_fuori, _metti, corpo_e_lati, misure_celle, posti_pezzo, scatole_fila,
                             spazi, zone_accesso)
from .piantina import Piantina
from .sala_libera import SalaLibera, libero_box, rett_ruotato, Forma

LIBERA = "libera"
GAP_U = 0      # IPOTESI (28/10): i quadrati "uniti" di Giacomo sono tavoli accostati, un pezzo da k è lungo k·80 cm;
#                i 2 u fra i quadrati sono solo il modo di disegnarli dell'editor (restano nella mappa)
_VOCALE = re.compile(r"\b(il|al|del|dal) (?=(?:8\d?|11|1|N\d+)\b)")
_ELISO = {"il": "l'", "al": "all'", "del": "dell'", "dal": "dall'"}


def articoli(testo: str) -> str:
    """Gli articoli davanti ai numeri dei tavoli: l'8, all'8, dell'11, l'N1; il 7, al 7."""
    return _VOCALE.sub(lambda m: _ELISO[m.group(1)], testo)
POSTI_REGOLA = {2: 6, 3: 8, 4: 10}         # regola di Giacomo per i pezzi uniti (1 quadrato: posti_quadrato_separato)
MOSSE_DA_PROVARE = 4                       # mosse provate col solver per ogni richiesta che non entra


def _mobili(dati: dict) -> dict[str, dict]:
    return {str(t["id"]): t for t in dati.get("tavoli") or [] if t.get("tipo") in ("quadrato", "blocco") and not t.get("fisso")}


def _moduli(t: dict) -> int:
    return int(t.get("moduli") or 1) if t.get("tipo") == "blocco" else 1


def posti_regola(dati: dict, k: int) -> int:
    return int(dati.get("posti_quadrato_separato") or 4) if k == 1 else POSTI_REGOLA.get(k, 2 * k + 2)


def corpo_disegnato(sala: SalaLibera, t: dict) -> Forma:
    """Il piano di un tavolo mobile come è disegnato (rotazione compresa), in cm."""
    k = _moduli(t)
    L = k * 32 + (k - 1) * GAP_U
    wu, hu = (L, 32) if t.get("verso") == "orizzontale" or t["tipo"] == "quadrato" else (32, L)
    return Forma(f"tavolo {t['id']}", "poli", tuple(rett_ruotato(float(t["x"]) * sala.cpu, float(t["y"]) * sala.cpu,
                                                                 wu * sala.cpu, hu * sala.cpu, float(t.get("rot") or 0))))


def _box_corpo(sala: SalaLibera, t: dict) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = corpo_disegnato(sala, t).bbox()
    g = sala.griglia_cm
    return int(x0 // g), int(y0 // g), int(math.ceil(x1 / g)), int(math.ceil(y1 / g))


def _impronte(sala: SalaLibera, t: dict, B: int):
    """Per un pezzo: prefissi delle celle del corpo + 50 cm (sedie) e del corpo + 50 cm + B celle (spalliere)."""
    cache = sala.__dict__.setdefault("_impronte_pezzi", {})
    chiave = (str(t["id"]), t["tipo"], _moduli(t), t.get("verso"), round(float(t["x"]), 2), round(float(t["y"]), 2),
              float(t.get("rot") or 0))
    if chiave not in cache:
        forme = [corpo_disegnato(sala, t)]       # corpo + 50 cm tutt'intorno: le sedie, anche dei tavoli nuovi
        m2 = [[0] * sala.W for _ in range(sala.H)]
        mE = [[0] * sala.W for _ in range(sala.H)]
        for c in forme:
            sala.marca_fisso(m2, c, sala.sedie_cm)
            sala.marca_fisso(mE, c, sala.sedie_cm + B * sala.griglia_cm)
        cache[chiave] = (sala.prefissi(m2), sala.prefissi(mE), m2, mE)
    return cache[chiave]


def _posizioni(sala: SalaLibera, k: int, pezzi: list[dict], sedie_min: int, dati: dict, conflitti: bool):
    """Tutte le posizioni (a 0° o 90°) di una fila nuova di k quadrati che rispettano le regole rispetto a muri, cose
    vietate e tavoli fissi; con conflitti=False anche rispetto ai `pezzi` (che restano), con conflitti=True i pezzi non
    contano ma per ogni posizione si dice quali danno fastidio. Restituisce [(fila, posti, pezzi in conflitto)]."""
    W, H, g = sala.W, sala.H, sala.griglia_cm
    L, S, _ = misure_celle(sala)
    B, occ1 = spazi(sala, "accesso")
    occ2 = [r[:] for r in sala._tavoli_senza_strade]       # niente strade riservate: conta la raggiungibilità vera
    occE = [r[:] for r in occ1]
    occA = [r[:] for r in sala.occ_cammino]
    imp = {str(t["id"]): _impronte(sala, t, B) for t in pezzi}
    if not conflitti:
        for t in pezzi:
            _, _, m2, mE = imp[str(t["id"])]
            for j in range(H):
                r2, rE, rA, a2, aE = occ2[j], occE[j], occA[j], m2[j], mE[j]
                for i in range(W):
                    if a2[i]:
                        r2[i] = 1
                        rA[i] = 1
                    if aE[i]:
                        rE[i] = 1
    p2, pE, pA = sala.prefissi(occ2), sala.prefissi(occE), sala.prefissi(occA)
    massimo = posti_regola(dati, k)
    out = []
    for vert in (False, True):
        w, h = (L, k * L) if vert else (k * L, L)
        _, lati = corpo_e_lati(k, vert, L, S)
        for j in range(H - h + 1):
            for i in range(W - w + 1):
                cb = (i, j, i + w, j + h)
                if not libero_box(p2, W, H, *cb) or not _libero_fuori(pE, W, H, _allarga(cb, B)):
                    continue
                f = {"k": k, "vert": vert, "x": i, "y": j, "sedie": {"a": [0] * k, "b": [0] * k, "testa": 0, "coda": 0}}
                for lato, q, dx, dy, ww, hh in lati:
                    z = (i + dx, j + dy, i + dx + ww, j + dy + hh)
                    if libero_box(p2, W, H, *z) and _libero_fuori(pE, W, H, _allarga(z, B)):
                        _metti(f["sedie"], lato, q, 1)
                n = posti_pezzo(f, 0, k - 1)
                if n < sedie_min:
                    continue
                _, zs = scatole_fila(sala, f)
                bb = (min(b[0] for b in [cb] + zs), min(b[1] for b in [cb] + zs), max(b[2] for b in [cb] + zs),
                      max(b[3] for b in [cb] + zs))
                if not _libero_fuori(pE, W, H, _allarga(bb, B)):
                    continue
                accessi = [(lato, z) for lato, z in zone_accesso(sala, f).items() if libero_box(pA, W, H, *z)]
                if not accessi:
                    continue
                C = set()
                if conflitti:
                    for tid, (q2, qE, _, _) in imp.items():
                        if any(not libero_box(q2, W, H, *b) for b in [cb] + zs) or not _libero_fuori(qE, W, H, _allarga(bb, B)):
                            C.add(tid)
                    def extra(z):
                        return {tid for tid, (q2, _, _, _) in imp.items() if tid not in C and not libero_box(q2, W, H, *z)}
                    lato, z = min(accessi, key=lambda a: len(extra(a[1])))
                    C |= extra(z)
                else:
                    lato = accessi[0][0]
                f["accesso"] = lato
                out.append((f, min(n, massimo), frozenset(C)))
    return out


def _fila_in_pezzo(sala: SalaLibera, f: dict, tid: str, posti: int, da: dict) -> dict:
    """Una fila nuova (in celle) come pezzo della piantina (blocco a 0°, unità del disegno), con le sue sedie."""
    g, cpu = sala.griglia_cm, sala.cpu
    L, _, _ = misure_celle(sala)
    w, h = (L, f["k"] * L) if f["vert"] else (f["k"] * L, L)
    t = {"id": tid, "tipo": "blocco" if f["k"] > 1 else "quadrato", "x": (f["x"] + w / 2) * g / cpu,
         "y": (f["y"] + h / 2) * g / cpu, "rot": 0, "posti": posti, "fisso": False, "separabile": False,
         "note": "tavolo nuovo della disposizione libera", "spazio_u": 0}
    if f["k"] > 1:
        t.update(moduli=f["k"], verso="verticale" if f["vert"] else "orizzontale")
    t["_libera"] = {"stato": "nuovo", "da": dict(da), "fila": copy.deepcopy(f), "x_cm": f["x"] * g, "y_cm": f["y"] * g,
                    "larghezza_cm": w * g, "altezza_cm": h * g}
    return t


def _accorcia(dati: dict, t: dict, verso_x: float, verso_y: float) -> tuple[dict | None, str]:
    """Il pezzo t senza il quadrato all'estremità più vicina al punto (verso_x, verso_y) in unità: (pezzo rimasto o
    None, quale estremità). Resta dov'era, più corto; posti: la regola, mai più di quelli che aveva."""
    k = _moduli(t)
    if k <= 1:
        return None, ""
    a = math.radians(float(t.get("rot") or 0))
    ax, ay = (math.cos(a), math.sin(a)) if t.get("verso") == "orizzontale" else (-math.sin(a), math.cos(a))
    s = 1 if (verso_x - float(t["x"])) * ax + (verso_y - float(t["y"])) * ay >= 0 else -1
    passo = 32 / 2                             # quadrati accostati: lo spazio del disegno è solo grafico
    r = copy.deepcopy(t)
    r["x"], r["y"] = float(t["x"]) - s * ax * passo, float(t["y"]) - s * ay * passo
    if k - 1 == 1:
        r["tipo"] = "quadrato"
        for c in ("moduli", "verso", "separabile"):
            r.pop(c, None)
    else:
        r["moduli"] = k - 1
    # resta dov'era: la regola, mai più di prima; senza sedie in testa (posti = 2k, i 20-24) 2 per quadrato
    senza_testa = int(t.get("posti") or 0) == 2 * k
    r["posti"] = 2 * (k - 1) if senza_testa else min(posti_regola(dati, k - 1), int(t.get("posti") or 0))
    return r, ("in fondo" if s > 0 else "in testa")


def _provenienza(t: dict) -> dict:
    return dict((t.get("_libera") or {}).get("da") or {str(t["id"]): _moduli(t)})


def _regioni(sala: SalaLibera, pezzi: list[dict]) -> list[tuple[str, list]]:
    """Per la raggiungibilità: corpo di ogni pezzo (riquadro in celle) e, per i tavoli nuovi, le zone delle sedie."""
    out = []
    for t in pezzi:
        info = t.get("_libera") or {}
        if info.get("stato") == "nuovo":
            cb, zs = scatole_fila(sala, info["fila"])
            out.append((str(t["id"]), [cb] + zs))
        else:
            out.append((str(t["id"]), [_box_corpo(sala, t)]))
    return out


def _vicino(sala: SalaLibera, f: dict, pezzi: list[dict], dati: dict) -> str:
    """Un riferimento per il personale: il tavolo (fisso o mobile) più vicino al centro della fila nuova."""
    g, cpu = sala.griglia_cm, sala.cpu
    L, _, _ = misure_celle(sala)
    w, h = (L, f["k"] * L) if f["vert"] else (f["k"] * L, L)
    cx, cy = (f["x"] + w / 2) * g / cpu, (f["y"] + h / 2) * g / cpu
    tutti = [t for t in dati["tavoli"] if t.get("fisso")] + pezzi
    t = min(tutti, key=lambda t: math.hypot(float(t["x"]) - cx, float(t["y"]) - cy))
    return str(t["id"])


def proponi_mosse(sala: SalaLibera, var: dict, coperti: int, n_max: int = MOSSE_DA_PROVARE) -> list[dict]:
    """Le disposizioni nuove (varianti) con un tavolo da k quadrati per `coperti`, dalla disposizione `var`: le migliori
    `n_max` per (pezzi toccati, posti persi, distanza dei quadrati portati). Vedi il docstring del modulo."""
    dati = var["dati"]
    mob = _mobili(dati)
    pezzi = list(mob.values())
    # il tavolo più piccolo che ha i posti; per un gruppo più grande di ogni tavolo nuovo, il più grande: serve a chi
    # deve lasciare un tavolo fisso grande (il lungo, il tondo) al nuovo arrivato
    k = next((k for k in range(1, sala.k_max + 1) if posti_regola(dati, k) >= coperti), sala.k_max)
    coperti = min(coperti, posti_regola(dati, k))
    g, cpu = sala.griglia_cm, sala.cpu
    L, _, _ = misure_celle(sala)
    base = sala.irraggiungibili(_regioni(sala, pezzi))
    posti_prima = sum(int(t.get("posti") or 0) for t in pezzi)
    migliori: dict[frozenset, tuple] = {}
    for f, n, C in _posizioni(sala, k, pezzi, coperti, dati, conflitti=True):
        liberi = sum(_moduli(mob[c]) for c in C)
        if liberi > k + 4 or k - liberi > 2:
            continue
        w, h = (L, f["k"] * L) if f["vert"] else (f["k"] * L, L)
        cx, cy = (f["x"] + w / 2) * g / cpu, (f["y"] + h / 2) * g / cpu
        chiave = (-n, sum(math.hypot(float(mob[c]["x"]) - cx, float(mob[c]["y"]) - cy) for c in C))
        if C not in migliori or chiave < migliori[C][0]:
            migliori[C] = (chiave, f, n, cx, cy)
    proposte = []
    for C, (_, f, n, cx, cy) in migliori.items():
        restano = [t for t in pezzi if str(t["id"]) not in C]
        quadrati = [o for c in sorted(C) for o, q in _provenienza(mob[c]).items() for _ in range(q)]
        mosse = [f"smonta il {c}" + (f" ({_moduli(mob[c])} quadrati)" if _moduli(mob[c]) > 1 else "") for c in sorted(C)]
        tocca = len(C)
        while len(quadrati) < k:                   # stacca un quadrato dal pezzo più vicino che ne ha di più
            cand = [t for t in restano if _moduli(t) > 1 and not (t.get("_libera") or {}).get("stato") == "nuovo"]
            if not cand:
                break
            t = min(cand, key=lambda t: math.hypot(float(t["x"]) - cx, float(t["y"]) - cy))
            r, dove = _accorcia(dati, t, cx, cy)
            prov = _provenienza(t)
            o = next(iter(prov))
            prov[o] -= 1
            if not prov[o]:
                del prov[o]
            r["_libera"] = {"stato": "accorciato", "da": prov, "prima": str(t["id"])}
            restano = [r if x is t else x for x in restano]
            quadrati.append(o)
            mosse.append(f"stacca il quadrato {dove} al {t['id']} (resta da {_moduli(r)}, {r['posti']} posti)")
            tocca += 1
        if len(quadrati) < k:
            continue
        n_nuovi = sum(1 for t in pezzi if str(t["id"]).startswith("N")) + 1
        nid = f"N{n_nuovi}"
        da = {}
        for o in quadrati[:k]:
            da[o] = da.get(o, 0) + 1
        nuovo = _fila_in_pezzo(sala, f, nid, n, da)
        avanzo = quadrati[k:]
        layout = restano + [nuovo]
        mosse.append(f"componi il {nid}: {k} quadrati ({'+'.join(f'{q}×{o}' if q > 1 else o for o, q in da.items())}), "
                     f"{'in verticale' if f['vert'] else 'in orizzontale'}, {n} posti, vicino al "
                     f"{_vicino(sala, f, restano, dati)} (angolo a {round(f['x'] * g)}, {round(f['y'] * g)} cm)")
        messi = _rimetti(sala, dati, layout, avanzo, (cx, cy), n_nuovi + 1, restano) if avanzo else []
        if messi is None:
            continue
        for t, testo in messi:
            layout.append(t)
            mosse.append(testo)
            tocca += 1
        # raggiungibilità sulla disposizione effettiva, mai peggio del disegno: nessun tavolo o porta che si raggiungeva
        # diventa irraggiungibile; i tavoli nuovi si raggiungono, salvo che stiano dove già i pezzi smontati non si
        # raggiungevano col personale largo 60 cm (la parte destra della sala, anche col disegno)
        nuovi = {str(t["id"]) for t in layout if (t.get("_libera") or {}).get("stato") == "nuovo"}
        dopo = sala.irraggiungibili(_regioni(sala, layout))
        if not dopo - base <= (nuovi if C <= base else set()):
            continue
        posti_dopo = sum(int(t.get("posti") or 0) for t in layout)
        d = copy.deepcopy(dati)
        d["tavoli"] = [t for t in d["tavoli"] if str(t["id"]) not in mob] + copy.deepcopy(layout)
        proposte.append(((tocca, posti_prima - posti_dopo), {"nome": f"{var['nome']} + {nid}", "dati": d,
                                                             "mosse": var.get("mosse", []) + mosse}))
    proposte.sort(key=lambda p: p[0])
    return [p[1] for p in proposte[:n_max]]


# ---------------------------------------------------------------------------- mosse "attacca a un pezzo fermo"

DISTANZA_REGOLA_CM = 140      # fra i corpi di due tavoli: 50 cm di sedie + 40 cm fra le zone + 50 cm di sedie
SPOSTAMENTI_CM = (0, 25, -25, 50, -50, 75, -75, 100, -100)
ROTAZIONI = (0, 15, -15)


def _d_forme(a: Forma, b: Forma) -> float:
    """Distanza fra due forme (poligoni convessi, cerchi, muri con mezzo spessore), 0 se si toccano o si coprono."""
    from .sala_libera import dentro, dist_punto_seg
    if a.tipo != "poli":
        a, b = b, a
    if a.tipo != "poli":
        return 0.0
    pa = list(a.punti)
    sa = [(pa[i], pa[(i + 1) % len(pa)]) for i in range(len(pa))]
    if b.tipo == "cerchio":
        c = b.punti[0]
        if dentro(c, pa):
            return 0.0
        return max(0.0, min(dist_punto_seg(c, *s) for s in sa) - b.r)
    pb = list(b.punti)
    sb = [(pb[i], pb[i + 1]) for i in range(len(pb) - 1)] if b.tipo == "linea" else \
        [(pb[i], pb[(i + 1) % len(pb)]) for i in range(len(pb))]
    if b.tipo == "poli" and (any(dentro(q, pb) for q in pa) or any(dentro(q, pa) for q in pb)):
        return 0.0
    if any(_tagliano(s, u) for s in sa for u in sb):
        return 0.0
    d = min(min(dist_punto_seg(q, *u) for q in pa for u in sb), min(dist_punto_seg(q, *s) for q in pb for s in sa))
    return max(0.0, d - (b.r if b.tipo == "linea" else 0.0))


def _oltre_un_muro(sala: SalaLibera, a: Forma, b: Forma) -> bool:
    """Fra i centri delle due forme passa un muro interno (le zone delle sedie non passano i muri)."""
    ca = ((a.bbox()[0] + a.bbox()[2]) / 2, (a.bbox()[1] + a.bbox()[3]) / 2)
    cb = ((b.bbox()[0] + b.bbox()[2]) / 2, (b.bbox()[1] + b.bbox()[3]) / 2)
    return any(_tagliano((ca, cb), (m.punti[i], m.punti[i + 1])) for m in sala.muri for i in range(len(m.punti) - 1))


def _tagliano(s, u) -> bool:
    (a, b), (c, d) = s, u
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (o(a, b, c) > 0) != (o(a, b, d) > 0) and (o(c, d, a) > 0) != (o(c, d, b) > 0)


def _asse(t: dict) -> tuple[tuple[float, float], tuple[float, float]]:
    a = math.radians(float(t.get("rot") or 0))
    ax = (math.cos(a), math.sin(a)) if t.get("verso") == "orizzontale" or t["tipo"] == "quadrato" else (-math.sin(a), math.cos(a))
    return ax, (-ax[1], ax[0])


def allunga(t: dict, in_testa: int, in_coda: int, sposta_asse_cm: float = 0.0, sposta_lato_cm: float = 0.0,
            ruota: float = 0.0, cpu: float = 2.5, verso_singolo: str = "orizzontale") -> dict:
    """Il pezzo t allungato di `in_testa` quadrati dalla parte della testa e `in_coda` da quella della coda, con la sua
    rotazione (più `ruota` gradi) e spostato di poco (cm, lungo l'asse e di lato). Un quadrato singolo diventa un blocco
    nel verso `verso_singolo`."""
    r = copy.deepcopy(t)
    if t["tipo"] == "quadrato":
        r.update(tipo="blocco", verso=verso_singolo, separabile=True)
        r.setdefault("rot", t.get("rot") or 0)
    k = _moduli(t) + in_testa + in_coda
    (ax, ay), (px, py) = _asse(r)
    passo = 32                                  # il quadrato aggiunto a filo, a 32 u dal precedente
    dx = ax * (in_coda - in_testa) * passo / 2 + (ax * sposta_asse_cm + px * sposta_lato_cm) / cpu
    dy = ay * (in_coda - in_testa) * passo / 2 + (ay * sposta_asse_cm + py * sposta_lato_cm) / cpu
    r.update(moduli=k, x=float(t["x"]) + dx, y=float(t["y"]) + dy, rot=float(t.get("rot") or 0) + ruota)
    return r


def _zone_sedie_pezzo(sala: SalaLibera, t: dict) -> list[Forma]:
    """Le zone delle sedie (50 cm) di un pezzo: una per lato lungo di ogni quadrato, più testa e coda (in cm)."""
    k = _moduli(t)
    (ax, ay), (px, py) = _asse(t)
    cx, cy = float(t["x"]) * sala.cpu, float(t["y"]) * sala.cpu
    lato, passo, sd = sala.lato_cm, (32 + GAP_U) * sala.cpu, sala.sedie_cm
    L = k * lato + (k - 1) * GAP_U * sala.cpu
    out = []
    def rett(c0, c1, w_asse, w_lato):
        pts = [(c0 + ax * sa + px * sl, c1 + ay * sa + py * sl) for sa, sl in
               ((-w_asse / 2, -w_lato / 2), (w_asse / 2, -w_lato / 2), (w_asse / 2, w_lato / 2), (-w_asse / 2, w_lato / 2))]
        return Forma("sedia", "poli", tuple(pts))
    for q in range(k):
        off = -L / 2 + lato / 2 + q * passo
        for s in (-1, 1):
            out.append(rett(cx + ax * off + px * s * (lato + sd) / 2, cy + ay * off + py * s * (lato + sd) / 2, lato, sd))
    for s in (-1, 1):
        out.append(rett(cx + ax * s * (L + sd) / 2, cy + ay * s * (L + sd) / 2, sd, lato))
    return out


def _zone_accesso_pezzo(sala: SalaLibera, t: dict) -> list[Forma]:
    """Le quattro zone d'accesso di un pezzo (anche ruotato): una fascia di 60 cm oltre le sedie (50 cm), lungo i due
    lati lunghi e le due teste, come per i tavoli nuovi (`zone_accesso`)."""
    k = _moduli(t)
    (ax, ay), (px, py) = _asse(t)
    cx, cy = float(t["x"]) * sala.cpu, float(t["y"]) * sala.cpu
    lato, sd, A = sala.lato_cm, sala.sedie_cm, sala.corridoio_cm
    L = k * lato + (k - 1) * GAP_U * sala.cpu
    out = []

    def rett(c0, c1, w_asse, w_lato):
        return Forma("accesso", "poli", tuple((c0 + ax * sa + px * sl, c1 + ay * sa + py * sl) for sa, sl in
                                              ((-w_asse / 2, -w_lato / 2), (w_asse / 2, -w_lato / 2),
                                               (w_asse / 2, w_lato / 2), (-w_asse / 2, w_lato / 2))))
    for s in (-1, 1):
        off = lato / 2 + sd + A / 2
        out.append(rett(cx + px * s * off, cy + py * s * off, L, A))
        off = L / 2 + sd + A / 2
        out.append(rett(cx + ax * s * off, cy + ay * s * off, A, lato))
    return out


def ha_accesso(sala: SalaLibera, t: dict, altri: list[dict]) -> bool:
    """Il pezzo ha almeno un lato d'accesso: la fascia di 60 cm oltre le sedie dentro la sala, fuori da muri e cose
    vietate e fuori dalle zone delle sedie (50 cm) degli altri tavoli, fissi e mobili."""
    from .sala_libera import dentro
    corpi = [f.corpo for f in sala.fissi] + [corpo_disegnato(sala, x) for x in altri if str(x["id"]) != str(t["id"])]
    for z in _zone_accesso_pezzo(sala, t):
        if all(dentro(q, sala.stanza) for q in z.punti) and all(_d_forme(z, m) > 0 for m in sala.muri) and \
                all(_d_forme(z, f) > 0 for f in sala.vietate) and all(_d_forme(z, c) >= sala.sedie_cm for c in corpi):
            return True
    return False


def controlla_pezzo(sala: SalaLibera, nuovo: dict, prima: dict | None, altri: list[dict],
                    altri_prima: list[dict] | None = None) -> tuple[list, int]:
    """Le regole per un pezzo allungato o spostato rispetto al resto della sala: corpo dentro la sala, fuori da muri e
    cose vietate; dagli altri tavoli (fissi e mobili) 140 cm fra i corpi (50 + 40 + 50), ma dove il disegno aveva già
    meno spazio basta non peggiorare la distanza che c'era; le sedie dove ci stanno davvero. Restituisce
    ([(regola, contro cosa, quanti cm mancano)], sedie che ci stanno)."""
    from .sala_libera import dentro, dist_punto_seg
    corpo = corpo_disegnato(sala, nuovo)
    bb = corpo.bbox()

    def vicino(f, m):
        b = f.bbox()
        return max(0.0, b[0] - bb[2], bb[0] - b[2]) < m and max(0.0, b[1] - bb[3], bb[1] - b[3]) < m
    viol = []
    st = sala.stanza
    seg_st = [(st[i], st[(i + 1) % len(st)]) for i in range(len(st))]
    for q in corpo.punti:
        if not dentro(q, st):
            viol.append(("dentro la sala", "muro perimetrale", round(min(dist_punto_seg(q, *s) for s in seg_st), 1)))
            break
    muri = [m for m in sala.muri if vicino(m, 120)]
    vietate = [f for f in sala.vietate if vicino(f, 120)]
    for m in muri:
        if _d_forme(corpo, m) <= 0:
            viol.append(("sul muro", m.nome, None))
    for f in vietate:
        if _d_forme(corpo, f) <= 0:
            viol.append(("sulle cose vietate", f.nome, None))
    corpo_prima = corpo_disegnato(sala, prima) if prima is not None else None
    ostacoli = [(f.id, f.corpo) for f in sala.fissi] + [(str(t["id"]), corpo_disegnato(sala, t)) for t in altri]
    ostacoli = [(o, c) for o, c in ostacoli if vicino(c, DISTANZA_REGOLA_CM + 10) and not _oltre_un_muro(sala, corpo, c)]
    for oid, oc in ostacoli:
        d = _d_forme(corpo, oc)
        serve = DISTANZA_REGOLA_CM
        if corpo_prima is not None:
            serve = min(serve, _d_forme(corpo_prima, oc))
        if d < serve - 1.0:
            viol.append(("140 cm fra i tavoli (o non peggio del disegno)", oid, round(serve - d, 1)))
    sedie = 0
    sedie_bloccate = []
    if viol:                                    # le sedie si contano solo per un corpo già a posto
        return viol, 0
    # il lato d'accesso da 60 cm, come per i tavoli nuovi; dove il disegno non l'aveva, basta non peggiorare
    # il confronto col disegno: il pezzo di prima con i suoi vicini di prima (anche quelli che danno un quadrato)
    if not ha_accesso(sala, nuovo, altri) and (prima is None or ha_accesso(sala, prima, altri_prima or altri)):
        viol.append(("lato d'accesso da 60 cm oltre le sedie", "nessun lato libero", None))
        return viol, 0
    for z in _zone_sedie_pezzo(sala, nuovo):
        chi = [m.nome for m in muri if _d_forme(z, m) <= 0] + [f.nome for f in vietate if _d_forme(z, f) <= 0] + \
            [o for o, oc in ostacoli if _d_forme(z, oc) <= 0]
        if not all(dentro(q, st) for q in z.punti):
            chi.append("muro perimetrale")
        sedie += not chi
        for o in chi:                           # quanto manca: 50 cm di sedia meno la distanza del corpo dall'ostacolo
            oc = next((c for n, c in ostacoli if n == o), None) or next((f for f in list(muri) + list(vietate) if f.nome == o), None)
            manca = round(sala.sedie_cm - _d_forme(corpo, oc), 1) if oc is not None else None
            if not any(v[0] == "sedia" and v[1] == o for v in sedie_bloccate):
                sedie_bloccate.append(("sedia", o, manca))
    nuovo["_sedie_bloccate"] = sedie_bloccate
    return viol, sedie


def _donatori(sala: SalaLibera, dati: dict, resto: list[dict], quanti: int, vicino: tuple[float, float],
              preferiti: list[str]) -> tuple[list[dict], list[str], list[str]] | None:
    """Prende `quanti` quadrati dai pezzi `resto`: prima dai `preferiti` (quelli che danno fastidio), poi dai più
    vicini; un singolo si toglie, un blocco separabile si accorcia dall'estremità più vicina. (resto aggiornato,
    provenienze dei quadrati, istruzioni) o None se non bastano."""
    resto = list(resto)
    presi, mosse = [], []
    for _ in range(quanti):
        cand = [t for t in resto if (t["tipo"] == "quadrato" or t.get("separabile")) and
                (t.get("_libera") or {}).get("stato") not in ("nuovo", "allungato")]
        if not cand:
            return None
        t = min(cand, key=lambda t: (str(t["id"]) not in preferiti, _moduli(t) > 1,
                                     math.hypot(float(t["x"]) - vicino[0], float(t["y"]) - vicino[1])))
        prov = _provenienza(t)
        o = next(iter(prov))
        if _moduli(t) == 1:
            resto.remove(t)
            mosse.append(f"prendi il {t['id']}")
        else:
            r, dove = _accorcia(dati, t, *vicino)
            prov[o] -= 1
            if not prov[o]:
                del prov[o]
            r["_libera"] = {"stato": "accorciato", "da": prov, "prima": str(t["id"])}
            resto = [r if x is t else x for x in resto]
            mosse.append(f"dividi il {t['id']} e prendi il quadrato {dove} (il {t['id']} resta da {_moduli(r)}, {r['posti']} posti)")
        presi.append(o)
    return resto, presi, mosse


def schemi_allungo(dati: dict, k: int, sala: SalaLibera) -> list[tuple[dict, int, int, str]]:
    """Gli allunghi che portano un pezzo mobile a k quadrati: (pezzo, in testa, in coda, verso se era un singolo)."""
    out = []
    for t in _mobili(dati).values():
        km = _moduli(t)
        if km >= k or (t.get("_libera") or {}).get("stato") == "nuovo":
            continue
        n = k - km
        if t["tipo"] == "quadrato" and n > 1:      # un singolo con 2 o più quadrati attaccati è un tavolo nuovo
            continue
        versi =("orizzontale", "verticale") if t["tipo"] == "quadrato" else (t.get("verso"),)
        for v in versi:
            for testa in range(n + 1):
                out.append((t, testa, n - testa, v))
    return out


def proponi_attacchi(sala: SalaLibera, var: dict, coperti: int, n_max: int = MOSSE_DA_PROVARE,
                     diagnosi: list | None = None) -> list[dict]:
    """Mosse "attacca a un pezzo fermo": uno o due quadrati staccati da pezzi separabili (o singoli presi) e attaccati
    in testa o in coda a un pezzo che resta dov'è con la sua rotazione; se non basta, lo stesso pezzo spostato fino a
    1 m o ruotato di 15 gradi. Il pezzo allungato ha i posti della regola (4 quadrati = 10) se le sedie ci stanno.
    Le varianti ammesse, le migliori `n_max`; in `diagnosi` per ogni schema il caso migliore e cosa lo blocca."""
    cache = sala.__dict__.setdefault("_cache_attacchi", {})
    chiave = (var["nome"], tuple(var.get("mosse") or []), coperti, n_max)
    if diagnosi is None and chiave in cache:
        return cache[chiave]
    dati = var["dati"]
    mob = _mobili(dati)
    k = next((k for k in range(2, sala.k_max + 1) if posti_regola(dati, k) >= coperti), None)
    if k is None:
        return []
    base = sala.irraggiungibili(_regioni(sala, list(mob.values())))
    proposte = []
    for t, testa, coda, verso in schemi_allungo(dati, k, sala):
        migliore = None

        def prova(sa, sl, ruota):
            nonlocal migliore
            if abs(sa) + abs(sl) > 100 or abs(ruota) > 15:
                return False
            nuovo = allunga(t, testa, coda, sa, sl, ruota, sala.cpu, verso)
            altri = [x for x in mob.values() if x is not t]
            viol, sedie = controlla_pezzo(sala, nuovo, t, altri)
            # chi dà fastidio e può dare un quadrato lo dà (così si libera lo spazio): poi si ricontrolla
            fastidio = [o for r, o, _ in viol if o in mob and o != str(t["id"])]
            dona = _donatori(sala, dati, altri, testa + coda, (float(nuovo["x"]), float(nuovo["y"])), fastidio)
            if dona is None:
                return False
            resto, presi, mosse = dona
            viol, sedie = controlla_pezzo(sala, nuovo, t, resto, altri)
            posti = min(posti_regola(dati, k), sedie)
            if posti < coperti and not viol:
                viol = [(f"sedie che ci stanno: {sedie} su {2 * k + 2}", "", None)] + nuovo.get("_sedie_bloccate", [])
            nuovo.pop("_sedie_bloccate", None)
            numeri = [v[2] for v in viol if v[2] is not None]     # quanti cm mancano (le sedie: la più vicina)
            costo = (len(viol), max(numeri) if numeri else (999 if viol else 0),
                     abs(sa) + abs(sl) + abs(ruota), len(mosse))
            if migliore is None or costo < migliore[0]:
                migliore = (costo, nuovo, resto, presi, mosse, viol, posti, sa, sl, ruota)
            return not viol

        trovata = any(prova(sa, sl, ruota) for ruota in ROTAZIONI for sa in SPOSTAMENTI_CM for sl in SPOSTAMENTI_CM)
        if not trovata and migliore is not None and migliore[0][1] <= 30:     # vicino: si cerca di fino (5 cm, 2°)
            _, _, _, _, _, _, _, sa0, sl0, r0 = migliore
            trovata = any(prova(sa0 + da, sl0 + dl, r0 + dr) for dr in (0, 2, -2, 4, -4, 6, -6)
                          for da in range(-25, 30, 5) for dl in range(-25, 30, 5))
        if migliore is None:
            continue
        _, nuovo, resto, presi, mosse, viol, posti, sa, sl, ruota = migliore
        nome = f"{t['id']} + {testa + coda} in {'testa' if testa and not coda else 'coda' if coda and not testa else 'testa e coda'}"
        spost = ("" if not (sa or sl or ruota) else
                 f", spostato di {abs(sa)} cm lungo l'asse e {abs(sl)} cm di lato" + (f", ruotato di {ruota}°" if ruota else ""))
        if diagnosi is not None:
            diagnosi.append({"schema": nome, "verso": verso, "spostamento": spost.lstrip(", ") or "fermo",
                             "donatori": mosse, "blocchi": viol, "posti": posti})
        if viol:
            continue
        da = _provenienza(t)
        for o in presi:
            da[o] = da.get(o, 0) + 1
        nuovo["posti"] = posti
        nuovo["_libera"] = {"stato": "allungato", "da": da, "prima": str(t["id"])}
        layout = resto + [nuovo]
        dopo = sala.irraggiungibili(_regioni(sala, layout))
        if not dopo <= base:
            if diagnosi is not None:
                diagnosi[-1]["blocchi"] = [("raggiungibilità", ", ".join(sorted(dopo - base)), None)]
            continue
        testo = (f"attacca {testa + coda} {'quadrati' if testa + coda > 1 else 'quadrato'} "
                 f"{'in testa' if testa and not coda else 'in coda' if coda and not testa else 'in testa e in coda'} "
                 f"al {t['id']}{spost}: diventa un tavolo da {k} quadrati e {posti} posti")
        d = copy.deepcopy(dati)
        d["tavoli"] = [x for x in d["tavoli"] if str(x["id"]) not in mob] + copy.deepcopy(layout)
        proposte.append(((len(mosse) + 1 + bool(spost), abs(sa) + abs(sl)),
                         {"nome": f"{var['nome']} + {t['id']} allungato", "dati": d,
                          "mosse": var.get("mosse", []) + mosse + [testo]}))
    proposte.sort(key=lambda p: p[0])
    cache[chiave] = [p[1] for p in proposte[:n_max]]
    return cache[chiave]


def proponi_combinazioni(sala: SalaLibera, var: dict, coperti: int, n_max: int = MOSSE_DA_PROVARE,
                         diagnosi: list | None = None) -> list[dict]:
    """Combinazioni di due o tre attacchi nella stessa disposizione: prima il pezzo per il nuovo gruppo, poi gli
    allungamenti che rifanno i pezzi da 8 e da 6 posti persi o occupati (da 2 a 3 quadrati, un singolo a un altro
    singolo), ognuno controllato con le regole rispetto alla disposizione già cambiata dal primo."""
    out = []
    for a in proponi_attacchi(sala, var, coperti, n_max=3):
        for c2 in (8, 6):
            d2 = [] if diagnosi is not None else None
            for b in proponi_attacchi(sala, a, c2, n_max=3, diagnosi=d2):
                out.append(b)
                out += proponi_attacchi(sala, b, 8, n_max=2)     # il terzo: solo un altro pezzo da 8
            if diagnosi is not None:
                diagnosi.append({"prima": a["mosse"][len(var.get("mosse") or []):], "seconda_per": c2, "schemi": d2})
    visti, uniche = set(), []
    for v in out:
        firma = tuple(sorted(v["mosse"]))
        if firma not in visti:
            visti.add(firma)
            uniche.append(v)
    uniche.sort(key=lambda v: -sum(int(t.get("posti") or 0) for t in _mobili(v["dati"]).values()))
    return uniche[:n_max]


def _rimetti(sala: SalaLibera, dati: dict, layout: list[dict], avanzo: list[str], vicino: tuple[float, float],
             primo: int, restano: list[dict]) -> list[tuple[dict, str]] | None:
    """I quadrati che avanzano diventano tavoli nuovi dove le regole lo permettono, con il resto al suo posto: un pezzo
    solo se ci sta, altrimenti pezzi da 2 (e uno da 1). Restituisce [(pezzo, istruzione)] o None se non ci stanno."""
    g, cpu = sala.griglia_cm, sala.cpu
    tagli = ([([len(avanzo)], 2)] if len(avanzo) <= sala.k_max else []) +         [([2] * (len(avanzo) // 2) + [1] * (len(avanzo) % 2), 2), ([1] * len(avanzo), 1)]
    for taglio, sedie_min in tagli:               # da ultimo, quadrati da soli anche con una sedia sola (contro un muro)
        out, lay, resto, ok = [], list(layout), list(avanzo), True
        for n, ka in enumerate(taglio):
            pos = _posizioni(sala, ka, lay, min(sedie_min, posti_regola(dati, ka)), dati, conflitti=False)
            if not pos:
                ok = False
                break
            fa, na, _ = max(pos, key=lambda p: (p[1], -math.hypot(p[0]["x"] * g / cpu - vicino[0], p[0]["y"] * g / cpu - vicino[1])))
            da2 = {}
            for o in resto[:ka]:
                da2[o] = da2.get(o, 0) + 1
            resto = resto[ka:]
            nid = f"N{primo + n}"
            pz = _fila_in_pezzo(sala, fa, nid, na, da2)
            lay.append(pz)
            out.append((pz, f"con {ka} {'quadrati' if ka > 1 else 'quadrato'} che {'avanzano' if ka > 1 else 'avanza'} "
                            f"metti il {nid} ({na} posti) vicino al {_vicino(sala, fa, restano, dati)} "
                            f"(angolo a {round(fa['x'] * g)}, {round(fa['y'] * g)} cm)"))
        if ok:
            return out
    return None


def _tavoli_per_prenotazione(ist: Istanza, mod, piano: dict) -> dict[str, str]:
    _, ass, _ = _estrai(ist, mod, piano)
    return {str(r["id"]): str(r["tavolo"]) + (f" ({r['quadrati'][0]}-{r['quadrati'][1]})" if r.get("quadrati") else "")
            for r in ass}


def accetta_in_ordine_varianti(ist: Istanza, sala_cfg: dict, pren: dict, worker: int | None = None,
                               seed: int | None = None, log: bool = False,
                               avanzamento: Callable[[str], None] | None = None, mosse: bool = True) -> dict:
    """Ordine di arrivo sul disegno con le mosse proposte dal motore (vedi il docstring del modulo). Se le mosse hanno
    tolto qualcosa (prenotazioni o coperti) rispetto al solo disegno, si tiene il solo disegno."""
    sol = _accetta(ist, sala_cfg, pren, worker, seed, log, avanzamento, mosse)
    if mosse and sol["variante"]["mosse"]:
        say = avanzamento or (lambda _m: None)
        say("Riserva: la stessa serata col solo disegno, per non fare mai peggio del modo a tavoli fermi")
        ist0 = costruisci_istanza(sala_cfg, pren)
        rif = _accetta(ist0, sala_cfg, pren, worker, seed, log, None, False)
        def conta(s):
            return len(s["assegnazioni"]), sum(r["coperti"] for r in s["assegnazioni"])
        a, b = conta(sol), conta(rif)
        sol["variante"]["riserva"] = {"prenotazioni": b[0], "coperti": b[1]}
        if a[0] < b[0] or a[1] < b[1]:
            say(f"Le mosse danno {a[0]} prenotazioni e {a[1]} coperti, il disegno {b[0]} e {b[1]}: si tiene il disegno")
            rif["variante"]["riserva"] = {"scartate_mosse": sol["variante"]["mosse"], "prenotazioni": a[0], "coperti": a[1]}
            return rif
    return sol


PENALITA_CAMBIO = 100        # per prenotazione che cambia tavolo rispetto alla conferma: più di 10 posti vuoti
PENALITA_CAMBIO_PEZZO = 10   # stesso tavolo, altri quadrati del blocco


def penalizza_cambi(mod, conferme: dict[str, str], peso: int) -> list[tuple[str, int]]:
    """Aggiunge all'obiettivo della piantina finale una penalità per ogni prenotazione seduta a un tavolo diverso da
    quello dato alla conferma (e una piccola se resta allo stesso blocco ma su altri quadrati). [(variabile, peso)]."""
    proto = mod.m.proto
    n = []
    for (pid, ch), av in mod.a.items():
        conf = conferme.get(str(pid))
        if conf is None:
            continue
        u, _k = mod.unita[ch]
        ora = str(u.tavolo) + (f" ({u.quadrati[0]}-{u.quadrati[1]})" if u.quadrati is not None else "")
        if str(u.tavolo) != conf.split(" (")[0]:
            w = peso
        elif conf != ora:
            w = PENALITA_CAMBIO_PEZZO
        else:
            continue
        proto.objective.vars.append(av.index)
        proto.objective.coeffs.append(w)
        n.append((av.name, w))
    return n


TEMPO_STABILE_S = 1.5         # per conferma: il tavolo più piccolo che basta e nessun cambio inutile


def _stabilizza(ist_v: Istanza, accettate: list, pr, tavoli_ora: dict, mod, piano: dict, dati: dict, worker, seed):
    """Dopo una conferma: lo stesso modello con un obiettivo che mette il nuovo arrivato al tavolo più piccolo che
    basta (a parità, un pezzo del disegno) e lascia gli altri dove erano (100 per un tavolo diverso, 10 per altri
    quadrati dello stesso blocco). Partendo dal piano trovato, per pochi secondi; se non migliora resta quello."""
    mod2 = _costruisci(ist_v, accettate, "fissa", obiettivo="nessuno")
    cambiati = {str(t["id"]) for t in _mobili(dati).values() if (t.get("_libera") or {}).get("stato")}
    proto = mod2.m.proto
    for (pid, ch), av in mod2.a.items():
        u, _k = mod2.unita[ch]
        if str(pid) == str(pr.id):
            w = max(0, int(u.posti) - pr.coperti) * 2 + (1 if str(u.tavolo) in cambiati else 0)
        else:
            conf = tavoli_ora.get(str(pid))
            if conf is None:
                continue
            ora = str(u.tavolo) + (f" ({u.quadrati[0]}-{u.quadrati[1]})" if u.quadrati is not None else "")
            w = PENALITA_CAMBIO if str(u.tavolo) != conf.split(" (")[0] else (PENALITA_CAMBIO_PEZZO if ora != conf else 0)
        if w:
            proto.objective.vars.append(av.index)
            proto.objective.coeffs.append(w)
    stato, p2, _ = _risolvi_modello(mod2, TEMPO_STABILE_S, worker, seed, False, hint=piano)
    return (mod2, p2) if p2 is not None else (mod, piano)


def _accetta(ist: Istanza, sala_cfg: dict, pren: dict, worker, seed, log, avanzamento, con_mosse: bool,
             penalita_cambio: int = PENALITA_CAMBIO, stabile: bool = True) -> dict:
    from .modello_libero import sala_libera
    say = avanzamento or (lambda _m: None)
    t_inizio = time.perf_counter()
    sala = sala_libera(ist)
    dati = ist.piantina.dati
    vs = [{"nome": "disegno", "dati": dati, "mosse": []}]
    istanze = [ist]
    worker, seed = _parametri(ist, worker, seed)
    tempo_d = float(ist.sala.get("solver", {}).get("tempo_decisione_s", 60))
    politica = ist.cliente_accetta_proposta
    corrente = 0
    accettate: list[_Voce] = []
    rifiutate, registro = [], []
    piano, tavoli_ora = None, {}
    cap = max(Piantina(dati).capienza_massima, *(posti_regola(dati, k) for k in range(1, sala.k_max + 1)))
    per_mossa: dict[int, str] = {}
    mosse_fatte: dict[tuple, list[int]] = {}

    def istanza(v):
        while len(istanze) <= v:
            s2 = copy.deepcopy(sala_cfg)
            s2["piantina"] = _senza_interni(vs[len(istanze)]["dati"])
            istanze.append(costruisci_istanza(s2, pren))
        return istanze[v]

    def prova(kk, pr, v):
        """La richiesta nel turno kk con tutte le accettate, sulla variante v: (piano o None, stato, voce, modello)."""
        ist_v = istanza(v)
        voce = _Voce(pr, [(ist_v.turni[kk].inizio_min - pr.orario_min, ist_v.passo_turno(kk))], True)
        if _impossibile_per_conteggio(ist_v, accettate, pr, voce.opzioni[0][1]):
            return None, "CONTEGGIO", voce, None
        mod = _costruisci(ist_v, accettate + [voce], "fissa", obiettivo="nessuno")
        stato, nuovo, _ = _risolvi_modello(mod, tempo_d, worker, seed, log, hint=piano if v == corrente else None)
        return nuovo, stato, voce, mod

    def cerca(kk, pr, con_mosse_qui):
        """Disposizione corrente; con le mosse, quelle proposte dal motore: (variante, piano, voce, modello, esiti, decisi)."""
        nuovo, stato, voce, mod = prova(kk, pr, corrente)
        esiti = [f"{vs[corrente]['nome']} {'AMMISSIBILE' if nuovo is not None else stato}"]
        if nuovo is not None:
            return corrente, nuovo, voce, mod, esiti, True
        decisi = stato in ("INFEASIBLE", "CONTEGGIO")
        if con_mosse_qui:
            chiave = (corrente, pr.coperti)          # le mosse dipendono solo dalla disposizione e dai coperti
            if chiave not in mosse_fatte:
                mosse_fatte[chiave] = []
                for v in (proponi_attacchi(sala, vs[corrente], pr.coperti) +
                          proponi_combinazioni(sala, vs[corrente], pr.coperti) +
                          proponi_mosse(sala, vs[corrente], pr.coperti))[:3 * MOSSE_DA_PROVARE]:
                    vs.append(v)
                    mosse_fatte[chiave].append(len(vs) - 1)
            for n in mosse_fatte[chiave]:
                v = vs[n]
                nuovo, stato, voce, mod = prova(kk, pr, n)
                esiti.append(f"mossa {v['nome']} {'AMMISSIBILE' if nuovo is not None else stato}")
                if nuovo is not None:
                    return n, nuovo, voce, mod, esiti, True
                decisi = decisi and stato in ("INFEASIBLE", "CONTEGGIO")
        return None, None, None, None, esiti, decisi

    def prima_e_dopo(pr, k_chiesto, con_mosse_qui):
        trovate, es2, tutti = {}, [], True
        for direz, cand in (("prima", range(k_chiesto - 1, -1, -1)), ("dopo", range(k_chiesto + 1, len(ist.turni)))):
            for kk in cand:
                r = cerca(kk, pr, con_mosse_qui)
                es2.append(f"{ist.turni[kk].nome}: " + " · ".join(r[4]))
                if r[1] is not None:
                    trovate[direz] = (kk, *r[:4])
                    break
                tutti = tutti and r[5]
        return trovate, es2, tutti

    for n, pr in enumerate(ist.in_ordine_di_arrivo(), start=1):
        k_chiesto = ist.turno_della(pr)
        rec = {"ordine": n, "id": pr.id, "nome": pr.nome, "coperti": pr.coperti,
               "orario_richiesto": min_a_hhmm(pr.orario_min), "prenotata_il": pr.prenotata_il,
               "esito": None, "orario_promesso": None, "spostamento_min": None, "motivo": None,
               "stato_solver": None, "decisione": None, "spostamento_minimo_dimostrato": None,
               "spareggio": None, "proposta_prima": None, "proposta_dopo": None, "proposta_principale": None,
               "proposte_piu_vicine_dimostrate": None, "esiti_proposte": None, "tempo_s": 0.0,
               "turno_richiesto": ist.turni[k_chiesto].nome, "turno_promesso": None, "turno_proposto": None,
               "mosse": None, "tavolo_alla_conferma": None, "cambiano_tavolo": None}
        t0 = time.perf_counter()
        motivo = None
        presa = None                                  # (turno, variante, piano, voce, modello, su proposta)
        if pr.coperti > cap:
            rec.update(decisione="impossibile (a priori)", stato_solver="non necessario")
            motivo = MOTIVO_TROPPO_GRANDE
        else:
            v, nuovo, voce, mod, esiti, deciso = cerca(k_chiesto, pr, False)
            rec["stato_solver"] = f"{ist.turni[k_chiesto].nome}: " + " · ".join(esiti)
            if nuovo is not None:
                presa = (k_chiesto, v, nuovo, voce, mod, False)
            elif politica == MAI and not con_mosse:
                rec["decisione"] = "impossibile (dimostrato)" if deciso else "non decisa (tempo scaduto)"
                motivo = MOTIVO_TURNO_PIENO if deciso else MOTIVO_TEMPO_SCADUTO
            else:
                trovate, es2, tutti = ({}, [], deciso) if politica == MAI else prima_e_dopo(pr, k_chiesto, False)
                tutti = tutti and deciso
                if not trovate and con_mosse:         # verrebbe rifiutata: le mosse, prima nel turno chiesto
                    v, nuovo, voce, mod, esiti, d1 = cerca(k_chiesto, pr, True)
                    rec["stato_solver"] += " | con le mosse: " + " · ".join(esiti[1:] or ["nessuna mossa possibile"])
                    if nuovo is not None:
                        presa = (k_chiesto, v, nuovo, voce, mod, False)
                    elif politica != MAI:
                        trovate, es3, t3 = prima_e_dopo(pr, k_chiesto, True)
                        es2 += ["con le mosse: " + e for e in es3]
                        tutti = tutti and d1 and t3
                    else:
                        tutti = tutti and d1
                rec["esiti_proposte"] = " | ".join(es2) or None
                if presa is None and not trovate:
                    rec["decisione"] = "impossibile (dimostrato)" if tutti else "non decisa (tempo scaduto)"
                    motivo = (MOTIVO_TURNI_PIENI if politica != MAI else MOTIVO_TURNO_PIENO) if tutti else MOTIVO_TEMPO_SCADUTO
                elif presa is None:
                    for direz, (kk, *_r) in trovate.items():
                        rec[f"proposta_{direz}"] = min_a_hhmm(ist.turni[kk].inizio_min)
                    dopo = ist.proposta_a_parita == "dopo"
                    direz, (kk, v2, nuovo2, voce2, mod2) = min(trovate.items(), key=lambda it: (
                        abs(ist.turni[it[1][0]].inizio_min - pr.orario_min), (it[0] == "dopo") != dopo))
                    rec.update(proposta_principale=min_a_hhmm(ist.turni[kk].inizio_min), turno_proposto=ist.turni[kk].nome,
                               decisione="ammissibile su proposta", proposte_piu_vicine_dimostrate={"prima": None, "dopo": None})
                    if ist.accetta_proposta(ist.turni[kk].inizio_min - pr.orario_min):
                        presa = (kk, v2, nuovo2, voce2, mod2, True)
                    else:
                        motivo = MOTIVO_PROPOSTA_RIFIUTATA
                        rec["decisione"] = "proposta rifiutata dal cliente"
        if presa is not None:
            kk, v, nuovo, voce, mod, su_proposta = presa
            if v != corrente:
                nuove = vs[v]["mosse"][len(vs[corrente]["mosse"]):]
                rec["mosse"] = nuove
                for m in range(len(vs[corrente]["mosse"]), len(vs[v]["mosse"])):
                    per_mossa[m] = (f"{pr.nome} ×{pr.coperti} ({min_a_hhmm(ist.turni[kk].inizio_min)})", str(pr.id))
            accettate.append(voce)
            piano, corrente = nuovo, v
            if stabile:
                mod, piano = _stabilizza(istanza(v), accettate, pr, tavoli_ora, mod, piano, vs[v]["dati"], worker, seed)
                nuovo = piano
            ora = _tavoli_per_prenotazione(istanza(v), mod, nuovo)
            rec["tavolo_alla_conferma"] = ora.get(str(pr.id))
            rec["cambiano_tavolo"] = [f"{x}: {tavoli_ora[x]} → {ora.get(x)}" for x in tavoli_ora if ora.get(x) != tavoli_ora[x]]
            tavoli_ora = ora
            if su_proposta:
                rec.update(esito="accettata su proposta", spostamento_min=0, turno_promesso=ist.turni[kk].nome,
                           orario_promesso=min_a_hhmm(ist.turni[kk].inizio_min))
            else:
                rec.update(esito="accettata", decisione="ammissibile", spostamento_min=0, turno_promesso=rec["turno_richiesto"],
                           orario_promesso=min_a_hhmm(ist.turni[kk].inizio_min))
        if motivo is not None:
            rec.update(esito="rifiutata", motivo=motivo)
            rifiutate.append(_non_sistemata(ist, pr, ist.opzioni(pr), motivo))
        rec["tempo_s"] = round(time.perf_counter() - t0, 2)
        registro.append(rec)
        say(f"{n:2d}. {pr.prenotata_il} {pr.nome} ×{pr.coperti} {rec['orario_richiesto']}: {rec['esito']}"
            f"{'' if rec['esito'] != 'rifiutata' else ' (' + rec['motivo'] + ')'} [{rec['stato_solver']}"
            f"{' | ' + rec['esiti_proposte'] if rec['esiti_proposte'] else ''}, {rec['tempo_s']} s]"
            + (f" · mosse: {'; '.join(rec['mosse'])}" if rec["mosse"] else ""))

    # piantina finale sulla disposizione scelta
    t0 = time.perf_counter()
    ist_c = istanza(corrente)
    info = {"stato": "non necessario", "obiettivo": 0, "bound": 0, "gap_pct": 0.0, "tempo_s": 0.0}
    tavoli, assegnazioni = [], []
    if accettate:
        mod = _costruisci(ist_c, accettate, "fissa", non_sistemate_fisse=len(rifiutate))
        conferme = {str(r["id"]): r["tavolo_alla_conferma"] for r in registro if r["tavolo_alla_conferma"] is not None}
        termini = penalizza_cambi(mod, conferme, penalita_cambio) if penalita_cambio else []
        stato, finale, info = _risolvi_modello(mod, float(ist.sala.get("solver", {}).get("tempo_piantina_s", 60)),
                                               worker, seed, log, hint=piano)
        info["origine"] = "solver"
        if finale is not None and termini:      # l'obiettivo dichiarato resta quello delle componenti, la penalità a parte
            pen = sum(w * int(finale.get(nome, 0)) for nome, w in termini)
            info["penalita_cambi_tavolo"] = {"peso_per_cambio": penalita_cambio, "peso_per_cambio_di_quadrati":
                                             PENALITA_CAMBIO_PEZZO, "totale": pen}
            info["obiettivo"] = info["obiettivo"] - pen
            info["bound"] = info["obiettivo"] if info.get("stato") == "OPTIMAL" else max(0, info["bound"] - pen)
        if finale is None:
            finale, info["origine"] = piano, "ultimo piano di accettazione"
        tavoli, assegnazioni, sedute = _estrai(ist_c, mod, finale)
        if len(sedute) != len(accettate):
            raise RuntimeError("piantina finale: non tutte le accettate sono sedute")
    info["tempo_piantina_s"] = round(time.perf_counter() - t0, 2)
    finali = {str(r["id"]): str(r["tavolo"]) + (f" ({r['quadrati'][0]}-{r['quadrati'][1]})" if r.get("quadrati") else "")
              for r in assegnazioni}
    for rec in registro:
        if rec["tavolo_alla_conferma"] is not None:
            rec["tavolo_finale"] = finali.get(str(rec["id"]))
            rec["tavolo_cambiato"] = rec["tavolo_finale"] != rec["tavolo_alla_conferma"]
    comp = calcola_componenti(ist_c, tavoli, assegnazioni, rifiutate)
    if info.get("origine") == "solver":
        info["obiettivo_coerente_con_componenti"] = comp["totale"] == info["obiettivo"]
    else:
        info["obiettivo"] = comp["totale"]
    var = vs[corrente]
    stati = [r["decisione"] for r in registro]
    riepilogo = {
        "prenotazioni": len(registro),
        "accettate": sum(r["esito"] in ("accettata", "accettata su proposta") for r in registro),
        "accettate_su_proposta": sum(r["esito"] == "accettata su proposta" for r in registro),
        "rifiutate": sum(r["esito"] == "rifiutata" for r in registro),
        "proposte_rifiutate_dal_cliente": stati.count("proposta rifiutata dal cliente"),
        "decisioni_ammissibili": stati.count("ammissibile"),
        "decisioni_ammissibili_su_proposta": stati.count("ammissibile su proposta") + stati.count("proposta rifiutata dal cliente"),
        "decisioni_impossibili_dimostrate": stati.count("impossibile (dimostrato)"),
        "decisioni_impossibili_a_priori": stati.count("impossibile (a priori)"),
        "decisioni_unknown": stati.count("non decisa (tempo scaduto)"),
        "spostamento_minimo_non_dimostrato": 0,
        "tempo_decisioni_s": round(sum(r["tempo_s"] for r in registro), 1),
        "tempo_totale_s": round(time.perf_counter() - t_inizio, 1),
        "tavoli_cambiati": sum(1 for r in registro if r.get("tavolo_cambiato")),
    }
    return {"sala": ist.sala.get("nome", ""), "serata": ist.serata.get("serata", ""),
            "modalita": {"accettazione": ORDINE_DI_ARRIVO, "disposizione": LIBERA, "cliente_accetta_proposta": politica,
                         "proposta_max_distanza_min": ist.proposta_max_distanza_min,
                         "proposta_a_parita": ist.proposta_a_parita, **modalita_turni(ist)},
            "solver": info, "accettazione": riepilogo, "registro": registro, "obiettivo_componenti": comp,
            "tavoli": tavoli, "assegnazioni": assegnazioni, "non_sistemate": rifiutate,
            "variante": {"nome": var["nome"],
                         "mosse": [{"mossa": articoli(m), "per": (per_mossa.get(i) or (None, None))[0],
                                    "per_tavolo": finali.get((per_mossa.get(i) or (None, None))[1])}
                                   for i, m in enumerate(var["mosse"])],
                         "chi_siede": _chi_siede(var["dati"], assegnazioni),
                         "pezzi": pezzi_variante(sala, var["dati"]), "varianti_provate": len(vs)},
            "geometria": {"corridoio_cm": sala.corridoio_cm, "k_max": sala.k_max, "sedie_cm": sala.sedie_cm,
                          "spalliere_cm": sala.spalliere_cm, "cm_per_unita": sala.cpu, "quadrati_mobili": sala.n_quadrati,
                          "strade_riservate": False},
            "misure_usate": sala.misure}


def _chi_siede(dati: dict, assegnazioni: list[dict]) -> dict[str, list[str]]:
    """Per ogni pezzo cambiato rispetto al disegno (allungato, accorciato, nuovo): chi ci siede, turno per turno."""
    out = {}
    for t in _mobili(dati).values():
        stato = (t.get("_libera") or {}).get("stato")
        if stato:
            out[str(t["id"])] = [f"{r['nome']} ×{r['coperti']} ({r['turno']} turno)" for r in assegnazioni
                                 if str(r["tavolo"]) == str(t["id"])]
    return out


def _senza_interni(dati: dict) -> dict:
    """La piantina per il modello a tavoli fermi: senza le annotazioni interne della disposizione libera."""
    d = copy.deepcopy(dati)
    for t in d["tavoli"]:
        t.pop("_libera", None)
    return d


def pezzi_variante(sala: SalaLibera, dati: dict) -> list[dict]:
    """I tavoli mobili della disposizione, come li controlla il verificatore e li disegna la mappa: stato (disegno,
    accorciato, nuovo), da quali pezzi del disegno vengono i quadrati, posizione, sedie dei tavoli nuovi."""
    out = []
    for t in _mobili(dati).values():
        info = t.get("_libera") or {}
        p = {"id": str(t["id"]), "tipo": t["tipo"], "moduli": _moduli(t), "verso": t.get("verso"), "x": float(t["x"]),
             "y": float(t["y"]), "rot": float(t.get("rot") or 0), "posti": int(t.get("posti") or 0),
             "stato": info.get("stato", "disegno"), "da": _provenienza(t), "separabile": bool(t.get("separabile"))}
        if "spazio_u" in t:
            p["spazio_u"] = t["spazio_u"]
        if info.get("stato") in ("accorciato", "allungato"):
            p["prima"] = info["prima"]
        if info.get("stato") == "nuovo":
            f = info["fila"]
            p.update(orientamento="verticale" if f["vert"] else "orizzontale", x_cm=info["x_cm"], y_cm=info["y_cm"],
                     larghezza_cm=info["larghezza_cm"], altezza_cm=info["altezza_cm"], accesso=f.get("accesso"),
                     sedie={"lato_a": f["sedie"]["a"], "lato_b": f["sedie"]["b"], "testa": f["sedie"]["testa"],
                            "coda": f["sedie"]["coda"]})
        out.append(p)
    return out
