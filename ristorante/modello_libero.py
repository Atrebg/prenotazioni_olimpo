"""Disposizione LIBERA sulla sala vera: i quadrati mobili si dispongono in file e si decide chi siede dove, per turno.

Una sola disposizione fisica per serata (posizioni, rotazioni e sedie valgono per i due turni); dentro quella, per ogni
turno una fila si divide in pezzi CONTIGUI che restano al loro posto, come i blocchi del modo a tavoli fermi. I tavoli
fissi (panche, tondi, lungo, rettangolari) restano dove sono, con i loro posti; il lungo ha uno o due gruppi come oggi.

Due passi, perché la geometria dentro ogni decisione di accettazione è troppo pesante per CP-SAT quando la sala si riempie
(misurato il 28/10/2026 sul sabato di prova: decisioni da 50-70 s e rifiuti "tempo scaduto"):

1. **Postazioni** (`progetta_postazioni`, una volta per serata, senza guardare le prenotazioni): un modello CP-SAT con la
   geometria (griglia `griglia_cm`, `sala_libera.py`) mette nella sala più posti possibile con file di k quadrati
   (k <= `k_max`, a 0° o a 90°), per un inventario di qualche quadrato in più di quelli veri (`quadrati_in_piu`):
   - fila s di un tipo (k, orientamento), opzionale: presenza p, angolo in alto a sinistra x, y;
   - sedie: un letterale per lato da un quadrato (lato a, lato b, testa, coda); una sedia c'è solo se la sua zona
     (`sedie_cm`) è libera: rettangolo opzionale nello stesso NoOverlap2D di muri, ostacoli, porte con lo spazio davanti,
     passaggi, ingresso, corridoi di servizio e tavoli fissi con la zona delle loro sedie;
   - corridoio (`regola_impianto` "corridoi"): il riquadro di tavolo + sedie allargato di mezzo corridoio non tocca quello
     di un'altra fila né la zona delle sedie dei fissi allargata di mezzo corridoio (secondo NoOverlap2D): tra due tavoli
     restano almeno `corridoio_cm`; ripiego "corridoi_muri": anche lungo muri e ostacoli; poi si controlla che ogni
     tavolo e ogni porta si raggiungano dall'ingresso (`SalaLibera.irraggiungibili`);
   - obiettivo: 10 per sedia più 3 per tavolo; si parte dalla migliore di qualche disposizione golosa
     (`impianto_goloso`, stesse regole) data come hint.
2. **Serata** (`costruisci_postazioni`, per ogni decisione e per la piantina finale): niente geometria. Ogni postazione
   prende una fila di 0..K quadrati, accostati dall'inizio (u[s, q] = c'è il quadrato q, a prefisso), con le sedie
   della postazione; somma dei quadrati <= quadrati veri. Una fila più corta sta dentro lo spazio della postazione, e la
   sua sedia di coda nel posto del quadrato che manca: ogni disposizione della serata è un sottoinsieme della
   postazione, quindi resta valida e raggiungibile. Per turno: act[s, pezzo] come i blocchi; i posti di un pezzo sono le
   sedie dei suoi lati, la testata solo all'inizio, la coda solo all'ultimo quadrato presente; prenotazioni a[i, unità].
   Obiettivo: non sistemate >> posti vuoti (sui pezzi i posti NOMINALI 2j + 2, come i pezzi dei blocchi nel modo a
   tavoli fermi; sui fissi i loro posti) > divisioni delle file > cambi di partizione tra un turno e l'altro.

Accettazione in ordine di arrivo come il modo a tavoli fermi (`accetta_in_ordine_libera`): una decisione per richiesta
sulle postazioni (INFEASIBLE = turno pieno, dimostrato con queste postazioni), proposta dell'altro turno, piantina finale.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ortools.sat.python import cp_model

from .dati import (MAI, MOTIVO_PROPOSTA_RIFIUTATA, MOTIVO_TEMPO_SCADUTO, MOTIVO_TROPPO_GRANDE, MOTIVO_TURNI_PIENI,
                   MOTIVO_TURNO_PIENO, ORDINE_DI_ARRIVO, ErroreDati, Istanza, min_a_hhmm)
from .modello import _non_sistemata, _parametri, _Voce, modalita_turni
from .modello_turni import _opzioni_turno
from .piantina import LUNGO_DUE_GRUPPI, Piantina
from .sala_libera import SalaLibera, libero_box

LIBERA = "libera"
# impostazioni della disposizione libera (default; la sala può cambiarle con la chiave "libera")
IMPOSTAZIONI_LIBERA = {
    "k_max": 4, "griglia_cm": 10, "corridoio_cm": 60,
    "file_per_tipo": {"1": 16, "2": 6, "3": 4, "4": 3},     # postazioni al massimo per tipo (k quadrati, per orientamento)
    "quadrati_in_piu": 8,            # le postazioni si progettano per qualche quadrato in più: la serata sceglie dove
    "regola_impianto": "accesso",    # "accesso": ogni tavolo su un corridoio da almeno un lato, 40 cm fra spalliere;
                                     # "corridoi": corridoio fra ogni coppia di tavoli (più largo, meno tavoli)
    "spalliere_cm": 40,              # fra le zone (tavolo + sedie) di due tavoli diversi: come le righe della striscia
    "premio_tavolo": 3, "premio_quadrato": 4, "premio_fila_completa": {},  # postazioni: 10 per sedia più questi premi
    # ricerca deterministica (interleave_search, tempo "deterministico" di CP-SAT): stessi dati, stesso risultato;
    # il limite in secondi è solo una rete di sicurezza
    "dtempo_impianto": 15, "dtempo_decisione": 4, "dtempo_piantina": 10,
    "tempo_impianto_s": 120, "tempo_decisione_s": 10, "tempo_piantina_s": 30,
    "cpsat_impianto": False,         # CP-SAT ("corridoi") fra le candidate delle postazioni: 28/10 non batteva il disegno
    "worker_serata": 8,              # decisioni e piantina: 8 worker (veloci, non ripetibili al 100%); 1 = ripetibile
}
REGOLE = ("accesso", "corridoi", "corridoi_muri")


def impostazioni_libera(ist: Istanza) -> dict:
    cfg = dict(IMPOSTAZIONI_LIBERA)
    cfg.update(ist.sala.get("libera") or {})
    return cfg


def sala_libera(ist: Istanza) -> SalaLibera:
    """La geometria della sala, calcolata una volta per istanza."""
    s = getattr(ist, "_sala_libera", None)
    if s is None:
        if ist.piantina is None:
            raise ErroreDati("la disposizione libera vale solo per la sala vera (--sala olimpo/piantina.html)")
        cfg = impostazioni_libera(ist)
        s = SalaLibera(ist.piantina.dati, griglia_cm=int(cfg["griglia_cm"]), corridoio_cm=float(cfg["corridoio_cm"]),
                       k_max=int(cfg["k_max"]))
        s.spalliere_cm = float(cfg.get("spalliere_cm", 40))
        s.occ_fissi_spalliere = [[0] * s.W for _ in range(s.H)]
        for f in s.fissi:
            s.marca_fisso(s.occ_fissi_spalliere, f.corpo, s.sedie_cm + s.spalliere_cm / 2)
        s.misure.append({"cosa": "fra le zone (tavolo + sedie) di due tavoli diversi", "valore": f"{s.spalliere_cm:g} cm",
                         "fonte": "dal disegno: le righe della striscia hanno 40 cm fra le spalliere"})
        # il disegno dei tavoli mobili: le strade di servizio passano dove il disegno lascia i corridoi
        regola = cfg.get("regola_impianto", "accesso")
        s._tipi = _tipi(s, cfg)
        disegno, _ = disegno_in_file(s, regola)
        s.riserva_strade([(f["origine"], [scatole_fila(s, f)[0]]) for f in disegno])
        s._tipi = _tipi(s, cfg)
        s._disegno, s._disegno_note = disegno_in_file(s, regola)
        ist._sala_libera = s
    return s


# ---------------------------------------------------------------------------- geometria delle file (in celle)

def _celle(cm: float, g: int) -> int:
    return int(math.ceil(cm / g - 1e-9))


@dataclass
class _Tipo:
    k: int
    vert: bool
    n: int                                   # file al massimo di questo tipo
    xs: list = field(default_factory=list)   # posizioni ammesse (proiezioni)
    ys: list = field(default_factory=list)
    ammesse: set = field(default_factory=set)

    @property
    def nome(self) -> str:
        return f"{self.k}{'V' if self.vert else 'O'}"


def misure_celle(sala: SalaLibera) -> tuple[int, int, int]:
    """Lato del quadrato, profondità delle sedie e mezzo corridoio, in celle (arrotondati per eccesso)."""
    g = sala.griglia_cm
    return _celle(sala.lato_cm, g), _celle(sala.sedie_cm, g), _celle(sala.corridoio_cm / 2, g)


def corpo_e_lati(k: int, vert: bool, L: int, S: int) -> tuple[tuple, list]:
    """Corpo (dx, dy, w, h) e zone delle sedie [(lato, q, dx, dy, w, h)] di una fila, relativi all'angolo del corpo.
    Orizzontale: lato a = sopra, lato b = sotto, testa = sinistra, coda = destra; verticale: a = sinistra, b = destra,
    testa = sopra, coda = sotto."""
    if not vert:
        corpo = (0, 0, k * L, L)
        lati = [("a", q, q * L, -S, L, S) for q in range(k)] + [("b", q, q * L, L, L, S) for q in range(k)] + \
               [("testa", 0, -S, 0, S, L), ("coda", 0, k * L, 0, S, L)]
    else:
        corpo = (0, 0, L, k * L)
        lati = [("a", q, -S, q * L, S, L) for q in range(k)] + [("b", q, L, q * L, S, L) for q in range(k)] + \
               [("testa", 0, 0, -S, L, S), ("coda", 0, 0, k * L, L, S)]
    return corpo, lati


def _tipi(sala: SalaLibera, cfg: dict) -> list[_Tipo]:
    """Tipi di fila che entrano nella sala, con le posizioni ammesse del corpo (libero dai muri, dalle cose vietate, dai
    corridoi di servizio e dalle zone delle sedie dei fissi)."""
    L, S, B = misure_celle(sala)
    W, H = sala.W, sala.H
    pt = sala.prefissi(sala.occ_tavoli)
    caps = {int(k): int(v) for k, v in (cfg.get("file_per_tipo") or {}).items()}
    tot = sala.n_quadrati + int(cfg.get("quadrati_in_piu", 0))
    out = []
    for k in range(1, int(cfg["k_max"]) + 1):
        for vert in ((False,) if k == 1 else (False, True)):
            n = min(caps.get(k, 0), tot // k)
            if n <= 0:
                continue
            w, h = (L, k * L) if vert else (k * L, L)
            t = _Tipo(k, vert, n)
            for j in range(H - h + 1):
                for i in range(W - w + 1):
                    if libero_box(pt, W, H, i, j, i + w, j + h):
                        t.ammesse.add((i, j))
            if t.ammesse:
                t.xs = sorted({i for i, _ in t.ammesse})
                t.ys = sorted({j for _, j in t.ammesse})
                out.append(t)
    return out


def posti_nominali(a: int, b: int) -> int:
    """Posti "di listino" di un pezzo per l'obiettivo, come i pezzi dei blocchi nel modo a tavoli fermi: 2 per quadrato
    più 2 (2j + 2). Così dividere costa (posti vuoti in più) e un pezzo di mezzo non conviene più di un tavolo a sé."""
    return 2 * (b - a + 1) + 2


def posti_pezzo(fila: dict, a: int, b: int) -> int:
    """Sedie di un pezzo (a..b) di una fila: i lati dei suoi quadrati, la testata e la coda solo alle estremità."""
    s, k = fila["sedie"], fila["k"]
    return sum(s["a"][q] + s["b"][q] for q in range(a, b + 1)) + (s["testa"] if a == 0 else 0) + \
        (s["coda"] if b == k - 1 else 0)


def regioni(sala: SalaLibera, file: list[dict]) -> list[tuple[str, list]]:
    """Per la raggiungibilità: per ogni fila, i box in celle del corpo e delle zone delle sedie presenti."""
    L, S, _ = misure_celle(sala)
    out = []
    for n, f in enumerate(file):
        corpo, lati = corpo_e_lati(f["k"], f["vert"], L, S)
        boxes = [(f["x"], f["y"], f["x"] + corpo[2], f["y"] + corpo[3])]
        for lato, q, dx, dy, w, h in lati:
            if _sedia(f["sedie"], lato, q):
                boxes.append((f["x"] + dx, f["y"] + dy, f["x"] + dx + w, f["y"] + dy + h))
        out.append((f"fila{n}", boxes))
    return out


def _sedia(sedie: dict, lato: str, q: int) -> int:
    return sedie[lato][q] if lato in ("a", "b") else sedie[lato]


def _metti(sedie: dict, lato: str, q: int, v: int) -> None:
    if lato in ("a", "b"):
        sedie[lato][q] = v
    else:
        sedie[lato] = v


def _dilata(sala: SalaLibera, occ, r: int) -> list[list[int]]:
    """Celle a distanza (a blocchi) <= r da una cella occupata."""
    W, H = sala.W, sala.H
    pref = sala.prefissi(occ)
    return [[int(not libero_box(pref, W, H, max(0, i - r), max(0, j - r), min(W, i + r + 1), min(H, j + r + 1)))
             for i in range(W)] for j in range(H)]


# ---------------------------------------------------------------------------- 1. postazioni (geometria)

def _premi(cfg: dict) -> tuple[int, int, dict[int, int]]:
    return (int(cfg.get("premio_tavolo", 3)), int(cfg.get("premio_quadrato", 0)),
            {int(k): int(v) for k, v in (cfg.get("premio_fila_completa") or {}).items()})


def spazi(sala: SalaLibera, regola: str) -> tuple[int, list]:
    """Mezza distanza fra tavoli diversi (celle) e celle vietate al riquadro allargato di un tavolo (zona dei fissi
    allargata; con "corridoi_muri" anche muri e ostacoli allargati)."""
    g = sala.griglia_cm
    if regola == "accesso":
        return _celle(sala.spalliere_cm / 2, g), sala.occ_fissi_spalliere
    B = _celle(sala.corridoio_cm / 2, g)
    if regola == "corridoi_muri":
        return B, [[a or b for a, b in zip(r1, r2)] for r1, r2 in zip(sala.occ_fissi, _dilata(sala, sala.occ_cammino, B))]
    return B, sala.occ_fissi


def costruisci_impianto(ist: Istanza, regola: str, quadrati: int, cfg: dict) -> tuple[cp_model.CpModel, list[dict]]:
    """Modello delle postazioni: file opzionali con posizione, sedie e corridoi; obiettivo 10 per sedia, più un premio
    per tavolo e uno per le file lunghe con tutte le sedie (8 o 10 posti: i gruppi grandi)."""
    if regola not in REGOLE:
        raise ValueError(regola)
    sala = sala_libera(ist)
    L, S, B = misure_celle(sala)
    W, H = sala.W, sala.H
    m = cp_model.CpModel()
    file = []
    for t in sala._tipi:
        prima = None
        for n in range(t.n):
            ch = f"f{t.nome}.{n}"
            p = m.new_bool_var(f"p_{ch}")
            x = m.new_int_var_from_domain(cp_model.Domain.from_values(t.xs), f"x_{ch}")
            y = m.new_int_var_from_domain(cp_model.Domain.from_values(t.ys), f"y_{ch}")
            sedie = {"a": [m.new_bool_var(f"sa_{ch}_{q}") for q in range(t.k)],
                     "b": [m.new_bool_var(f"sb_{ch}_{q}") for q in range(t.k)],
                     "testa": m.new_bool_var(f"st_{ch}"), "coda": m.new_bool_var(f"sc_{ch}")}
            for lit in sedie["a"] + sedie["b"] + [sedie["testa"], sedie["coda"]]:
                m.add_implication(lit, p)
            if prima is not None:            # simmetrie: presenti per prime e in ordine di posizione
                m.add_implication(p, prima["p"])
                m.add(prima["y"] * W + prima["x"] + 1 <= y * W + x).only_enforce_if(p)
            f = {"chiave": ch, "tipo": t, "p": p, "x": x, "y": y, "sedie": sedie}
            file.append(f)
            prima = f
    m.add(sum(f["tipo"].k * f["p"] for f in file) <= quadrati)
    bx2, by2, bx1, by1 = [], [], [], []
    for i0, j0, i1, j1 in sala.rettangoli(sala.occ_tavoli):
        bx2.append(m.new_fixed_size_interval_var(i0, i1 - i0, ""))
        by2.append(m.new_fixed_size_interval_var(j0, j1 - j0, ""))
    B, occ1 = spazi(sala, regola)                 # tra due tavoli restano almeno 2B celle
    for i0, j0, i1, j1 in sala.rettangoli(occ1):
        bx1.append(m.new_fixed_size_interval_var(i0, i1 - i0, ""))
        by1.append(m.new_fixed_size_interval_var(j0, j1 - j0, ""))
    A = _celle(sala.corridoio_cm, sala.griglia_cm)
    cammino = [(m.new_fixed_size_interval_var(i0, i1 - i0, ""), m.new_fixed_size_interval_var(j0, j1 - j0, ""))
               for i0, j0, i1, j1 in sala.rettangoli(sala.occ_cammino)] if regola == "accesso" else []
    scatole, accessi = {}, {}
    for f in file:
        ch, k, vert, x, y, p, s = f["chiave"], f["tipo"].k, f["tipo"].vert, f["x"], f["y"], f["p"], f["sedie"]
        corpo, lati = corpo_e_lati(k, vert, L, S)
        box = [(m.new_optional_fixed_size_interval_var(x, corpo[2], p, f"cx_{ch}"),
                m.new_optional_fixed_size_interval_var(y, corpo[3], p, f"cy_{ch}"))]
        for lato, q, dx, dy, w, h in lati:
            lit = _sedia(s, lato, q)
            box.append((m.new_optional_fixed_size_interval_var(x + dx, w, lit, f"zx_{ch}_{lato}{q}"),
                        m.new_optional_fixed_size_interval_var(y + dy, h, lit, f"zy_{ch}_{lato}{q}")))
        scatole[ch] = box
        bx2 += [b[0] for b in box]
        by2 += [b[1] for b in box]
        any_a, any_b = m.new_bool_var(f"ua_{ch}"), m.new_bool_var(f"ub_{ch}")
        m.add_max_equality(any_a, s["a"])
        m.add_max_equality(any_b, s["b"])
        sx0, sx1, sy0, sy1 = (s["testa"], s["coda"], any_a, any_b) if not vert else (any_a, any_b, s["testa"], s["coda"])
        if regola == "accesso":
            # zona d'accesso: su uno dei quattro lati, oltre le sedie, profonda un corridoio e larga quanto il lato,
            # senza altri tavoli né sedie, muri, ostacoli o tavoli fissi (passaggi e altre zone d'accesso sì)
            acc, lits = [], []
            for nome, ax, aw, ay, ah in _lati_accesso(x, y, corpo, vert, sx0, sx1, sy0, sy1, S, A):
                lit = m.new_bool_var(f"acc_{ch}_{nome}")
                lits.append(lit)
                vx = m.new_int_var(-S - A - 2, W + S + A + 2, "")
                vy = m.new_int_var(-S - A - 2, H + S + A + 2, "")
                m.add(vx == ax)
                m.add(vy == ay)
                acc.append((m.new_optional_fixed_size_interval_var(vx, aw, lit, ""),
                            m.new_optional_fixed_size_interval_var(vy, ah, lit, "")))
            m.add(sum(lits) == p)
            accessi[ch] = acc
        # riquadro di tavolo + sedie, allargato di B celle (mezza distanza fra tavoli)
        lo, hi = -S - B, max(W, H) + 2 * S + 2 * B + L * k
        ex0, ex1, ey0, ey1 = (m.new_int_var(lo, hi, f"{n}_{ch}") for n in ("ex0", "ex1", "ey0", "ey1"))
        m.add(ex0 == x - S * sx0 - B)
        m.add(ex1 == x + corpo[2] + S * sx1 + B)
        m.add(ey0 == y - S * sy0 - B)
        m.add(ey1 == y + corpo[3] + S * sy1 + B)
        ew = m.new_int_var(corpo[2] + 2 * B, corpo[2] + 2 * B + 2 * S, f"ew_{ch}")
        eh = m.new_int_var(corpo[3] + 2 * B, corpo[3] + 2 * B + 2 * S, f"eh_{ch}")
        m.add(ew == ex1 - ex0)
        m.add(eh == ey1 - ey0)
        bx1.append(m.new_optional_interval_var(ex0, ew, ex1, p, f"ix_{ch}"))
        by1.append(m.new_optional_interval_var(ey0, eh, ey1, p, f"iy_{ch}"))
    m.add_no_overlap_2d(bx2, by2)
    if regola == "accesso":
        for ch, acc in accessi.items():         # la zona d'accesso di una fila contro tutto il resto
            boxes = acc + [b for c2, lst in scatole.items() if c2 != ch for b in lst] + cammino
            m.add_no_overlap_2d([b[0] for b in boxes], [b[1] for b in boxes])
    m.add_no_overlap_2d(bx1, by1)
    sedie_tot = sum(lit for f in file for lit in f["sedie"]["a"] + f["sedie"]["b"] + [f["sedie"]["testa"], f["sedie"]["coda"]])
    premio_tavolo, premio_quadrato, premio_completa = _premi(cfg)
    complete = []
    for f in file:
        if premio_completa.get(f["tipo"].k):
            g = m.new_bool_var(f"completa_{f['chiave']}")
            for lit in f["sedie"]["a"] + f["sedie"]["b"] + [f["sedie"]["testa"], f["sedie"]["coda"]]:
                m.add_implication(g, lit)
            complete.append((premio_completa[f["tipo"].k], g))
    m.maximize(10 * sedie_tot + sum((premio_tavolo + premio_quadrato * f["tipo"].k) * f["p"] for f in file)
               + sum(w * g for w, g in complete))
    return m, file


def _lati_accesso(x, y, corpo, vert, sx0, sx1, sy0, sy1, S, A):
    """Zone d'accesso possibili di una fila: (lato, x, larghezza, y, altezza) sui quattro lati, oltre le sedie."""
    w, h = corpo[2], corpo[3]
    sopra = ("a" if not vert else "testa", x, w, y - S * sy0 - A, A)
    sotto = ("b" if not vert else "coda", x, w, y + h + S * sy1, A)
    sinistra = ("testa" if not vert else "a", x - S * sx0 - A, A, y, h)
    destra = ("coda" if not vert else "b", x + w + S * sx1, A, y, h)
    return [sopra, sotto, sinistra, destra]


def _sovrap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _allarga(b, r):
    return b[0] - r, b[1] - r, b[2] + r, b[3] + r


def _libero_fuori(pref, W, H, box) -> bool:
    """Box libero nella griglia; fuori dalla griglia conta come libero (un riquadro allargato può uscire)."""
    i0, j0, i1, j1 = max(0, box[0]), max(0, box[1]), min(W, box[2]), min(H, box[3])
    return i0 >= i1 or j0 >= j1 or libero_box(pref, W, H, i0, j0, i1, j1)


def scatole_fila(sala: SalaLibera, f: dict) -> tuple[tuple, list]:
    """Corpo e zone delle sedie presenti di una fila, in celle (i0, j0, i1, j1)."""
    L, S, _ = misure_celle(sala)
    corpo, lati = corpo_e_lati(f["k"], f["vert"], L, S)
    cb = (f["x"], f["y"], f["x"] + corpo[2], f["y"] + corpo[3])
    return cb, [(f["x"] + dx, f["y"] + dy, f["x"] + dx + w, f["y"] + dy + h) for lato, q, dx, dy, w, h in lati
                if _sedia(f["sedie"], lato, q)]


def zone_accesso(sala: SalaLibera, f: dict) -> dict[str, tuple]:
    """Le quattro zone d'accesso possibili di una fila (oltre le sedie che ha), in celle."""
    L, S, _ = misure_celle(sala)
    A = _celle(sala.corridoio_cm, sala.griglia_cm)
    corpo, _ = corpo_e_lati(f["k"], f["vert"], L, S)
    s = f["sedie"]
    ua, ub = int(any(s["a"])), int(any(s["b"]))
    sx0, sx1, sy0, sy1 = (s["testa"], s["coda"], ua, ub) if not f["vert"] else (ua, ub, s["testa"], s["coda"])
    return {n: (ax, ay, ax + aw, ay + ah) for n, ax, aw, ay, ah in
            _lati_accesso(f["x"], f["y"], corpo, f["vert"], sx0, sx1, sy0, sy1, S, A)}


def controlla_regole(sala: SalaLibera, file: list[dict], regola: str = "accesso") -> list[str]:
    """Le regole della disposizione libera sulla griglia, fila per fila: corpo e sedie liberi (muri, cose vietate,
    zone dei fissi, strade di servizio), niente sovrapposizioni, 2B celle fra tavoli diversi e dai fissi, una zona
    d'accesso libera (regola "accesso"), tutti raggiungibili. Lista dei problemi (vuota = ammissibile)."""
    W, H = sala.W, sala.H
    B, occ1 = spazi(sala, regola)
    pt, pa, pe = sala.prefissi(sala.occ_tavoli), sala.prefissi(sala.occ_cammino), sala.prefissi(occ1)
    reg = [scatole_fila(sala, f) for f in file]
    out = []
    for n, (f, (cb, zs)) in enumerate(zip(file, reg)):
        nome = f.get("origine") or f"fila{n}"
        for b in [cb] + zs:
            if not libero_box(pt, W, H, *b):
                out.append(f"{nome}: tavolo o sedia su muri, cose vietate, zona dei fissi o strade di servizio")
        bb = (min(b[0] for b in [cb] + zs), min(b[1] for b in [cb] + zs), max(b[2] for b in [cb] + zs), max(b[3] for b in [cb] + zs))
        if not _libero_fuori(pe, W, H, _allarga(bb, B)):
            out.append(f"{nome}: a meno di {2 * B * sala.griglia_cm} cm dalla zona delle sedie di un fisso")
        for m2 in range(n + 1, len(file)):
            cb2, zs2 = reg[m2]
            bb2 = (min(b[0] for b in [cb2] + zs2), min(b[1] for b in [cb2] + zs2), max(b[2] for b in [cb2] + zs2),
                   max(b[3] for b in [cb2] + zs2))
            if _sovrap(_allarga(bb, B), _allarga(bb2, B)):
                out.append(f"{nome} e {file[m2].get('origine') or f'fila{m2}'}: a meno di {2 * B * sala.griglia_cm} cm")
        if regola == "accesso":
            z = zone_accesso(sala, f).get(f.get("accesso"))
            altri = [b for m2, (cb2, zs2) in enumerate(reg) if m2 != n for b in [cb2] + zs2]
            if z is None or not libero_box(pa, W, H, *z) or any(_sovrap(z, b) for b in altri):
                out.append(f"{nome}: senza zona d'accesso libera")
    mancano = sala.irraggiungibili(regioni(sala, file))
    if mancano:
        out.append(f"non raggiungibili: {', '.join(sorted(mancano))}")
    return out


def disegno_in_file(sala: SalaLibera, regola: str = "accesso") -> tuple[list[dict], list[str]]:
    """I tavoli mobili della piantina come file sulla griglia, con le regole della disposizione libera: orientamento a
    0° o 90° (il più vicino alla rotazione disegnata), la posizione libera più vicina a quella disegnata (entro 60 cm),
    sedie dove ci stanno, una zona d'accesso per tavolo (se serve si toglie una sedia da quel lato). Restituisce le
    file e le note (spostati, sedie tolte, tavoli che non entrano)."""
    W, H, g = sala.W, sala.H, sala.griglia_cm
    L, S, _ = misure_celle(sala)
    B, occ1 = spazi(sala, regola)
    pt, pa, pe = sala.prefissi(sala.occ_tavoli), sala.prefissi(sala.occ_cammino), sala.prefissi(occ1)
    note, file = [], []
    for t in sala.dati.get("tavoli") or []:
        if t.get("tipo") not in ("quadrato", "blocco") or t.get("fisso"):
            continue
        k = int(t.get("moduli") or 1) if t["tipo"] == "blocco" else 1
        vert = t.get("verso") == "verticale" and k > 1
        giri = round(float(t.get("rot") or 0) / 90)
        if k > 1 and giri % 2:
            vert = not vert
        w, h = (L, k * L) if vert else (k * L, L)
        cx, cy = float(t["x"]) * sala.cpu / g, float(t["y"]) * sala.cpu / g
        i0, j0 = round(cx - w / 2), round(cy - h / 2)
        corpi = [scatole_fila(sala, f)[0] for f in file]
        scelto = None
        for r in range(0, 11):                     # anelli di posizioni sempre più lontane, fino a 1 m
            cand = sorted({(i0 + di, j0 + dj) for di in range(-r, r + 1) for dj in range(-r, r + 1)
                           if max(abs(di), abs(dj)) == r}, key=lambda q: ((q[0] - i0) ** 2 + (q[1] - j0) ** 2, q))
            for i, j in cand:
                cb = (i, j, i + w, j + h)
                if libero_box(pt, W, H, *cb) and _libero_fuori(pe, W, H, _allarga(cb, B)) and \
                        not any(_sovrap(_allarga(cb, B), _allarga(c, B)) for c in corpi):
                    scelto = (i, j)
                    break
            if scelto:
                break
        if scelto is None:
            note.append(f"{t['id']}: non entra con le regole (posizione disegnata occupata)")
            continue
        if scelto != (i0, j0) or giri % 2 or float(t.get("rot") or 0) % 90:
            note.append(f"{t['id']}: messo a {abs(scelto[0] - i0) * g + abs(scelto[1] - j0) * g} cm"
                        + (f", ruotato a {'90' if vert else '0'}° (disegnato a {float(t.get('rot') or 0):g}°)"
                           if float(t.get("rot") or 0) else ""))
        file.append({"k": k, "vert": vert, "x": scelto[0], "y": scelto[1], "origine": str(t["id"]),
                     "sedie": {"a": [0] * k, "b": [0] * k, "testa": 0, "coda": 0}, "accesso": None})
    corpi = [scatole_fila(sala, f)[0] for f in file]
    riq = list(corpi)                              # riquadro di tavolo + sedie di ogni fila (come nel modello)
    for n, f in enumerate(file):                   # sedie dove ci stanno; i riquadri allargati di B non si toccano
        _, lati = corpo_e_lati(f["k"], f["vert"], L, S)
        for lato, q, dx, dy, w, h in lati:
            z = (f["x"] + dx, f["y"] + dy, f["x"] + dx + w, f["y"] + dy + h)
            nuovo = (min(riq[n][0], z[0]), min(riq[n][1], z[1]), max(riq[n][2], z[2]), max(riq[n][3], z[3]))
            if libero_box(pt, W, H, *z) and _libero_fuori(pe, W, H, _allarga(nuovo, B)) and \
                    not any(_sovrap(_allarga(nuovo, B), _allarga(b, B)) for m2, b in enumerate(riq) if m2 != n):
                _metti(f["sedie"], lato, q, 1)
                riq[n] = nuovo
    if regola == "accesso":                        # una zona d'accesso per tavolo; se non c'è, via una sedia
        for n, f in enumerate(file):
            def libera(z):
                altri = [c for m2, c in enumerate(corpi) if m2 != n] + \
                    [b for m2 in range(len(file)) if m2 != n for b in scatole_fila(sala, file[m2])[1]]
                return libero_box(pa, W, H, *z) and not any(_sovrap(z, b) for b in altri)
            serv = sala.occ_servizio            # prima i lati che danno sulle strade di servizio
            zz = sorted(zone_accesso(sala, f).items(), key=lambda lz: -sum(
                serv[j][i] for j in range(max(0, lz[1][1]), min(H, lz[1][3])) for i in range(max(0, lz[1][0]), min(W, lz[1][2]))))
            ok = next((lato for lato, z in zz if libera(z)), None)
            if ok is None:
                for lato in ("coda", "testa", "b", "a"):
                    prima = {k2: (v[:] if isinstance(v, list) else v) for k2, v in f["sedie"].items()}
                    if lato in ("a", "b"):
                        f["sedie"][lato] = [0] * f["k"]
                    else:
                        f["sedie"][lato] = 0
                    if f["sedie"] != prima and libera(zone_accesso(sala, f)[lato]):
                        ok = lato
                        note.append(f"{f['origine']}: tolte le sedie del lato {lato} per lasciare il corridoio")
                        break
                    f["sedie"] = prima
            f["accesso"] = ok
            if ok is None:
                note.append(f"{f['origine']}: senza zona d'accesso")
    # se il disegno così convertito chiude un passaggio, via il tavolo che riapre di più (a parità, quello con meno sedie)
    mancano = sala.irraggiungibili(regioni(sala, file))
    while mancano and file:
        prove = []
        for n, f in enumerate(file):
            resto = file[:n] + file[n + 1:]
            prove.append((len(sala.irraggiungibili(regioni(sala, resto))), posti_pezzo(f, 0, f["k"] - 1), n))
        dopo, _, n = min(prove)
        if dopo >= len(mancano):
            break
        note.append(f"{file[n]['origine']}: tolto, così convertito chiudeva il passaggio verso {len(mancano) - dopo} tavoli o porte")
        file.pop(n)
        mancano = sala.irraggiungibili(regioni(sala, file))
    return file, note


class _Posa:
    """Griglie di lavoro per mettere file una alla volta con le regole del modello (goloso)."""

    def __init__(self, sala: SalaLibera, regola: str):
        self.sala, self.regola = sala, regola
        self.B, occ1 = spazi(sala, regola)
        self.occ2 = [r[:] for r in sala.occ_tavoli]          # tavoli e sedie: muri, vietate, fissi, strade, altre file
        self.occA = [r[:] for r in sala.occ_cammino]         # zone d'accesso: muri, ostacoli, fissi, tavoli e sedie
        self.occE = [r[:] for r in occ1]                     # riquadri allargati
        self.aggiorna()

    def aggiorna(self):
        s = self.sala
        self.p2, self.pA, self.pE = s.prefissi(self.occ2), s.prefissi(self.occA), s.prefissi(self.occE)

    def segna(self, occ, box):
        W, H = self.sala.W, self.sala.H
        for j in range(max(0, box[1]), min(H, box[3])):
            for i in range(max(0, box[0]), min(W, box[2])):
                occ[j][i] = 1

    def prova(self, k: int, vert: bool, i: int, j: int) -> dict | None:
        sala, W, H = self.sala, self.sala.W, self.sala.H
        L, S, _ = misure_celle(sala)
        corpo, lati = corpo_e_lati(k, vert, L, S)
        cb = (i, j, i + corpo[2], j + corpo[3])
        if not libero_box(self.p2, W, H, *cb) or not _libero_fuori(self.pE, W, H, _allarga(cb, self.B)):
            return None
        f = {"k": k, "vert": vert, "x": i, "y": j, "sedie": {"a": [0] * k, "b": [0] * k, "testa": 0, "coda": 0},
             "accesso": None}
        for lato, q, dx, dy, w, h in lati:
            z = (i + dx, j + dy, i + dx + w, j + dy + h)
            if libero_box(self.p2, W, H, *z) and _libero_fuori(self.pE, W, H, _allarga(z, self.B)):
                _metti(f["sedie"], lato, q, 1)
        if not posti_pezzo(f, 0, k - 1):
            return None
        _, zs = scatole_fila(sala, f)
        bb = (min(b[0] for b in [cb] + zs), min(b[1] for b in [cb] + zs), max(b[2] for b in [cb] + zs), max(b[3] for b in [cb] + zs))
        if not _libero_fuori(self.pE, W, H, _allarga(bb, self.B)):
            return None
        if self.regola == "accesso":
            f["accesso"] = next((n for n, z in zone_accesso(sala, f).items() if libero_box(self.pA, W, H, *z)), None)
            if f["accesso"] is None:
                return None
        return f

    def metti(self, f: dict) -> None:
        cb, zs = scatole_fila(self.sala, f)
        for b in [cb] + zs:
            self.segna(self.occ2, b)
            self.segna(self.occA, b)
        bb = (min(b[0] for b in [cb] + zs), min(b[1] for b in [cb] + zs), max(b[2] for b in [cb] + zs), max(b[3] for b in [cb] + zs))
        self.segna(self.occE, _allarga(bb, self.B))
        if f.get("accesso"):
            self.segna(self.occ2, zone_accesso(self.sala, f)[f["accesso"]])
        self.aggiorna()


def impianto_goloso(sala: SalaLibera, quadrati: int, regola: str, ordine: list[tuple[int, bool]]) -> list[dict]:
    """Postazioni messe una alla volta, dall'alto in basso e da sinistra a destra, provando i tipi nell'`ordine` dato,
    con le regole del modello. Serve come punto di partenza di CP-SAT, con il disegno."""
    posa = _Posa(sala, regola)
    tipi = {(t.k, t.vert): t for t in sala._tipi}
    usati, messi, n_tipo = 0, [], {}
    for j in range(sala.H):
        for i in range(sala.W):
            for k, vert in ordine:
                t = tipi.get((k, vert))
                if t is None or (i, j) not in t.ammesse or usati + k > quadrati or n_tipo.get(t.nome, 0) >= t.n:
                    continue
                f = posa.prova(k, vert, i, j)
                if f is None:
                    continue
                posa.metti(f)
                messi.append(f)
                usati += k
                n_tipo[t.nome] = n_tipo.get(t.nome, 0) + 1
                break
    return messi


def _hint_impianto(file: list[dict], messi: list[dict], W: int) -> dict:
    """Hint per il modello delle postazioni da una disposizione già fatta (file dello stesso tipo in ordine di posizione)."""
    h = {}
    per_tipo: dict[tuple, list] = {}
    for f in sorted(messi, key=lambda f: (f["y"] * W + f["x"])):
        per_tipo.setdefault((f["k"], f["vert"]), []).append(f)
    usati: dict[tuple, int] = {}
    for f in file:
        chiave = (f["tipo"].k, f["tipo"].vert)
        n = usati.get(chiave, 0)
        lst = per_tipo.get(chiave, [])
        if n < len(lst):
            g = lst[n]
            usati[chiave] = n + 1
            h[f["p"].name], h[f["x"].name], h[f["y"].name] = 1, g["x"], g["y"]
            for q in range(f["tipo"].k):
                h[f["sedie"]["a"][q].name], h[f["sedie"]["b"][q].name] = g["sedie"]["a"][q], g["sedie"]["b"][q]
            h[f["sedie"]["testa"].name], h[f["sedie"]["coda"].name] = g["sedie"]["testa"], g["sedie"]["coda"]
            if g.get("accesso"):
                for nome in ("a", "b", "testa", "coda"):
                    h[f"acc_{f['chiave']}_{nome}"] = int(nome == g["accesso"])
        else:
            h[f["p"].name] = 0
            for lit in f["sedie"]["a"] + f["sedie"]["b"] + [f["sedie"]["testa"], f["sedie"]["coda"]]:
                h[lit.name] = 0
    return h


def _valore_impianto(messi: list[dict], cfg: dict) -> int:
    premio_tavolo, premio_quadrato, premio_completa = _premi(cfg)
    return sum(10 * posti_pezzo(f, 0, f["k"] - 1) + premio_tavolo + premio_quadrato * f["k"] + (
        premio_completa.get(f["k"], 0) if posti_pezzo(f, 0, f["k"] - 1) == 2 * f["k"] + 2 else 0) for f in messi)


ORDINI_GOLOSI = [[(3, False), (3, True), (2, False), (2, True), (1, False)],
                 [(2, False), (2, True), (3, False), (3, True), (1, False)],
                 [(4, False), (4, True), (3, False), (3, True), (2, False), (2, True), (1, False)],
                 [(3, True), (3, False), (2, True), (2, False), (1, False)],
                 [(2, True), (2, False), (1, False)]]


def assegna_accessi(sala: SalaLibera, file: list[dict]) -> None:
    """A ogni fila il primo lato con la zona d'accesso libera (muri, ostacoli, fissi, altri tavoli e sedie); prima i
    lati che danno sulle strade di servizio. Una fila senza lato libero resta senza (e non passa le regole)."""
    W, H = sala.W, sala.H
    pa = sala.prefissi(sala.occ_cammino)
    reg = [scatole_fila(sala, f) for f in file]
    serv = sala.occ_servizio
    for n, f in enumerate(file):
        altri = [b for m2, (cb, zs) in enumerate(reg) if m2 != n for b in [cb] + zs]
        zz = sorted(zone_accesso(sala, f).items(), key=lambda lz: -sum(
            serv[j][i] for j in range(max(0, lz[1][1]), min(H, lz[1][3])) for i in range(max(0, lz[1][0]), min(W, lz[1][2]))))
        f["accesso"] = next((lato for lato, z in zz if libero_box(pa, W, H, *z) and not any(_sovrap(z, b) for b in altri)),
                            None)


def progetta_postazioni(ist: Istanza, cfg: dict, worker: int, seed: int, log: bool = False,
                        say: Callable[[str], None] = lambda _m: None) -> tuple[list[dict], dict]:
    """Le postazioni della serata, tutte con le regole della disposizione libera (`regola_impianto`, di solito
    "accesso": un lato su un corridoio di 60 cm, 40 cm fra tavoli diversi, strade di servizio libere, tutto
    raggiungibile). Candidate, tutte ripetibili: il disegno della piantina convertito in file, qualche disposizione
    golosa, e la disposizione di CP-SAT sul modello "corridoi" (più leggero: 60 cm fra due tavoli qualsiasi, che
    rispetta anche i 40 cm) partendo dalla migliore delle altre, a cui si assegnano poi i lati d'accesso. Si tiene la
    candidata con più sedie (più i premi) che passa le regole: mai peggio del disegno. CP-SAT sul modello "accesso"
    non si usa: con una zona d'accesso per fila diventa troppo lento (240 s per migliorare di una sedia, 28/10/2026)."""
    sala = sala_libera(ist)
    quadrati = sala.n_quadrati + int(cfg.get("quadrati_in_piu", 0))
    regola = cfg.get("regola_impianto", "accesso")
    t0 = time.perf_counter()
    cand = [("disegno", [dict(f, sedie={k: (v[:] if isinstance(v, list) else v) for k, v in f["sedie"].items()})
                         for f in sala._disegno])]
    cand += [(f"goloso {o[0][0]}{'V' if o[0][1] else 'O'}", impianto_goloso(sala, quadrati, regola, o)) for o in ORDINI_GOLOSI]
    valide = {n: g for n, g in cand if g and not controlla_regole(sala, g, regola)}
    note = {n: (controlla_regole(sala, g, regola)[:2] if g else ["vuota"]) for n, g in cand if n not in valide}
    nome_p, partenza = max(valide.items(), key=lambda ng: _valore_impianto(ng[1], cfg), default=(None, None))
    info = {"regola": regola}
    if regola == "accesso" and cfg.get("cpsat_impianto"):   # CP-SAT sul modello "corridoi", dalla migliore candidata
        m, file = costruisci_impianto(ist, "corridoi", quadrati, cfg)
        stato, sol, info_s = risolvi_deterministico(_ModelloSolo(m), float(cfg["dtempo_impianto"]),
                                                    float(cfg["tempo_impianto_s"]), 1, seed, log,
                                                    hint=_hint_impianto(file, partenza, sala.W) if partenza else None)
        info |= {"cpsat": info_s}
        if sol is not None:
            V = _valori(sol)
            g = [{"k": f["tipo"].k, "vert": f["tipo"].vert, "x": V(f["x"]), "y": V(f["y"]),
                  "sedie": {"a": [V(v) for v in f["sedie"]["a"]], "b": [V(v) for v in f["sedie"]["b"]],
                            "testa": V(f["sedie"]["testa"]), "coda": V(f["sedie"]["coda"])}} for f in file if V(f["p"])]
            assegna_accessi(sala, g)
            problemi = controlla_regole(sala, g, regola)
            if problemi:
                note["cp-sat (corridoi)"] = problemi[:2]
            else:
                valide["cp-sat (corridoi)"] = g
    if not valide:
        raise RuntimeError(f"nessuna disposizione delle postazioni passa le regole: {note}")
    nome, siti = max(valide.items(), key=lambda ng: (_valore_impianto(ng[1], cfg), ng[0] == "disegno"))
    siti = [dict(f) for f in siti]
    siti.sort(key=lambda f: (f["y"], f["x"]))
    aggiunte = completa_sedie(sala, siti, regola)
    info |= {"scelta": nome, "valori": {n: _valore_impianto(g, cfg) for n, g in valide.items()}, "scartate": note,
             "postazioni": len(siti), "quadrati": sum(f["k"] for f in siti),
             "sedie": sum(posti_pezzo(f, 0, f["k"] - 1) for f in siti), "sedie_aggiunte_dopo": aggiunte,
             "quadrati_progettati_per": quadrati, "tempo_s": round(time.perf_counter() - t0, 1),
             "disegno": {"file": len(sala._disegno), "quadrati": sum(f["k"] for f in sala._disegno),
                         "sedie": sum(posti_pezzo(f, 0, f["k"] - 1) for f in sala._disegno), "note": sala._disegno_note}}
    say(f"Postazioni: {len(siti)} file ({info['quadrati']} quadrati, {info['sedie']} sedie), scelta {nome} fra "
        f"{', '.join(f'{n} {v}' for n, v in info['valori'].items())} · disegno: {info['disegno']['sedie']} sedie · "
        f"{info['tempo_s']} s")
    return siti, info


@dataclass
class _ModelloSolo:
    m: cp_model.CpModel


def box_accesso(sala: SalaLibera, f: dict) -> tuple[int, int, int, int] | None:
    """Box in celle della zona d'accesso di una fila (sul lato scelto, oltre le sedie); None se non ce l'ha."""
    if not f.get("accesso"):
        return None
    L, S, _ = misure_celle(sala)
    A = _celle(sala.corridoio_cm, sala.griglia_cm)
    corpo, _ = corpo_e_lati(f["k"], f["vert"], L, S)
    s = f["sedie"]
    ua, ub = int(any(s["a"])), int(any(s["b"]))
    sx0, sx1, sy0, sy1 = (s["testa"], s["coda"], ua, ub) if not f["vert"] else (ua, ub, s["testa"], s["coda"])
    for nome, ax, aw, ay, ah in _lati_accesso(f["x"], f["y"], corpo, f["vert"], sx0, sx1, sy0, sy1, S, A):
        if nome == f["accesso"]:
            return ax, ay, ax + aw, ay + ah
    return None


def completa_sedie(sala: SalaLibera, file: list[dict], regola: str = "accesso") -> int:
    """Aggiunge una sedia su ogni lato che ha ancora la zona libera (muri, cose vietate, zone dei fissi, altri tavoli e
    le loro sedie), finché tutti restano raggiungibili. Restituisce quante sedie ha aggiunto."""
    L, S, B = misure_celle(sala)
    W, H = sala.W, sala.H
    pt = sala.prefissi(sala.occ_tavoli)
    prima = [{"a": f["sedie"]["a"][:], "b": f["sedie"]["b"][:], "testa": f["sedie"]["testa"], "coda": f["sedie"]["coda"]}
             for f in file]
    reg = {n: boxes for n, (_, boxes) in enumerate(regioni(sala, file))}
    accessi = [a for a in (box_accesso(sala, f) for f in file) if a]
    Bd, occ1 = spazi(sala, regola)
    pe = sala.prefissi(occ1)
    aggiunte = 0

    def sovrap(a, b):
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

    for n, f in enumerate(file):
        _, lati = corpo_e_lati(f["k"], f["vert"], L, S)
        for lato, q, dx, dy, w, h in lati:
            if _sedia(f["sedie"], lato, q) or lato == f.get("accesso"):
                continue                     # sul lato d'accesso no: la zona d'accesso si sposterebbe
            z = (f["x"] + dx, f["y"] + dy, f["x"] + dx + w, f["y"] + dy + h)
            if not libero_box(pt, W, H, *z) or any(sovrap(z, a) for a in accessi) or \
                    not _libero_fuori(pe, W, H, _allarga(z, Bd)) or \
                    any(sovrap(_allarga(z, 2 * Bd), b) for m2, boxes in reg.items() if m2 != n for b in boxes):
                continue
            _metti(f["sedie"], lato, q, 1)
            reg[n] = reg[n] + [z]
            aggiunte += 1
    if aggiunte and sala.irraggiungibili(regioni(sala, file)):
        for f, s in zip(file, prima):          # le sedie in più chiudono un passaggio: si torna a prima
            f["sedie"] = s
        aggiunte = 0
    return aggiunte


# ---------------------------------------------------------------------------- 2. serata sulle postazioni

@dataclass
class _ModelloPostazioni:
    m: cp_model.CpModel
    voci: list
    siti: list
    u: list = field(default_factory=list)            # sito -> [letterale "c'è il quadrato q"]
    act: dict = field(default_factory=dict)          # (sito, turno) -> {(a, b): letterale}
    a: dict = field(default_factory=dict)            # pid -> [(letterale, posto)], posto ("fila", s, (a, b), k) | ("unita", ch, k)
    o: dict = field(default_factory=dict)            # pid -> [(turno, letterale)]
    seduta: dict = field(default_factory=dict)       # pid -> letterale (1 se obbligatoria)


def _coda_libera(sito: dict, b: int) -> int:
    """La sedia di coda quando l'ultimo quadrato presente è b: dentro la postazione (posto del quadrato che manca) c'è
    sempre; alla fine della postazione solo se la postazione ce l'ha."""
    return 1 if b < sito["k"] - 1 else int(sito["sedie"]["coda"])


def unita_fisse(pia: Piantina) -> list:
    """Unità dei tavoli fissi, come nel modo a tavoli fermi (il lungo con due gruppi); un blocco fisso resta intero."""
    out = []
    for t in pia.tavoli:
        if t.get("tipo") in ("quadrato", "blocco") and not t.get("fisso"):
            continue
        out += [u for u in pia.unita_del(t) if t["tipo"] != "blocco" or u.intero]
    return out


def costruisci_postazioni(ist: Istanza, siti: list[dict], voci: list[_Voce], obiettivo: str = "completo",
                          non_sistemate_fisse: int = 0) -> _ModelloPostazioni:
    sala = sala_libera(ist)
    m = cp_model.CpModel()
    K = len(ist.turni)
    mod = _ModelloPostazioni(m, voci, siti)
    opz = {v.pr.id: _opzioni_turno(ist, v) for v in voci}
    divisioni, cambi = [], []
    pezzi = []                       # (s, (a, b), turno, act, sedie (espressione), sedie al più, ultimo)
    for s, sito in enumerate(siti):
        k, sd = sito["k"], sito["sedie"]
        u = [m.new_bool_var(f"u_{s}_{q}") for q in range(k)]
        for q in range(k - 1):
            m.add_implication(u[q + 1], u[q])
        mod.u.append(u)
        for t in range(K):
            act = {}
            for a in range(k):
                for b in range(a, k):
                    v = m.new_bool_var(f"act_{s}_{a}-{b}.k{t}")
                    m.add_implication(v, u[b])
                    act[(a, b)] = v
            for q in range(k):
                m.add(sum(v for (a, b), v in act.items() if a <= q <= b) == u[q])
            mod.act[(s, t)] = act
            divisioni.append(sum(act.values()) - u[0])
            for (a, b), v in act.items():
                ultimo = u[b] - (u[b + 1] if b + 1 < k else 0)          # b è l'ultimo quadrato presente
                fisse = sum(sd["a"][q] + sd["b"][q] for q in range(a, b + 1)) + (sd["testa"] if a == 0 else 0)
                coda = _coda_libera(sito, b)
                pezzi.append((s, (a, b), t, v, fisse + coda * ultimo, fisse + coda, ultimo))
        if obiettivo == "completo":
            for t in range(1, K):
                prima, ora = mod.act[(s, t - 1)], mod.act[(s, t)]
                diff = []
                for ab in ora:
                    d = m.new_bool_var("")
                    m.add_abs_equality(d, ora[ab] - prima[ab])
                    diff.append(d)
                c = m.new_bool_var(f"camb_{s}.k{t}")
                m.add_max_equality(c, diff)
                cambi.append(c)
    m.add(sum(q for u in mod.u for q in u) <= sala.n_quadrati)
    unita = unita_fisse(ist.piantina)

    occ_p: dict[tuple, list] = {}           # (s, (a, b), turno) -> [(coperti, letterale)]
    occ_u: dict[str, list] = {}
    usi: dict[int, list] = {}
    lungo_grande: dict[str, list] = {}
    lungo_primo: dict[str, list] = {}
    lungo_secondo: dict[str, list] = {}
    vuoti, non_sedute = [], []
    for v in voci:
        pr = v.pr
        olits = []
        for sm, st, k in opz[pr.id]:
            olits.append((k, m.new_bool_var(f"o_{pr.id}_{sm}")))
        mod.o[pr.id] = olits
        seduta = 1 if v.obbligatoria else m.new_bool_var(f"seduta_{pr.id}")
        mod.seduta[pr.id] = seduta
        if not v.obbligatoria:
            non_sedute.append(1 - seduta)
        m.add(sum(ov for _, ov in olits) == seduta)
        mod.a[pr.id] = []
        for k, ov in olits:
            lits = []
            for s, ab, t, _, _, smax, _ in pezzi:
                if t != k or smax < pr.coperti:
                    continue
                av = m.new_bool_var(f"a_{pr.id}_{s}_{ab[0]}-{ab[1]}.k{k}")
                lits.append(av)
                mod.a[pr.id].append((av, ("fila", s, ab, k)))
                occ_p.setdefault((s, ab, k), []).append((pr.coperti, av))
                usi.setdefault(s, []).append(av)
                vuoti.append((posti_nominali(*ab) - pr.coperti) * av)
            for un in unita:
                if un.posti < pr.coperti:
                    continue
                ch = f"{un.chiave}.k{k}"
                av = m.new_bool_var(f"a_{pr.id}_{ch}")
                lits.append(av)
                mod.a[pr.id].append((av, ("unita", un.chiave, k)))
                occ_u.setdefault(ch, []).append(av)
                if un.gruppo == 2:
                    vuoti.append(-pr.coperti * av)
                    lungo_secondo.setdefault(f"t{un.tavolo}.k{k}", []).append(av)
                else:
                    vuoti.append((un.posti - pr.coperti) * av)
                    if un.gruppo == 1:
                        lungo_primo.setdefault(f"t{un.tavolo}.k{k}", []).append(av)
                if un.gruppo is not None and (un.gruppo == 2 or pr.coperti > LUNGO_DUE_GRUPPI):
                    lungo_grande.setdefault(f"t{un.tavolo}.k{k}", []).append(av)
            if lits:
                m.add(sum(lits) == ov)
            else:
                m.add(ov == 0)
    for s, ab, t, act, sedie, _, ultimo in pezzi:
        lst = occ_p.get((s, ab, t), [])
        if not lst:
            m.add(act == 0 if ab[0] > 0 else act <= ultimo)      # un pezzo vuoto è solo la fila intera
            continue
        m.add(sum(c * av for c, av in lst) <= sedie)             # al più una prenotazione, coperti <= sedie del pezzo
        m.add(sum(av for _, av in lst) <= act)
        if ab[0] > 0:                                            # fila divisa: ogni pezzo attivo è occupato
            m.add(sum(av for _, av in lst) == act)
        else:
            m.add(sum(av for _, av in lst) >= act - ultimo)
    for s, u in enumerate(mod.u):                                # una fila messa serve a qualcuno
        m.add(sum(usi.get(s, [])) >= u[0])
    for lst in occ_u.values():
        if len(lst) > 1:
            m.add(sum(lst) <= 1)
    for lst in lungo_grande.values():
        if len(lst) > 1:
            m.add(sum(lst) <= 1)
    for ch, lst in lungo_secondo.items():
        m.add(sum(lst) <= sum(lungo_primo.get(ch, [])))
    pesi = ist.sala.get("pesi", {})
    totale = (int(pesi.get("non_sistemata", 10000)) * (sum(non_sedute) + non_sistemate_fisse)
              + int(pesi.get("posto_vuoto", 10)) * sum(vuoti)
              + int(pesi.get("divisione_blocco", 4)) * sum(divisioni)
              + int(pesi.get("riallestimento", 2)) * sum(cambi))
    if obiettivo == "completo":
        m.minimize(totale)
    elif obiettivo != "nessuno":
        raise ValueError(obiettivo)
    return mod


def _valori(sol: dict):
    def V(x):
        return x if isinstance(x, int) else sol.get(x.name, 0)
    return V


def estrai(mod: _ModelloPostazioni, sol: dict) -> dict:
    """Il piano della serata: quadrati per postazione e chi siede dove."""
    V = _valori(sol)
    lunghezze = [sum(V(q) for q in u) for u in mod.u]
    sedute = {}
    for v in mod.voci:
        for av, posto in mod.a[v.pr.id]:
            if V(av):
                sedute[v.pr.id] = posto
                break
    return {"lunghezze": lunghezze, "sedute": sedute}


def hint_piano(mod: _ModelloPostazioni, piano: dict | None) -> dict:
    """Hint completo dal piano precedente (quadrati, pezzi, sedute, opzioni): una soluzione intera per le accettate."""
    if not piano:
        return {}
    h = {}
    for s, u in enumerate(mod.u):
        n = piano["lunghezze"][s] if s < len(piano["lunghezze"]) else 0
        for q, var in enumerate(u):
            h[var.name] = int(q < n)
        for (s2, t), act in mod.act.items():
            if s2 != s:
                continue
            occ = sorted(tuple(p[2]) for p in piano["sedute"].values() if p[0] == "fila" and p[1] == s and p[3] == t)
            attivi = set(occ) if len(occ) > 1 else ({(0, n - 1)} if n else set())
            for ab, var in act.items():
                h[var.name] = int(ab in attivi)
    for v in mod.voci:
        pid = v.pr.id
        p = piano["sedute"].get(pid)
        for av, posto in mod.a[pid]:
            h[av.name] = int(p is not None and tuple(posto[:2]) == tuple(p[:2]) and tuple(posto[2:]) == tuple(p[2:]))
        for k, ov in mod.o[pid]:
            h[ov.name] = int(p is not None and p[-1] == k)
        if not isinstance(mod.seduta[pid], int):
            h[mod.seduta[pid].name] = int(p is not None)
    return h


def risolvi_deterministico(mod, dtempo: float, tempo_max_s: float, worker: int, seed: int, log: bool,
                           hint: dict | None = None) -> tuple[str, dict | None, dict]:
    """Come `_risolvi_modello`; con `worker` = 1 è ripetibile (limite in tempo deterministico di CP-SAT: stessi dati e
    seed, stesso risultato) e il limite in secondi è solo una rete di sicurezza. `interleave_search` con più worker va
    in crash con OR-Tools 9.15 su questi modelli (provato il 28/10/2026)."""
    import ortools
    m = mod.m
    n_hint = 0
    if hint:
        for idx, vp in enumerate(m.proto.variables):
            if vp.name in hint:
                m.add_hint(m.get_int_var_from_proto_index(idx), hint[vp.name])
                n_hint += 1
    solver = cp_model.CpSolver()
    par = solver.parameters
    par.num_workers, par.random_seed, par.log_search_progress = worker, seed, log
    if worker == 1:                          # un worker e tempo deterministico: ripetibile
        par.max_deterministic_time = dtempo
    par.max_time_in_seconds = tempo_max_s
    t0 = time.perf_counter()
    stato = solver.solve(m)
    tempo = time.perf_counter() - t0
    nome = solver.status_name(stato)
    info = {"stato": nome, "obiettivo": None, "bound": None, "gap_pct": None, "tempo_s": round(tempo, 2),
            "tempo_deterministico": round(solver.deterministic_time, 2), "limite_deterministico": dtempo,
            "limite_s": tempo_max_s, "ripetibile": worker == 1 and tempo < tempo_max_s, "worker": worker, "seed": seed,
            "versione_ortools": ortools.__version__, "variabili": len(m.proto.variables),
            "vincoli": len(m.proto.constraints), "variabili_con_hint": n_hint}
    if stato == cp_model.MODEL_INVALID:
        raise RuntimeError(f"modello non valido: {m.validate()}")
    if stato not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return nome, None, info
    info["obiettivo"] = int(round(solver.objective_value))
    info["bound"] = int(round(solver.best_objective_bound))
    piano = {vp.name: int(v) for vp, v in zip(m.proto.variables, solver.response_proto.solution)}
    return nome, piano, info


def _risolvi(mod, dtempo, tempo_s, worker, seed, log, piano):
    return risolvi_deterministico(mod, dtempo, tempo_s, worker, seed, log, hint=hint_piano(mod, piano))


# ---------------------------------------------------------------------------- impossibilità per conteggio

def impossibile_per_conteggio_libera(ist: Istanza, coperti: list[int]) -> bool:
    """Condizione SUFFICIENTE di impossibilità in un turno, in qualunque disposizione: anche mettendo sui tavoli fissi
    le prenotazioni che "costano" più quadrati, le altre chiedono più quadrati dell'inventario (una prenotazione da c su
    una fila usa almeno max(1, ceil((c - 2) / 2)) quadrati) o più posti di una fila da k_max."""
    sala = sala_libera(ist)
    pia: Piantina = ist.piantina
    kmax = sala.k_max
    semplici, lunghi = [], []
    for t in pia.tavoli:
        if t.get("tipo") in ("quadrato", "blocco") and not t.get("fisso"):
            continue
        (lunghi if t["tipo"] == "lungo" else semplici).append(int(t["posti"]))

    def quadrati(c):
        return max(1, -(-(c - 2) // 2))

    def prova(capienze):
        liberi = sorted(capienze)
        resto = []
        for c in sorted(coperti, reverse=True):
            i = next((n for n, x in enumerate(liberi) if x >= c), None)
            if i is None:
                resto.append(c)
            else:
                liberi.pop(i)
        if any(c > 2 * kmax + 2 for c in resto):
            return False
        return sum(quadrati(c) for c in resto) <= sala.n_quadrati

    combinazioni = [[]]
    for p in lunghi:                                 # il lungo: un gruppo fino ai suoi posti o due fino a 8
        combinazioni = [c + [p] for c in combinazioni] + [c + [min(p, LUNGO_DUE_GRUPPI)] * 2 for c in combinazioni]
    return not any(prova(semplici + c) for c in combinazioni)


# ---------------------------------------------------------------------------- decisioni e piantina finale

def _prova_turno(ist: Istanza, siti: list[dict], accettate: list[_Voce], voce: _Voce, piano: dict | None, cfg: dict,
                 worker: int, seed: int, log: bool) -> tuple[str, dict | None]:
    """C'è posto per `voce` (un turno) con le accettate, sulle postazioni? (stato, piano); stato "AMMISSIBILE",
    "INFEASIBLE" (dimostrato), "CONTEGGIO" (dimostrato a priori) o "UNKNOWN"."""
    k = ist.turno_da_passo(voce.opzioni[0][1])
    cop = [v.pr.coperti for v in accettate if ist.turno_da_passo(v.opzioni[0][1]) == k] + [voce.pr.coperti]
    if impossibile_per_conteggio_libera(ist, cop):
        return "CONTEGGIO", None
    mod = costruisci_postazioni(ist, siti, accettate + [voce], obiettivo="nessuno")
    stato, sol, _ = _risolvi(mod, float(cfg["dtempo_decisione"]), float(cfg["tempo_decisione_s"]),
                             int(cfg.get("worker_serata", worker)), seed, log, piano)
    if sol is None:
        return stato, None
    return "AMMISSIBILE", estrai(mod, sol)


def accetta_in_ordine_libera(ist: Istanza, worker: int | None = None, seed: int | None = None, log: bool = False,
                             avanzamento: Callable[[str], None] | None = None, tempi: dict | None = None) -> dict:
    """Progetta le postazioni, rigioca le prenotazioni in ordine di `prenotata_il` (se il turno chiesto è pieno e la
    politica non è "mai", propone l'altro turno) e alla fine ottimizza la piantina della serata."""
    if not ist.turni or ist.piantina is None:
        raise ErroreDati("la disposizione libera vale solo per la sala vera a turni")
    cfg = impostazioni_libera(ist) | (tempi or {})
    worker, seed = _parametri(ist, worker, seed)
    mancanti = [p.id for p in ist.prenotazioni if not p.prenotata_il]
    if mancanti:
        raise ErroreDati(f"accettazione in ordine di arrivo: manca prenotata_il per {', '.join(mancanti)}")
    say = avanzamento or (lambda _msg: None)
    t_inizio = time.perf_counter()
    sala = sala_libera(ist)
    say(f"Sala libera: {sala.n_quadrati} quadrati mobili, {len(sala.fissi)} tavoli fissi, griglia {sala.griglia_cm} cm, "
        f"tipi di fila {', '.join(f'{t.nome}×{t.n}' for t in sala._tipi)} · geometria in "
        f"{round(time.perf_counter() - t_inizio, 1)} s")
    t0 = time.perf_counter()
    siti, info_imp = progetta_postazioni(ist, cfg, worker, seed, log, say)
    info_imp["tempo_totale_s"] = round(time.perf_counter() - t0, 1)
    regola = {"corridoi": "tra due tavoli qualsiasi e tra un tavolo e la zona sedie dei fissi",
              "corridoi_muri": "tra due tavoli qualsiasi, tra un tavolo e la zona sedie dei fissi, e lungo muri e ostacoli",
              "accesso": "su almeno un lato di ogni tavolo"}.get(info_imp.get("regola"), "")
    for m in sala.misure:
        if m["cosa"] == "corridoio per il personale" and regola and regola not in m["valore"]:
            m["valore"] = m["valore"].replace("(", f"({regola}; ", 1)
    politica = ist.cliente_accetta_proposta
    cap_max = max([2 * sala.k_max + 2] + [f.posti for f in sala.fissi])
    accettate: list[_Voce] = []
    rifiutate: list[dict] = []
    registro: list[dict] = []
    piano: dict | None = None
    for n, pr in enumerate(ist.in_ordine_di_arrivo(), start=1):
        k_chiesto = ist.turno_della(pr)
        rec = {"ordine": n, "id": pr.id, "nome": pr.nome, "coperti": pr.coperti,
               "orario_richiesto": min_a_hhmm(pr.orario_min), "prenotata_il": pr.prenotata_il,
               "esito": None, "orario_promesso": None, "spostamento_min": None, "motivo": None,
               "stato_solver": None, "decisione": None, "spostamento_minimo_dimostrato": None,
               "spareggio": None, "proposta_prima": None, "proposta_dopo": None, "proposta_principale": None,
               "proposte_piu_vicine_dimostrate": None, "esiti_proposte": None, "tempo_s": 0.0,
               "turno_richiesto": ist.turni[k_chiesto].nome, "turno_promesso": None, "turno_proposto": None}
        t0 = time.perf_counter()
        motivo = None

        def voce_turno(kk):
            return _Voce(pr, [(ist.turni[kk].inizio_min - pr.orario_min, ist.passo_turno(kk))], True)
        if pr.coperti > cap_max:
            rec.update(decisione="impossibile (a priori)", stato_solver="non necessario")
            motivo = MOTIVO_TROPPO_GRANDE
        else:
            stato, nuovo = _prova_turno(ist, siti, accettate, voce_turno(k_chiesto), piano, cfg, worker, seed, log)
            rec["stato_solver"] = f"{ist.turni[k_chiesto].nome} {stato}"
            if nuovo is not None:
                accettate.append(voce_turno(k_chiesto))
                piano = nuovo
                rec.update(esito="accettata", decisione="ammissibile", spostamento_min=0, turno_promesso=rec["turno_richiesto"],
                           orario_promesso=min_a_hhmm(ist.turni[k_chiesto].inizio_min))
            else:
                deciso = stato in ("INFEASIBLE", "CONTEGGIO")
                if politica == MAI:
                    rec["decisione"] = "impossibile (dimostrato)" if deciso else "non decisa (tempo scaduto)"
                    motivo = MOTIVO_TURNO_PIENO if deciso else MOTIVO_TEMPO_SCADUTO
                else:
                    trovate, esiti, tutti_decisi = {}, [], deciso
                    for direz, cand in (("prima", range(k_chiesto - 1, -1, -1)), ("dopo", range(k_chiesto + 1, len(ist.turni)))):
                        for kk in cand:
                            st2, nuovo2 = _prova_turno(ist, siti, accettate, voce_turno(kk), piano, cfg, worker, seed, log)
                            esiti.append(f"{ist.turni[kk].nome} {st2}")
                            if nuovo2 is not None:
                                trovate[direz] = (kk, nuovo2)
                                break
                            tutti_decisi = tutti_decisi and st2 in ("INFEASIBLE", "CONTEGGIO")
                    rec["esiti_proposte"] = " | ".join(esiti) or None
                    if not trovate:
                        rec["decisione"] = "impossibile (dimostrato)" if tutti_decisi else "non decisa (tempo scaduto)"
                        motivo = MOTIVO_TURNI_PIENI if tutti_decisi else MOTIVO_TEMPO_SCADUTO
                    else:
                        for direz, (kk, _) in trovate.items():
                            rec[f"proposta_{direz}"] = min_a_hhmm(ist.turni[kk].inizio_min)
                        a_parita_dopo = ist.proposta_a_parita == "dopo"
                        direz, (kk, nuovo2) = min(trovate.items(), key=lambda it: (
                            abs(ist.turni[it[1][0]].inizio_min - pr.orario_min), (it[0] == "dopo") != a_parita_dopo))
                        rec.update(proposta_principale=min_a_hhmm(ist.turni[kk].inizio_min),
                                   turno_proposto=ist.turni[kk].nome, decisione="ammissibile su proposta",
                                   proposte_piu_vicine_dimostrate={"prima": None, "dopo": None})
                        if ist.accetta_proposta(ist.turni[kk].inizio_min - pr.orario_min):
                            accettate.append(voce_turno(kk))
                            piano = nuovo2
                            rec.update(esito="accettata su proposta", spostamento_min=0, turno_promesso=ist.turni[kk].nome,
                                       orario_promesso=min_a_hhmm(ist.turni[kk].inizio_min))
                        else:
                            motivo = MOTIVO_PROPOSTA_RIFIUTATA
                            rec["decisione"] = "proposta rifiutata dal cliente"
        if motivo is not None:
            rec.update(esito="rifiutata", motivo=motivo)
            rifiutate.append(_non_sistemata(ist, pr, ist.opzioni(pr), motivo))
        rec["tempo_s"] = round(time.perf_counter() - t0, 2)
        registro.append(rec)
        dettaglio = {"accettata": f" nel {rec['turno_promesso']} turno",
                     "accettata su proposta": f" nel {rec['turno_promesso']} turno (chiesto il {rec['turno_richiesto']})"
                     }.get(rec["esito"], f" ({rec['motivo']})")
        say(f"{n:2d}. {pr.prenotata_il} {pr.nome} ×{pr.coperti} {rec['orario_richiesto']}: {rec['esito']}{dettaglio} "
            f"[{rec['stato_solver']}{' | ' + rec['esiti_proposte'] if rec['esiti_proposte'] else ''}, {rec['tempo_s']} s]")

    # ------------------------------------------------------------ piantina finale
    t0 = time.perf_counter()
    base = {"sala": ist.sala.get("nome", ""), "serata": ist.serata.get("serata", ""),
            "modalita": {"accettazione": ORDINE_DI_ARRIVO, "disposizione": LIBERA, "cliente_accetta_proposta": politica,
                         "proposta_max_distanza_min": ist.proposta_max_distanza_min,
                         "proposta_a_parita": ist.proposta_a_parita, **modalita_turni(ist)}}
    info = {"stato": "non necessario", "obiettivo": 0, "bound": 0, "gap_pct": 0.0, "tempo_s": 0.0,
            "origine": "nessuna prenotazione accettata"}
    finale = {"lunghezze": [0] * len(siti), "sedute": {}}
    if accettate:
        mod = costruisci_postazioni(ist, siti, accettate, non_sistemate_fisse=len(rifiutate))
        stato, sol, info = _risolvi(mod, float(cfg["dtempo_piantina"]), float(cfg["tempo_piantina_s"]),
                                    int(cfg.get("worker_serata", worker)), seed, log, piano)
        info["origine"] = "solver"
        if sol is None:
            finale, info["origine"] = piano, "ultimo piano di accettazione (il solver non ha restituito soluzioni)"
        else:
            finale = estrai(mod, sol)
        if len(finale["sedute"]) != len(accettate):
            raise RuntimeError("piantina finale: non tutte le accettate sono sedute")
    info["tempo_piantina_s"] = round(time.perf_counter() - t0, 2)
    tavoli, assegnazioni, file = _tavoli_e_assegnazioni(ist, siti, finale, accettate)
    comp = componenti_libera(ist, tavoli, assegnazioni, rifiutate)
    if info.get("origine") == "solver":
        info["obiettivo_coerente_con_componenti"] = comp["totale"] == info["obiettivo"]
    else:
        info["obiettivo"] = comp["totale"]
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
        "tempi_limite_s": {k: cfg[k] for k in ("tempo_impianto_s", "tempo_decisione_s", "tempo_piantina_s")},
        "limiti_deterministici": {k: cfg[k] for k in ("dtempo_impianto", "dtempo_decisione", "dtempo_piantina")},
    }
    g = sala.griglia_cm
    geometria = {"lato_quadrato_cm": sala.lato_cm, "sedie_cm": sala.sedie_cm, "corridoio_cm": sala.corridoio_cm,
                 "griglia_cm": g, "k_max": sala.k_max, "quadrati_mobili": sala.n_quadrati,
                 "quadrati_da": [{"tavolo": t, "quadrati": k} for t, k in sala.origine_quadrati],
                 "tolleranza_cm": sala.tolleranza_cm, "cm_per_unita": sala.cpu,
                 "file_per_tipo": {t.nome: t.n for t in sala._tipi},
                 "irraggiungibili_secondo_il_motore": sorted(sala.irraggiungibili(regioni(sala, file))),
                 "corridoi_di_servizio_cm": [[[i * g, j * g] for i, j in punti] for punti in sala.percorsi_servizio.values()]}
    L, _, _ = misure_celle(sala)
    postazioni = [{"x_cm": f["x"] * g, "y_cm": f["y"] * g, "moduli": f["k"],
                   "orientamento": "verticale" if f["vert"] else "orizzontale",
                   "larghezza_cm": (1 if f["vert"] else f["k"]) * sala.lato_cm,
                   "altezza_cm": (f["k"] if f["vert"] else 1) * sala.lato_cm,
                   "quadrati_usati": finale["lunghezze"][s]} for s, f in enumerate(siti)]
    return base | {"solver": info, "impianto": info_imp, "accettazione": riepilogo, "registro": registro,
                   "obiettivo_componenti": comp, "tavoli": tavoli, "assegnazioni": assegnazioni,
                   "non_sistemate": rifiutate, "postazioni": postazioni, "geometria": geometria,
                   "misure_usate": sala.misure}


def _tavoli_e_assegnazioni(ist: Istanza, siti: list[dict], piano: dict, accettate: list[_Voce]) -> tuple[list, list, list]:
    """Tavoli della soluzione (fissi, poi le file messe), assegnazioni, e le file come dizionari in celle."""
    sala = sala_libera(ist)
    g = sala.griglia_cm
    nomi = [t.nome for t in ist.turni]
    tavoli = [{"id": f.id, "tipo": f.tipo, "posti": f.posti, "fisso": True} for f in sala.fissi]
    file, nome_di = [], {}
    for s, sito in enumerate(siti):
        n = piano["lunghezze"][s]
        if not n:
            continue
        sd = sito["sedie"]
        f = {"k": n, "vert": sito["vert"], "x": sito["x"], "y": sito["y"],
             "sedie": {"a": sd["a"][:n], "b": sd["b"][:n], "testa": sd["testa"], "coda": _coda_libera(sito, n - 1)}}
        nome_di[s] = f"F{len(file) + 1}"
        file.append(f)
        part = {}
        for t, nome in enumerate(nomi):
            occ = sorted(tuple(p[2]) for p in piano["sedute"].values() if p[0] == "fila" and p[1] == s and p[3] == t)
            part[nome] = [list(p) for p in occ] if len(occ) > 1 else [[0, n - 1]]
        tavoli.append({"id": nome_di[s], "tipo": "fila", "moduli": n, "orientamento": "verticale" if f["vert"] else "orizzontale",
                       "x_cm": f["x"] * g, "y_cm": f["y"] * g,
                       "larghezza_cm": (1 if f["vert"] else n) * sala.lato_cm, "altezza_cm": (n if f["vert"] else 1) * sala.lato_cm,
                       "sedie": {"lato_a": f["sedie"]["a"], "lato_b": f["sedie"]["b"], "testa": f["sedie"]["testa"],
                                 "coda": f["sedie"]["coda"]},
                       "posti": posti_pezzo(f, 0, n - 1), "posti_nominali": posti_nominali(0, n - 1), "partizioni": part,
                       "postazione": s})
    per_id = {v.pr.id: v for v in accettate}
    unita = {u.chiave: u for u in unita_fisse(ist.piantina)}
    file_di = {s: f for s, f in zip([s for s in range(len(siti)) if piano["lunghezze"][s]], file)}
    assegnazioni = []
    for pid, p in piano["sedute"].items():
        pr = per_id[pid].pr
        tu = ist.turni[p[-1]]
        r = {"id": pr.id, "nome": pr.nome, "coperti": pr.coperti, "orario_richiesto": min_a_hhmm(pr.orario_min),
             "orario_assegnato": min_a_hhmm(tu.inizio_min), "spostamento_min": 0, "fine": min_a_hhmm(tu.fine_min),
             "note": pr.note, "turno": tu.nome, "turno_richiesto": ist.turni[ist.turno_della(pr)].nome}
        if p[0] == "fila":
            a, b = p[2]
            r.update(tavolo=nome_di[p[1]], quadrati=[a, b], gruppo=None, posti_tavolo=posti_pezzo(file_di[p[1]], a, b),
                     posti_nominali=posti_nominali(a, b))
        else:
            u = unita[p[1]]
            r.update(tavolo=u.tavolo, quadrati=None, gruppo=u.gruppo, posti_tavolo=u.posti)
        assegnazioni.append(r)
    ordine_t = {t["id"]: n for n, t in enumerate(tavoli)}
    assegnazioni.sort(key=lambda r: (r["orario_assegnato"], ordine_t[r["tavolo"]], (r["quadrati"] or [0])[0], r["gruppo"] or 0))
    return tavoli, assegnazioni, file


def componenti_libera(ist: Istanza, tavoli: list, assegnazioni: list, non_sistemate: list) -> dict:
    """Componenti dell'obiettivo ricalcolate dalla soluzione (stesse del modello)."""
    pesi = ist.sala.get("pesi", {})
    p_ns, p_pv = int(pesi.get("non_sistemata", 10000)), int(pesi.get("posto_vuoto", 10))
    p_div, p_ri = int(pesi.get("divisione_blocco", 4)), int(pesi.get("riallestimento", 2))
    lunghi = {str(t["id"]): int(t["posti"]) for t in ist.piantina.tavoli if t["tipo"] == "lungo"}
    vuoti = 0
    usati: dict[tuple, int] = {}
    for r in assegnazioni:
        if r["tavolo"] in lunghi:
            usati[(r["tavolo"], r["turno"])] = usati.get((r["tavolo"], r["turno"]), 0) + r["coperti"]
        else:
            vuoti += r.get("posti_nominali", r["posti_tavolo"]) - r["coperti"]
    vuoti += sum(lunghi[t] - c for (t, _), c in usati.items())
    nomi = [t.nome for t in ist.turni]
    div = sum(len(t["partizioni"][n]) - 1 for t in tavoli if t.get("partizioni") for n in nomi)
    camb = sum(1 for t in tavoli if t.get("partizioni") for a, b in zip(nomi, nomi[1:])
               if t["partizioni"][a] != t["partizioni"][b])
    per_turno = {n: sum(r["coperti"] for r in assegnazioni if r["turno"] == n) for n in nomi}
    comp = {
        "non_sistemate": {"numero": len(non_sistemate), "costo": p_ns * len(non_sistemate)},
        "posti_vuoti": {"posti": vuoti, "costo": p_pv * vuoti,
                        "nota": "tavoli mobili: posti nominali del pezzo (2 per quadrato + 2) meno i coperti"},
        "spostamenti": {"quarti_d_ora": 0, "costo": 0},
        "accostamenti": {"moduli_oltre_il_primo": 0, "costo": 0},
        "picco_cucina": {"coperti_oltre_soglia": 0, "soglia": 0, "costo": 0, "coperti_per_orario": per_turno,
                         "disattivato": "turni"},
        "divisioni_blocchi": {"numero": div, "costo": p_div * div},
        "riallestimenti": {"numero": camb, "costo": p_ri * camb},
    }
    comp["totale"] = sum(v["costo"] for v in comp.values())
    return comp
