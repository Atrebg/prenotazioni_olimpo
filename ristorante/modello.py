"""Modello CP-SAT: disposizione dei tavoli + assegnazione delle prenotazioni, risolte insieme.

Accettazione (config `accettazione`):
- "tutte_insieme": una sola ottimizzazione su tutte le prenotazioni; le non sistemate pagano un peso;
- "ordine_di_arrivo": le prenotazioni si rigiocano nell'ordine di `prenotata_il`. Ognuna è accettata solo se
  esiste un piano con tutte quelle accettate prima (obbligatorie, orario congelato) più lei, con il suo orario
  scelto tra gli spostamenti ammessi: prima lo spostamento minimo, poi il resto dell'obiettivo. Il tavolo NON
  si congela. Alla fine la "piantina delle 18" ottimizza la disposizione con tutti gli orari congelati.

Disposizione (config `disposizione`):
- "fissa": ogni tavolo esiste per tutta la serata; un solo NoOverlap2D sugli ingombri;
- "variabile": ogni slot ha un intervallo di esistenza [a_s, b_s] su passi da 15 min; due slot possono
  occupare lo stesso spazio solo se non esistono nello stesso momento (disgiunzione a coppie su x, y o tempo);
  moduli e tondi in uso in ogni istante entro l'inventario (cumulativi); peso per ogni slot montato dopo
  l'apertura ("riallestimento").

Modalità a turni (`turni` nella sala): il modello è in `modello_turni.py` (ogni turno è un problema di sola
sistemazione); `_costruisci`, `_estrai` e il conteggio dei moduli passano lì da soli.

Variabili (G = cella di griglia, P = passo orario):
- slot a moduli (opzionali): presenza p, forma b[f] (k, orientamento), angolo dell'ingombro x, y,
  dimensioni w, h = somma b[f]*dimensione(f); slot tondi: presenza, x, y;
- in "variabile": inizio a, fine b dell'esistenza, riallestimento r = (a > 0);
- prenotazioni: a[i,s] (i seduta su s), o[i,d] (spostamento d scelto), inizio S[i].
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import ortools
from ortools.sat.python import cp_model

from .dati import (
    FISSA,
    MAI,
    MOTIVO_FUORI_ORARIO,
    MOTIVO_NESSUNA_SOLUZIONE,
    MOTIVO_PROPOSTA_RIFIUTATA,
    MOTIVO_SALA_PIENA,
    MOTIVO_SALA_PIENA_ACCETTATE,
    MOTIVO_TEMPO_SCADUTO,
    MOTIVO_TROPPO_GRANDE,
    MOTIVO_TURNI_PIENI,
    MOTIVO_TURNO_PIENO,
    ORDINE_DI_ARRIVO,
    TUTTE_INSIEME,
    VARIABILE,
    ErroreDati,
    Forma,
    Istanza,
    Prenotazione,
    min_a_hhmm,
    motivo_nessun_orario,
)

# ---------------------------------------------------------------------------- strutture


@dataclass
class _Voce:
    """Una prenotazione dentro un modello."""
    pr: Prenotazione
    opzioni: list[tuple[int, int]]       # (spostamento_min, inizio in passi) ammessi
    obbligatoria: bool                   # True: deve sedersi (accettata / in valutazione)


@dataclass
class _Slot:
    chiave: str                          # "m3" (moduli) / "t1" (tondo): nomi stabili per gli hint
    tipo: str
    p: Any
    x: Any
    y: Any
    forme: list[tuple[Forma, Any]]
    capienza: Any
    moduli: Any
    cap_max: int
    a: Any = 0                           # inizio esistenza (passi)
    b: Any = 0                           # fine esistenza (passi, esclusa)
    riall: Any = 0                       # 1 se montato dopo l'apertura


@dataclass
class _Modello:
    m: cp_model.CpModel
    slots: list[_Slot]
    voci: list[_Voce]
    a: dict = field(default_factory=dict)        # (pid, chiave) -> BoolVar
    o: dict = field(default_factory=dict)        # (pid, spostamento_min) -> BoolVar
    disposizione: str = FISSA
    turni: bool = False                          # modello a turni (modello_turni.py)
    info_slot: dict = field(default_factory=dict)    # a turni: chiave -> (tipo "m"/"t", indice, turno | None)
    turni_slot: dict = field(default_factory=dict)   # a turni: chiave -> turni in cui lo slot esiste


def _pesi(ist: Istanza) -> dict:
    p = ist.sala["pesi"]
    return {
        "non_sistemata": int(p["non_sistemata"]),
        "posto_vuoto": int(p["posto_vuoto"]),
        "spostamento_per_quarto": int(p["spostamento_per_quarto"]),
        "accostamento_per_modulo": int(p["accostamento_per_modulo"]),
        "picco_cucina_per_coperto": int(p["picco_cucina_per_coperto"]),
        "riallestimento": int(p.get("riallestimento", 20)),
    }


def costo_spostamento(peso_per_quarto: int, spostamento_min: int) -> int:
    """Costo di uno spostamento: peso per ogni quarto d'ora (|spostamento| / 15 min)."""
    return round(peso_per_quarto * abs(spostamento_min) / 15)


def _cfg_solver(ist: Istanza, chiave: str, default):
    return ist.sala.get("solver", {}).get(chiave, default)


# ---------------------------------------------------------------------------- costruzione del modello

def _costruisci(ist: Istanza, voci: list[_Voce], disposizione: str, obiettivo: str = "completo",
                non_sistemate_fisse: int = 0, proiezioni: bool = True, rinforzo: bool = True) -> _Modello:
    """Costruisce il modello CP-SAT per le prenotazioni `voci`.

    obiettivo "completo": somma pesata di tutte le componenti; "nessuno": sola ammissibilità (decisioni di
    accettazione). `non_sistemate_fisse` aggiunge al costo le prenotazioni già rifiutate (costante, per la
    piantina finale). `rinforzo`: vincoli ridondanti per dimostrare prima l'impossibilità."""
    if ist.turni:
        from .modello_turni import costruisci_turni
        return costruisci_turni(ist, voci, disposizione, obiettivo, non_sistemate_fisse, proiezioni, rinforzo)
    pesi = _pesi(ist)
    soglia_picco = int(ist.sala.get("picco_cucina_soglia_coperti", 30))
    m = cp_model.CpModel()
    W, H = ist.larghezza_g, ist.altezza_g
    T, R, Z = ist.fine_passi, ist.riapp_passi, ist.orizzonte_passi
    variabile = disposizione == VARIABILE
    mod = _Modello(m, [], voci, disposizione=disposizione)

    # ------------------------------------------------------------ quanti slot
    forme, ft = ist.forme_moduli, ist.forma_tondo
    cap_mod = max((f.capienza for f in forme), default=0)
    n_el_mod = sum(1 for v in voci if v.opzioni and v.pr.coperti <= cap_mod)
    n_el_tondo = sum(1 for v in voci if v.opzioni and ft is not None and v.pr.coperti <= ft.capienza)
    base_m = ist.slot_variabile_moduli if variabile else ist.n_moduli
    base_t = ist.slot_variabile_tondi if variabile else ist.n_tondi
    # ogni slot presente ospita almeno una prenotazione: più slot delle prenotazioni non servono mai
    n_m = min(base_m, n_el_mod) if forme else 0
    n_t = min(base_t, n_el_tondo) if ft is not None else 0

    # ------------------------------------------------------------ geometria
    # ostacoli e corsie: la loro unione scomposta in rettangoli disgiunti (NoOverlap2D vieta anche la
    # sovrapposizione fissi-fissi, es. il pilastro dentro la corsia centrale)
    fx_box = [m.new_fixed_size_interval_var(r.x0, r.x1 - r.x0, f"fx_{r.nome}") for r in ist.fissi_disgiunti_g]
    fy_box = [m.new_fixed_size_interval_var(r.y0, r.y1 - r.y0, f"fy_{r.nome}") for r in ist.fissi_disgiunti_g]
    box: dict[str, tuple] = {}          # chiave -> (x_iv, y_iv, x, xe, y, ye, w, h)
    esistenza: dict[str, Any] = {}      # chiave -> intervallo di esistenza (solo variabile)

    def _esistenza(k: str, p) -> tuple:
        if not variabile:
            return 0, Z, 0
        a_s = m.new_int_var(0, T - 1, f"ea_{k}")
        b_s = m.new_int_var(1, Z, f"eb_{k}")
        ln = m.new_int_var(1, Z, f"el_{k}")
        m.add(b_s == a_s + ln)
        esistenza[k] = m.new_optional_interval_var(a_s, ln, b_s, p, f"ie_{k}")
        m.add(a_s == 0).only_enforce_if(~p)
        m.add(b_s == Z).only_enforce_if(~p)
        r = m.new_bool_var(f"r_{k}")             # riallestimento: montato dopo l'apertura
        m.add(a_s <= (T - 1) * r)
        m.add(a_s >= r)
        m.add_implication(r, p)
        return a_s, b_s, r

    if n_m:
        min_l = min(f.ingombro_l for f in forme)
        min_h = min(f.ingombro_h for f in forme)
        dom_l = cp_model.Domain.from_values(sorted({0} | {f.ingombro_l for f in forme}))
        dom_h = cp_model.Domain.from_values(sorted({0} | {f.ingombro_h for f in forme}))
        for s in range(n_m):
            k = f"m{s}"
            p = m.new_bool_var(f"p_{k}")
            bs = [(f, m.new_bool_var(f"b_{k}_{f.nome}")) for f in forme]
            m.add(sum(b for _, b in bs) == p)
            x = m.new_int_var(0, W - min_l, f"x_{k}")
            y = m.new_int_var(0, H - min_h, f"y_{k}")
            w = m.new_int_var_from_domain(dom_l, f"w_{k}")
            h = m.new_int_var_from_domain(dom_h, f"h_{k}")
            m.add(w == sum(f.ingombro_l * b for f, b in bs))
            m.add(h == sum(f.ingombro_h * b for f, b in bs))
            xe = m.new_int_var(0, W, f"xe_{k}")
            ye = m.new_int_var(0, H, f"ye_{k}")
            m.add(xe == x + w)                  # dentro la sala
            m.add(ye == y + h)
            box[k] = (m.new_optional_interval_var(x, w, xe, p, f"ix_{k}"),
                      m.new_optional_interval_var(y, h, ye, p, f"iy_{k}"), x, xe, y, ye, w, h)
            if proiezioni:  # ridondante: x e y tra le posizioni libere della forma nella sala vuota
                for f, b in bs:
                    xs, ys = ist.posizioni[f.nome]
                    m.add_linear_expression_in_domain(x, cp_model.Domain.from_values(xs)).only_enforce_if(b)
                    m.add_linear_expression_in_domain(y, cp_model.Domain.from_values(ys)).only_enforce_if(b)
            m.add(x == 0).only_enforce_if(~p)    # slot assente: posizione fissata (meno soluzioni equivalenti)
            m.add(y == 0).only_enforce_if(~p)
            a_s, b_s, r = _esistenza(k, p)
            mod.slots.append(_Slot(k, "moduli", p, x, y, bs, sum(f.capienza * b for f, b in bs),
                                   sum(f.moduli * b for f, b in bs), cap_mod, a_s, b_s, r))
    mod_slots = [sl for sl in mod.slots if sl.tipo == "moduli"]
    # rottura delle simmetrie (gli slot a moduli sono intercambiabili, tutto è indicizzato per slot):
    # k non crescente (quindi presenza non crescente), a parità di k x non decrescente
    for s1, s2 in zip(mod_slots, mod_slots[1:]):
        m.add(s1.moduli >= s2.moduli)
        m.add(s1.p >= s2.p)
        uguali = m.new_bool_var(f"ugk_{s1.chiave}")
        m.add(s1.moduli == s2.moduli).only_enforce_if(uguali)
        m.add(s1.moduli != s2.moduli).only_enforce_if(~uguali)
        m.add(s1.x <= s2.x).only_enforce_if(uguali)

    tondi: list[_Slot] = []
    for r_ in range(n_t):
        k = f"t{r_}"
        p = m.new_bool_var(f"p_{k}")
        x = m.new_int_var(0, W - ft.ingombro_l, f"x_{k}")
        y = m.new_int_var(0, H - ft.ingombro_h, f"y_{k}")
        box[k] = (m.new_optional_fixed_size_interval_var(x, ft.ingombro_l, p, f"ix_{k}"),
                  m.new_optional_fixed_size_interval_var(y, ft.ingombro_h, p, f"iy_{k}"),
                  x, x + ft.ingombro_l, y, y + ft.ingombro_h, ft.ingombro_l, ft.ingombro_h)
        if proiezioni:
            xs, ys = ist.posizioni[ft.nome]
            m.add_linear_expression_in_domain(x, cp_model.Domain.from_values(xs)).only_enforce_if(p)
            m.add_linear_expression_in_domain(y, cp_model.Domain.from_values(ys)).only_enforce_if(p)
        m.add(x == 0).only_enforce_if(~p)
        m.add(y == 0).only_enforce_if(~p)
        a_s, b_s, r = _esistenza(k, p)
        sl = _Slot(k, "tondo", p, x, y, [(ft, p)], ft.capienza * p, 0, ft.capienza, a_s, b_s, r)
        mod.slots.append(sl)
        tondi.append(sl)
    for s1, s2 in zip(tondi, tondi[1:]):
        m.add(s1.p >= s2.p)
        m.add(s1.x <= s2.x).only_enforce_if(s2.p)

    if not variabile:
        # tavoli presenti tutta la serata: un solo NoOverlap2D (ingombri + fissi), moduli totali <= inventario
        m.add_no_overlap_2d([box[sl.chiave][0] for sl in mod.slots] + fx_box,
                            [box[sl.chiave][1] for sl in mod.slots] + fy_box)
        if mod_slots:
            m.add(sum(sl.moduli for sl in mod_slots) <= ist.n_moduli)
    else:
        # ostacoli e corsie esistono sempre: ogni slot non li tocca mai
        if fx_box:
            for sl in mod.slots:
                m.add_no_overlap_2d([box[sl.chiave][0]] + fx_box, [box[sl.chiave][1]] + fy_box)
        # due slot presenti: separati in x, in y oppure nel tempo
        for i1 in range(len(mod.slots)):
            for i2 in range(i1 + 1, len(mod.slots)):
                s1, s2 = mod.slots[i1], mod.slots[i2]
                _, _, x1, xe1, y1, ye1, _, _ = box[s1.chiave]
                _, _, x2, xe2, y2, ye2, _, _ = box[s2.chiave]
                nome = f"{s1.chiave}_{s2.chiave}"
                lits = [m.new_bool_var(f"sep_{nome}_{j}") for j in range(6)]
                m.add(xe1 <= x2).only_enforce_if(lits[0])
                m.add(xe2 <= x1).only_enforce_if(lits[1])
                m.add(ye1 <= y2).only_enforce_if(lits[2])
                m.add(ye2 <= y1).only_enforce_if(lits[3])
                m.add(s1.b <= s2.a).only_enforce_if(lits[4])
                m.add(s2.b <= s1.a).only_enforce_if(lits[5])
                m.add_bool_or(lits + [~s1.p, ~s2.p])
        # in ogni istante: moduli in uso <= inventario, tondi in uso <= inventario
        if mod_slots:
            dom = []
            for sl in mod_slots:
                q = m.new_int_var(0, max(f.moduli for f in forme), f"q_{sl.chiave}")
                m.add(q == sl.moduli)
                dom.append(q)
            m.add_cumulative([esistenza[sl.chiave] for sl in mod_slots], dom, ist.n_moduli)
        if len(tondi) > ist.n_tondi:
            m.add_cumulative([esistenza[sl.chiave] for sl in tondi], [1] * len(tondi), ist.n_tondi)

    # ------------------------------------------------------------ prenotazioni
    per_slot: dict[str, list] = {sl.chiave: [] for sl in mod.slots}
    spreco, sposta, non_sedute = [], [], []
    partenze: dict[int, list] = {}
    attive: dict[int, list] = {}         # passo -> [(coperti, o)] con riapparecchiatura (vincoli ridondanti)
    sempre: dict[str, set] = {}          # pid -> passi in cui è attiva qualunque spostamento scelga
    S: dict[str, Any] = {}
    for v in voci:
        pr, ops = v.pr, v.opzioni
        d = ist.durata_min(pr.coperti) // ist.passo
        t = ist.a_passi(pr.orario_min)
        if ops:
            sempre[pr.id] = set.intersection(*[set(range(st, min(Z, st + d + R))) for _, st in ops])
            valori = sorted({st for _, st in ops} | {t})
            S[pr.id] = m.new_int_var_from_domain(cp_model.Domain.from_values(valori), f"S_{pr.id}")
        eleggibili = [sl for sl in mod.slots if pr.coperti <= sl.cap_max] if ops else []
        if v.obbligatoria and not eleggibili:
            raise ErroreDati(f"{pr.id}: obbligatoria ma senza tavoli o orari possibili")
        lits = []
        for sl in eleggibili:
            av = m.new_bool_var(f"a_{pr.id}_{sl.chiave}")
            mod.a[(pr.id, sl.chiave)] = av
            lits.append(av)
            per_slot[sl.chiave].append((pr.id, av, d))
            m.add_implication(av, sl.p)
            if sl.tipo == "moduli":
                m.add(sl.capienza >= pr.coperti).only_enforce_if(av)
                # posti vuoti = capienza - coperti se assegnata, 0 altrimenti (uguaglianza esatta)
                sp = m.new_int_var(0, sl.cap_max - pr.coperti, f"vuoti_{pr.id}_{sl.chiave}")
                m.add(sp == sl.capienza - pr.coperti).only_enforce_if(av)
                m.add(sp == 0).only_enforce_if(~av)
                spreco.append(sp)
            else:
                spreco.append((sl.cap_max - pr.coperti) * av)
            if variabile:   # la prenotazione (con la riapparecchiatura) sta dentro l'esistenza del tavolo
                m.add(sl.a <= S[pr.id]).only_enforce_if(av)
                m.add(S[pr.id] + d + R <= sl.b).only_enforce_if(av)
        if v.obbligatoria:
            m.add(sum(lits) == 1)
            seduta = 1
        else:
            seduta = m.new_bool_var(f"seduta_{pr.id}")
            m.add(sum(lits) == seduta) if lits else m.add(seduta == 0)
            non_sedute.append(1 - seduta)
        if ops:
            olits = []
            for sm, st in ops:
                ov = m.new_bool_var(f"o_{pr.id}_{sm}")
                mod.o[(pr.id, sm)] = ov
                olits.append((st, ov))
                c = costo_spostamento(pesi["spostamento_per_quarto"], sm)
                if c:
                    sposta.append(c * ov)
                partenze.setdefault(st, []).append(pr.coperti * ov)
                for tau in range(st, min(Z, st + d + R)):
                    attive.setdefault(tau, []).append((pr.coperti, ov))
            m.add(sum(ov for _, ov in olits) == seduta)
            m.add(S[pr.id] == t + sum((st - t) * ov for st, ov in olits))

    # un tavolo presente ospita almeno una prenotazione (dominanza: un tavolo vuoto non migliora mai
    # l'obiettivo e toglierlo non viola nulla)
    for sl in mod.slots:
        lits = [av for _, av, _ in per_slot[sl.chiave]]
        if lits:
            m.add(sum(lits) >= sl.p)
        else:
            m.add(sl.p == 0)

    # nessuna sovrapposizione temporale sullo stesso tavolo (durata + riapparecchiatura)
    for sl in mod.slots:
        ivs = [m.new_optional_fixed_size_interval_var(S[pid], d + R, av, f"i_{pid}_{sl.chiave}")
               for pid, av, d in per_slot[sl.chiave]]
        if len(ivs) > 1:
            m.add_no_overlap(ivs)

    if variabile:
        if rinforzo:
            _rinforzo_per_istante(ist, m, mod, per_slot, sempre, box, fx_box, fy_box)
    elif rinforzo:
        # ridondanti (aiutano a dimostrare l'impossibilità): in ogni passo, per ogni soglia c di coperti,
        # i tavoli con capienza >= c sono almeno quante le prenotazioni attive con almeno c coperti
        soglie = sorted({v.pr.coperti for v in voci if v.opzioni})
        for tau, lst in sorted(attive.items()):
            for c in soglie:
                rhs = [ov for cop, ov in lst if cop >= c]
                if not rhs:
                    continue
                grandi = []
                for sl in mod.slots:
                    if sl.tipo == "moduli":
                        grandi += [b for f, b in sl.forme if f.capienza >= c]
                    elif sl.cap_max >= c:
                        grandi.append(sl.p)
                m.add(sum(grandi) >= sum(rhs))

    # picco cucina: coperti oltre soglia che iniziano nello stesso passo (uguaglianza esatta)
    eccessi = []
    massimo = sum(v.pr.coperti for v in voci) - soglia_picco
    if massimo > 0:
        for st, termini in sorted(partenze.items()):
            e = m.new_int_var(0, massimo, f"picco_{st}")
            m.add_max_equality(e, [sum(termini) - soglia_picco, 0])
            eccessi.append(e)

    # ------------------------------------------------------------ obiettivo
    totale = (pesi["non_sistemata"] * (sum(non_sedute) + non_sistemate_fisse)
              + pesi["posto_vuoto"] * sum(spreco)
              + sum(sposta)
              + pesi["accostamento_per_modulo"] * sum(sl.moduli - sl.p for sl in mod_slots)
              + pesi["picco_cucina_per_coperto"] * sum(eccessi)
              + pesi["riallestimento"] * sum(sl.riall for sl in mod.slots))
    if obiettivo == "completo":
        m.minimize(totale)
    elif obiettivo == "nessuno":     # sola ammissibilità
        pass
    else:
        raise ValueError(obiettivo)
    return mod


def _rinforzo_per_istante(ist: Istanza, m, mod: _Modello, per_slot: dict, sempre: dict, box: dict,
                          fx_box: list, fy_box: list) -> None:
    """Solo "variabile", vincoli RIDONDANTI (non cambiano le soluzioni ammesse, aiutano a dimostrare
    l'impossibilità). Per ogni passo tau e slot s: e[s,tau] = 1 se su s c'è una prenotazione attiva a tau
    (allora s esiste a tau); y[s,tau,c] = 1 se quella prenotazione ha almeno c coperti. A ogni passo:
    - NoOverlap2D sugli slot con e = 1 (più ostacoli e corsie);
    - slot con e = 1 >= prenotazioni attive; per ogni soglia c, slot con y = 1 >= attive con almeno c coperti;
    - moduli in uso >= somma degli slot a moduli con e = 1 (più i moduli extra che la soglia c impone) <= inventario;
      tondi con e = 1 <= inventario."""
    Z, R, passo = ist.orizzonte_passi, ist.riapp_passi, ist.passo
    coperti = {v.pr.id: v.pr.coperti for v in mod.voci}
    cap_min = min([f.capienza for f in ist.forme_moduli] + ([ist.forma_tondo.capienza] if ist.forma_tondo else []))
    soglie = sorted({c for c in coperti.values() if c > cap_min})
    delta, prec = {}, 1          # moduli in più necessari per passare alla capienza >= c
    for c in soglie:
        k = min((f.moduli for f in ist.forme_moduli if f.capienza >= c), default=None)
        delta[c] = (k - prec) if k is not None else 0
        prec = k if k is not None else prec
    # att[(pid, tau)] = opzioni di orario che rendono la prenotazione attiva a tau (riapparecchiatura compresa)
    att: dict[tuple, list] = {}
    for v in mod.voci:
        d = ist.durata_min(v.pr.coperti) // passo
        for sm, st in v.opzioni:
            ov = mod.o[(v.pr.id, sm)]
            for tau in range(st, min(Z, st + d + R)):
                att.setdefault((v.pr.id, tau), []).append(ov)
    for tau in range(Z):
        attive_tau = [(pid, sum(att[(pid, tau)])) for pid in coperti if (pid, tau) in att]
        if not attive_tau:
            continue
        es, uso_moduli, tondi_vivi = [], [], []
        per_soglia: dict[int, list] = {c: [] for c in soglie}
        bx, by = [], []
        for sl in mod.slots:
            cand = [(pid, av) for pid, av, _ in per_slot[sl.chiave] if (pid, tau) in att]
            if not cand:
                continue
            e = m.new_bool_var(f"es_{sl.chiave}_{tau}")
            fisse = [av for pid, av in cand if tau in sempre.get(pid, ())]
            if fisse:
                m.add(e >= sum(fisse))
            for pid, av in cand:
                if tau not in sempre.get(pid, ()):
                    m.add(e >= av + sum(att[(pid, tau)]) - 1)
            m.add_implication(e, sl.p)
            m.add(sl.a <= tau).only_enforce_if(e)
            m.add(sl.b >= tau + 1).only_enforce_if(e)
            es.append(e)
            (uso_moduli if sl.tipo == "moduli" else tondi_vivi).append(e)
            _, _, x, xe, y, ye, w, h = box[sl.chiave]
            bx.append(m.new_optional_interval_var(x, w, xe, e, f"ixs_{sl.chiave}_{tau}"))
            by.append(m.new_optional_interval_var(y, h, ye, e, f"iys_{sl.chiave}_{tau}"))
            for c in soglie:
                lc = [(pid, av) for pid, av in cand if coperti[pid] >= c]
                if not lc:
                    continue
                grandi = [b for f, b in sl.forme if f.capienza >= c] if sl.tipo == "moduli" else (
                    [sl.p] if sl.cap_max >= c else [])
                if not grandi:
                    continue
                yv = m.new_bool_var(f"ys_{sl.chiave}_{tau}_{c}")
                for pid, av in lc:
                    m.add(yv >= av + sum(att[(pid, tau)]) - 1)
                m.add_implication(yv, e)
                m.add(yv <= sum(grandi))
                per_soglia[c].append(yv)
                if sl.tipo == "moduli" and delta[c]:
                    uso_moduli.append(delta[c] * yv)
        if len(bx) > 1:
            m.add_no_overlap_2d(bx + fx_box, by + fy_box)
        m.add(sum(es) >= sum(a for _, a in attive_tau))
        for c in soglie:
            rhs = [a for pid, a in attive_tau if coperti[pid] >= c]
            if rhs:
                m.add(sum(per_soglia[c]) >= sum(rhs))
        if uso_moduli:
            m.add(sum(uso_moduli) <= ist.n_moduli)
        if len(tondi_vivi) > ist.n_tondi:
            m.add(sum(tondi_vivi) <= ist.n_tondi)


# ---------------------------------------------------------------------------- risoluzione

def _risolvi_modello(mod: _Modello, tempo_s: float, worker: int, seed: int, log: bool,
                     hint: dict | None = None) -> tuple[str, dict | None, dict]:
    """Risolve; restituisce (stato, piano = {nome variabile: valore} oppure None, info)."""
    m = mod.m
    n_hint = 0
    if hint:
        for idx, vp in enumerate(m.proto.variables):
            if vp.name in hint:
                m.add_hint(m.get_int_var_from_proto_index(idx), hint[vp.name])
                n_hint += 1
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = tempo_s
    solver.parameters.num_workers = worker
    solver.parameters.random_seed = seed
    solver.parameters.log_search_progress = log
    t0 = time.perf_counter()
    stato = solver.solve(m)
    tempo = time.perf_counter() - t0
    nome = solver.status_name(stato)
    info = {"stato": nome, "obiettivo": None, "bound": None, "gap_pct": None, "tempo_s": round(tempo, 2),
            "tempo_limite_s": tempo_s, "worker": worker, "seed": seed, "versione_ortools": ortools.__version__,
            "variabili": len(m.proto.variables), "vincoli": len(m.proto.constraints), "variabili_con_hint": n_hint}
    if stato == cp_model.MODEL_INVALID:
        raise RuntimeError(f"modello non valido: {m.validate()}")
    if stato not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return nome, None, info
    info["obiettivo"] = int(round(solver.objective_value))
    info["bound"] = int(round(solver.best_objective_bound))
    info["gap_pct"] = (round(100 * (solver.objective_value - solver.best_objective_bound) / solver.objective_value, 2)
                       if solver.objective_value > 0 else 0.0)
    piano = {vp.name: int(val) for vp, val in zip(m.proto.variables, solver.response_proto.solution)}
    return nome, piano, info


def _estrai(ist: Istanza, mod: _Modello, piano: dict) -> tuple[list, list, set]:
    """Tavoli e assegnazioni dal piano (valori per nome di variabile)."""
    if mod.turni:
        from .modello_turni import estrai_turni
        return estrai_turni(ist, mod, piano)

    def V(x):
        return x if isinstance(x, int) else piano[x.name]

    g, mg, passo = ist.griglia, ist.margine, ist.passo
    Z, R = ist.orizzonte_passi, ist.riapp_passi
    variabile = mod.disposizione == VARIABILE
    presenti = []
    for sl in mod.slots:
        if not V(sl.p):
            continue
        forma = next(f for f, b in sl.forme if V(b))
        presenti.append({"chiave": sl.chiave, "forma": forma, "fx": V(sl.x), "fy": V(sl.y),
                         "a": V(sl.a), "b": V(sl.b), "pren": []})
    per_chiave = {t["chiave"]: t for t in presenti}
    sedute = {}
    for v in mod.voci:
        chiave = next((k for (pid, k), av in mod.a.items() if pid == v.pr.id and V(av)), None)
        if chiave is None:
            continue
        sm = next(sm for (pid, sm), ov in mod.o.items() if pid == v.pr.id and V(ov))
        st = ist.a_passi(v.pr.orario_min + sm)
        d = ist.durata_min(v.pr.coperti) // passo
        sedute[v.pr.id] = (v.pr, sm, chiave)
        per_chiave[chiave]["pren"].append((st, st + d + R))

    if variabile:
        _rifinisci_esistenza(ist, presenti)

    # numerazione: in "fissa" in ordine di lettura; in "variabile" prima per ora di montaggio
    presenti.sort(key=lambda t: ((t["a"],) if variabile else ()) + (t["fy"], t["fx"], t["chiave"]))
    id_di = {}
    tavoli = []
    for n, t in enumerate(presenti, start=1):
        tid = f"T{n}"
        id_di[t["chiave"]] = tid
        f = t["forma"]
        x_cm, y_cm = t["fx"] * g + mg, t["fy"] * g + mg
        tav = {
            "id": tid, "tipo": f.tipo, "moduli": f.moduli,
            "orientamento": f.orientamento if f.tipo == "moduli" else None,
            "x_cm": x_cm, "y_cm": y_cm, "larghezza_cm": f.larghezza_cm, "altezza_cm": f.altezza_cm,
            "capienza": f.capienza,
            "ingombro_cm": {"x0": x_cm - mg, "y0": y_cm - mg,
                            "x1": x_cm + f.larghezza_cm + mg, "y1": y_cm + f.altezza_cm + mg},
            "esiste_dal": min_a_hhmm(ist.inizio_min + t["a"] * passo),
            "esiste_al": min_a_hhmm(ist.inizio_min + t["b"] * passo),
            "fino_a_chiusura": t["b"] == Z,
            "montato_in_servizio": t["a"] > 0,
        }
        if f.tipo == "tondo":
            tav["diametro_cm"] = f.larghezza_cm
        tavoli.append(tav)

    assegnazioni = []
    for pid, (pr, sm, chiave) in sedute.items():
        inizio = pr.orario_min + sm
        assegnazioni.append({
            "id": pr.id, "nome": pr.nome, "coperti": pr.coperti,
            "orario_richiesto": min_a_hhmm(pr.orario_min), "orario_assegnato": min_a_hhmm(inizio),
            "spostamento_min": sm, "fine": min_a_hhmm(inizio + ist.durata_min(pr.coperti)),
            "tavolo": id_di[chiave], "note": pr.note,
        })
    assegnazioni.sort(key=lambda r: (r["orario_assegnato"], int(r["tavolo"][1:])))
    return tavoli, assegnazioni, set(sedute)


def _rifinisci_esistenza(ist: Istanza, presenti: list[dict]) -> None:
    """Solo "variabile": il solver lascia libero l'intervallo di esistenza entro i vincoli. Per la lettura:
    - un tavolo montato dopo l'apertura si monta all'inizio della sua prima prenotazione (stesso costo);
    - un tavolo resta fino alla chiusura se nessun altro tavolo o l'inventario ne hanno bisogno,
      altrimenti si smonta alla fine (con riapparecchiatura) della sua ultima prenotazione.
    Entrambe le modifiche restringono o allungano l'intervallo solo dove resta ammissibile."""
    Z = ist.orizzonte_passi
    for t in presenti:
        if t["pren"]:
            if t["a"] > 0:
                t["a"] = min(s for s, _ in t["pren"])
            t["b"] = max(e for _, e in t["pren"])

    def spazio(t1, t2):
        f1, f2 = t1["forma"], t2["forma"]
        return (t1["fx"] < t2["fx"] + f2.ingombro_l and t2["fx"] < t1["fx"] + f1.ingombro_l
                and t1["fy"] < t2["fy"] + f2.ingombro_h and t2["fy"] < t1["fy"] + f1.ingombro_h)

    for t in sorted(presenti, key=lambda t: t["chiave"]):
        if t["b"] >= Z:
            continue
        # spazio-tempo: oggi t vive in [a, b) senza conflitti; allungarlo fino a Z è lecito solo se ogni
        # tavolo che usa lo stesso spazio è già stato smontato prima che t esista (u.b <= t.a)
        ok = all(u["b"] <= t["a"] for u in presenti if u is not t and spazio(t, u))
        for tau in range(t["b"], Z):
            if not ok:
                break
            attivi = [u for u in presenti if u is not t and u["a"] <= tau < u["b"]]
            if t["forma"].tipo == "moduli":
                uso = sum(u["forma"].moduli for u in attivi if u["forma"].tipo == "moduli") + t["forma"].moduli
                ok = uso <= ist.n_moduli
            else:
                ok = sum(1 for u in attivi if u["forma"].tipo == "tondo") + 1 <= ist.n_tondi
        if ok:
            t["b"] = Z


# ---------------------------------------------------------------------------- uscite comuni

def _non_sistemata(ist: Istanza, pr: Prenotazione, ops, motivo: str | None = None) -> dict:
    if motivo is None:
        if pr.coperti > ist.capienza_massima:
            motivo = MOTIVO_TROPPO_GRANDE
        elif not ops:
            motivo = MOTIVO_FUORI_ORARIO
        else:
            motivo = MOTIVO_SALA_PIENA
    return {"id": pr.id, "nome": pr.nome, "coperti": pr.coperti,
            "orario_richiesto": min_a_hhmm(pr.orario_min), "motivo": motivo, "note": pr.note}


def calcola_componenti(ist: Istanza, tavoli: list, assegnazioni: list, non_sistemate: list) -> dict:
    """Componenti dell'obiettivo ricalcolate dalla soluzione estratta (non dalle variabili ausiliarie)."""
    pesi = _pesi(ist)
    soglia = int(ist.sala.get("picco_cucina_soglia_coperti", 30))
    cap = {t["id"]: t["capienza"] for t in tavoli}
    vuoti = sum(cap[r["tavolo"]] - r["coperti"] for r in assegnazioni)
    quarti = sum(abs(r["spostamento_min"]) for r in assegnazioni) / 15
    quarti = int(quarti) if quarti == int(quarti) else round(quarti, 2)
    costo_sp = sum(costo_spostamento(pesi["spostamento_per_quarto"], r["spostamento_min"]) for r in assegnazioni)
    extra = sum(t["moduli"] - 1 for t in tavoli if t["tipo"] == "moduli")
    riall = sum(1 for t in tavoli if t.get("montato_in_servizio"))
    per_quarto: dict[str, int] = {}
    for r in assegnazioni:
        per_quarto[r["orario_assegnato"]] = per_quarto.get(r["orario_assegnato"], 0) + r["coperti"]
    oltre = sum(max(0, v - soglia) for v in per_quarto.values())
    if ist.turni:           # a turni ogni turno arriva tutto insieme: il picco della cucina non si conta
        oltre = 0
    comp = {
        "non_sistemate": {"numero": len(non_sistemate), "costo": pesi["non_sistemata"] * len(non_sistemate)},
        "posti_vuoti": {"posti": vuoti, "costo": pesi["posto_vuoto"] * vuoti},
        "spostamenti": {"quarti_d_ora": quarti, "costo": costo_sp},
        "accostamenti": {"moduli_oltre_il_primo": extra, "costo": pesi["accostamento_per_modulo"] * extra},
        "picco_cucina": {"coperti_oltre_soglia": oltre, "soglia": soglia,
                         "costo": pesi["picco_cucina_per_coperto"] * oltre,
                         "coperti_per_orario": dict(sorted(per_quarto.items())),
                         **({"disattivato": "turni"} if ist.turni else {})},
        "riallestimenti": {"numero": riall, "costo": pesi["riallestimento"] * riall},
    }
    comp["totale"] = sum(v["costo"] for v in comp.values())
    return comp


def _parametri(ist, worker, seed):
    return (int(worker if worker is not None else _cfg_solver(ist, "worker", 8)),
            int(seed if seed is not None else _cfg_solver(ist, "seed", 42)))


def modalita_turni(ist: Istanza) -> dict:
    """Voci della modalità a turni da dichiarare nella soluzione (le controlla il verificatore)."""
    if not ist.turni:
        return {}
    return {"turni": [{"nome": t.nome, "inizio": min_a_hhmm(t.inizio_min), "fine": min_a_hhmm(t.fine_min)}
                      for t in ist.turni], "turno_a_parita": ist.turno_a_parita}


# ---------------------------------------------------------------------------- modalità "tutte_insieme"

def risolvi(ist: Istanza, tempo_limite_s: float | None = None, worker: int | None = None,
            seed: int | None = None, log: bool = False, disposizione: str | None = None) -> dict:
    """Ottimizzazione unica su tutte le prenotazioni (la modalità originale)."""
    disposizione = disposizione or ist.disposizione
    tempo_limite_s = float(tempo_limite_s if tempo_limite_s is not None else _cfg_solver(ist, "tempo_limite_s", 30))
    worker, seed = _parametri(ist, worker, seed)
    t0 = time.perf_counter()
    voci = [_Voce(pr, ist.opzioni(pr), False) for pr in ist.prenotazioni]
    mod = _costruisci(ist, voci, disposizione)
    tempo_costr = time.perf_counter() - t0
    stato, piano, info = _risolvi_modello(mod, tempo_limite_s, worker, seed, log)
    info["tempo_costruzione_modello_s"] = round(tempo_costr, 2)
    if stato == "INFEASIBLE":
        # la soluzione "nessun tavolo, nessuna prenotazione sistemata" è sempre ammissibile
        raise RuntimeError("modello INFEASIBLE: errore di modellazione o di dati")
    base = {"sala": ist.sala.get("nome", ""), "serata": ist.serata.get("serata", ""),
            "modalita": {"accettazione": TUTTE_INSIEME, "disposizione": disposizione, **modalita_turni(ist)},
            "solver": info}
    if piano is None:
        ns = [_non_sistemata(ist, pr, [], MOTIVO_NESSUNA_SOLUZIONE) for pr in ist.prenotazioni]
        return base | {"obiettivo_componenti": calcola_componenti(ist, [], [], ns),
                       "tavoli": [], "assegnazioni": [], "non_sistemate": ns}
    tavoli, assegnazioni, sedute = _estrai(ist, mod, piano)
    non_sistemate = [_non_sistemata(ist, pr, ist.opzioni(pr)) for pr in ist.prenotazioni if pr.id not in sedute]
    comp = calcola_componenti(ist, tavoli, assegnazioni, non_sistemate)
    info["obiettivo_coerente_con_componenti"] = comp["totale"] == info["obiettivo"]
    return base | {"obiettivo_componenti": comp, "tavoli": tavoli, "assegnazioni": assegnazioni,
                   "non_sistemate": non_sistemate}


# ---------------------------------------------------------------------------- decisione su una richiesta

@dataclass
class Decisione:
    """Esito della valutazione di una richiesta contro le prenotazioni già accettate (orari congelati)."""
    esito: str                           # "accettata" | "proposta" | "rifiutata"
    decisione: str                       # "ammissibile" | "ammissibile su proposta" | "impossibile (a priori)" |
                                         # "impossibile (dimostrato)" | "non decisa (tempo scaduto)"
    motivo: str | None = None            # se "rifiutata"
    spostamento: int | None = None       # se "accettata": spostamento ammesso scelto
    piano: dict | None = None            # piano ammissibile (hint) se "accettata"
    stato_fascia: str = ""               # esiti dei livelli di spostamento ammessi
    minimo_dimostrato: bool | None = None
    spareggio: str | None = None
    prima: dict | None = None            # proposta più vicina prima: {"spostamento", "inizio", "piano", "dimostrata"}
    dopo: dict | None = None
    esiti_proposte: str = ""


def _impossibile_per_conteggio(ist: Istanza, accettate: list[_Voce], pr: Prenotazione, st: int,
                               disposizione: str | None = None) -> bool:
    """Condizione SUFFICIENTE di impossibilità, in qualunque disposizione: in un passo della permanenza di `pr`
    (riapparecchiatura compresa) le prenotazioni attive chiedono più moduli dell'inventario, anche usando al meglio
    i tondi. Ogni prenotazione attiva occupa un tavolo suo; un tavolo a moduli per c coperti usa almeno kmin(c) moduli.
    A turni il conteggio è per turno (e in "fissa" sui tavoli che servono tutti i turni)."""
    if ist.turni:
        from .modello_turni import impossibile_per_conteggio_turni
        return impossibile_per_conteggio_turni(ist, accettate, pr, st, disposizione)
    R, Z, passo = ist.riapp_passi, ist.orizzonte_passi, ist.passo
    cap_t = ist.forma_tondo.capienza if ist.forma_tondo is not None else 0
    n_t = ist.n_tondi if ist.forma_tondo is not None else 0

    def kmin(c):
        return min((f.moduli for f in ist.forme_moduli if f.capienza >= c), default=None)

    blocchi = [(v.opzioni[0][1], v.opzioni[0][1] + ist.durata_min(v.pr.coperti) // passo + R, v.pr.coperti)
               for v in accettate]
    d = ist.durata_min(pr.coperti) // passo
    for tau in range(st, min(Z, st + d + R)):
        coperti = [c for a, b, c in blocchi if a <= tau < b] + [pr.coperti]
        moduli, risparmi, tondi_obbligati = 0, [], 0
        for c in coperti:
            k = kmin(c)
            if k is None:
                if c > cap_t:
                    return True
                tondi_obbligati += 1
            else:
                moduli += k
                if c <= cap_t:
                    risparmi.append(k)
        liberi = n_t - tondi_obbligati
        if liberi < 0 or moduli - sum(sorted(risparmi, reverse=True)[:liberi]) > ist.n_moduli:
            return True
    return False


def _primo_ammissibile(ist, accettate, pr, candidati, disposizione, tempo_s, worker, seed, log, piano):
    """Prova i candidati (spostamento, inizio) dal più vicino; restituisce (proposta | None, esiti, tutti_decisi).
    `dimostrata` = tutti i candidati più vicini sono stati esclusi con certezza (INFEASIBLE o conteggio)."""
    esiti, tutti_decisi = [], True
    for sm, st in candidati:
        if _impossibile_per_conteggio(ist, accettate, pr, st, disposizione):
            esiti.append(f"{sm:+d}′ CONTEGGIO")
            continue
        mod = _costruisci(ist, accettate + [_Voce(pr, [(sm, st)], True)], disposizione, obiettivo="nessuno")
        stato, nuovo, _ = _risolvi_modello(mod, tempo_s, worker, seed, log, hint=piano)
        if nuovo is not None:
            esiti.append(f"{sm:+d}′ AMMISSIBILE")
            return {"spostamento": sm, "inizio": st, "piano": nuovo, "dimostrata": tutti_decisi}, esiti, tutti_decisi
        esiti.append(f"{sm:+d}′ {stato}")
        tutti_decisi = tutti_decisi and stato == "INFEASIBLE"
    return None, esiti, tutti_decisi


def valuta_richiesta(ist: Istanza, accettate: list[_Voce], pr: Prenotazione, disposizione: str,
                     tempo_decisione_s: float, tempo_spareggio_s: float, tempo_proposta_s: float,
                     worker: int, seed: int, log: bool = False, piano: dict | None = None,
                     cerca_proposte: bool = True) -> Decisione:
    """C'è posto per `pr` con le prenotazioni `accettate` (orari congelati, tavoli liberi)?
    1) spostamenti ammessi, un livello |spostamento| alla volta (sola ammissibilità; il tempo della decisione si
       divide tra i livelli), spareggio sul resto dell'obiettivo se il livello ha due direzioni;
    2) se non entra e `cerca_proposte`: l'orario ammissibile più vicino prima e dopo, entro la distanza massima
       (filtro rapido col conteggio dei moduli, poi solver con `tempo_proposta_s` per orario)."""
    if pr.coperti > ist.capienza_massima:
        return Decisione("rifiutata", "impossibile (a priori)", MOTIVO_TROPPO_GRANDE, stato_fascia="non necessario")
    ops = ist.opzioni(pr)
    livelli = sorted({abs(sm) for sm, _ in ops})
    t0 = time.perf_counter()
    esiti_liv = []
    for j, liv in enumerate(livelli):
        rimasto = tempo_decisione_s - (time.perf_counter() - t0)
        if rimasto < 0.05:
            esiti_liv.append((liv, "UNKNOWN"))
            continue
        ops_l = [o for o in ops if abs(o[0]) == liv]
        if all(_impossibile_per_conteggio(ist, accettate, pr, st, disposizione) for _, st in ops_l):
            esiti_liv.append((liv, "CONTEGGIO"))
            continue
        mod = _costruisci(ist, accettate + [_Voce(pr, ops_l, True)], disposizione, obiettivo="nessuno")
        stato, nuovo, _ = _risolvi_modello(mod, rimasto / (len(livelli) - j), worker, seed, log, hint=piano)
        if nuovo is None:
            esiti_liv.append((liv, stato))
            continue
        esiti_liv.append((liv, "AMMISSIBILE"))
        sm = next(s_ for (pid, s_), ov in mod.o.items() if pid == pr.id and nuovo[ov.name])
        dec = Decisione("accettata", "ammissibile", piano=nuovo,
                        minimo_dimostrato=all(st_ in ("INFEASIBLE", "CONTEGGIO") for _, st_ in esiti_liv[:-1]))
        if len(ops_l) > 1:   # stesso spostamento minimo in più direzioni: decide il resto dell'obiettivo
            mod2 = _costruisci(ist, accettate + [_Voce(pr, ops_l, True)], disposizione)
            stato2, nuovo2, _ = _risolvi_modello(mod2, tempo_spareggio_s, worker, seed, log, hint=nuovo)
            dec.spareggio = stato2
            if nuovo2 is not None:
                sm = next(s_ for (pid, s_), ov in mod2.o.items() if pid == pr.id and nuovo2[ov.name])
                dec.piano = nuovo2
        dec.spostamento = sm
        dec.stato_fascia = " · ".join(f"{l_}′ {st_}" for l_, st_ in esiti_liv)
        return dec
    stato_fascia = " · ".join(f"{l_}′ {st_}" for l_, st_ in esiti_liv) or "nessun orario ammesso nel servizio"
    fascia_decisa = all(st_ in ("INFEASIBLE", "CONTEGGIO") for _, st_ in esiti_liv)
    if not cerca_proposte:
        if not ops:
            return Decisione("rifiutata", "impossibile (a priori)", MOTIVO_FUORI_ORARIO, stato_fascia=stato_fascia)
        if fascia_decisa:
            return Decisione("rifiutata", "impossibile (dimostrato)",
                             MOTIVO_TURNO_PIENO if ist.turni else MOTIVO_SALA_PIENA_ACCETTATE, stato_fascia=stato_fascia)
        return Decisione("rifiutata", "non decisa (tempo scaduto)", MOTIVO_TEMPO_SCADUTO, stato_fascia=stato_fascia)
    cand_prima, cand_dopo = ist.candidati_proposta(pr)
    prima, es_p, dec_p = _primo_ammissibile(ist, accettate, pr, cand_prima, disposizione, tempo_proposta_s,
                                            worker, seed, log, piano)
    dopo, es_d, dec_d = _primo_ammissibile(ist, accettate, pr, cand_dopo, disposizione, tempo_proposta_s,
                                           worker, seed, log, piano)
    esiti_proposte = f"prima: {', '.join(es_p) or '—'} | dopo: {', '.join(es_d) or '—'}"
    if prima is None and dopo is None:
        if fascia_decisa and dec_p and dec_d:
            return Decisione("rifiutata", "impossibile (dimostrato)",
                             MOTIVO_TURNI_PIENI if ist.turni else motivo_nessun_orario(ist.proposta_max_distanza_min),
                             stato_fascia=stato_fascia, esiti_proposte=esiti_proposte)
        return Decisione("rifiutata", "non decisa (tempo scaduto)", MOTIVO_TEMPO_SCADUTO,
                         stato_fascia=stato_fascia, esiti_proposte=esiti_proposte)
    return Decisione("proposta", "ammissibile su proposta", stato_fascia=stato_fascia, prima=prima, dopo=dopo,
                     esiti_proposte=esiti_proposte)


def proposta_principale(ist: Istanza, dec: Decisione) -> dict | None:
    """La proposta più vicina; a parità di distanza decide `proposta_a_parita` ("prima" o "dopo")."""
    cand = [p for p in (dec.prima, dec.dopo) if p is not None]
    if not cand:
        return None
    dopo_preferito = ist.proposta_a_parita == "dopo"
    return min(cand, key=lambda p: (abs(p["spostamento"]), (p["spostamento"] > 0) != dopo_preferito))


# ---------------------------------------------------------------------------- modalità "ordine_di_arrivo"

def accetta_in_ordine(ist: Istanza, disposizione: str | None = None, tempo_decisione_s: float | None = None,
                      tempo_spareggio_s: float | None = None, tempo_piantina_s: float | None = None,
                      worker: int | None = None, seed: int | None = None, log: bool = False,
                      avanzamento: Callable[[str], None] | None = None,
                      tempo_proposta_s: float | None = None) -> dict:
    """Rigioca le prenotazioni in ordine di `prenotata_il` e costruisce la piantina finale. Se una prenotazione
    non entra negli spostamenti ammessi e la politica non è "mai", le si propone l'orario libero più vicino."""
    disposizione = disposizione or ist.disposizione
    tempo_decisione_s = float(tempo_decisione_s if tempo_decisione_s is not None
                              else _cfg_solver(ist, "tempo_decisione_s", 120))
    tempo_spareggio_s = float(tempo_spareggio_s if tempo_spareggio_s is not None
                              else _cfg_solver(ist, "tempo_spareggio_s", 20))
    tempo_piantina_s = float(tempo_piantina_s if tempo_piantina_s is not None
                             else _cfg_solver(ist, "tempo_piantina_s", 300))
    tempo_proposta_s = float(tempo_proposta_s if tempo_proposta_s is not None
                             else _cfg_solver(ist, "tempo_proposta_s", 60))
    worker, seed = _parametri(ist, worker, seed)
    mancanti = [p.id for p in ist.prenotazioni if not p.prenotata_il]
    if mancanti:
        raise ErroreDati(f"accettazione in ordine di arrivo: manca prenotata_il per {', '.join(mancanti)}")
    say = avanzamento or (lambda _msg: None)
    t_inizio = time.perf_counter()
    politica = ist.cliente_accetta_proposta

    accettate: list[_Voce] = []          # orario congelato: una sola opzione
    rifiutate: list[dict] = []
    registro: list[dict] = []
    piano: dict | None = None            # ultimo piano ammissibile (hint per il passo successivo)
    for n, pr in enumerate(ist.in_ordine_di_arrivo(), start=1):
        rec = {"ordine": n, "id": pr.id, "nome": pr.nome, "coperti": pr.coperti,
               "orario_richiesto": min_a_hhmm(pr.orario_min), "prenotata_il": pr.prenotata_il,
               "esito": None, "orario_promesso": None, "spostamento_min": None, "motivo": None,
               "stato_solver": None, "decisione": None, "spostamento_minimo_dimostrato": None,
               "spareggio": None, "proposta_prima": None, "proposta_dopo": None, "proposta_principale": None,
               "proposte_piu_vicine_dimostrate": None, "esiti_proposte": None, "tempo_s": 0.0}
        if ist.turni:
            rec.update(turno_richiesto=ist.turni[ist.turno_della(pr)].nome, turno_promesso=None, turno_proposto=None)
        t0 = time.perf_counter()
        dec = valuta_richiesta(ist, accettate, pr, disposizione, tempo_decisione_s, tempo_spareggio_s,
                               tempo_proposta_s, worker, seed, log, piano, cerca_proposte=politica != MAI)
        rec.update(stato_solver=dec.stato_fascia, decisione=dec.decisione, spareggio=dec.spareggio,
                   spostamento_minimo_dimostrato=dec.minimo_dimostrato, esiti_proposte=dec.esiti_proposte or None)
        motivo = dec.motivo
        if dec.esito == "accettata":
            sm = dec.spostamento
            accettate.append(_Voce(pr, [(sm, ist.a_passi(pr.orario_min + sm))], True))
            piano = dec.piano
            rec.update(esito="accettata", orario_promesso=min_a_hhmm(pr.orario_min + sm), spostamento_min=sm)
            if ist.turni:       # a turni non c'è spostamento: si promette il turno
                rec.update(spostamento_min=0, turno_promesso=rec["turno_richiesto"])
        elif dec.esito == "proposta":
            princ = proposta_principale(ist, dec)
            rec.update(proposta_prima=min_a_hhmm(pr.orario_min + dec.prima["spostamento"]) if dec.prima else None,
                       proposta_dopo=min_a_hhmm(pr.orario_min + dec.dopo["spostamento"]) if dec.dopo else None,
                       proposta_principale=min_a_hhmm(pr.orario_min + princ["spostamento"]),
                       proposte_piu_vicine_dimostrate={"prima": dec.prima["dimostrata"] if dec.prima else None,
                                                       "dopo": dec.dopo["dimostrata"] if dec.dopo else None})
            if ist.turni:
                rec["turno_proposto"] = ist.turni[ist.turno_da_passo(princ["inizio"])].nome
            if ist.accetta_proposta(princ["spostamento"]):
                sm = princ["spostamento"]
                accettate.append(_Voce(pr, [(sm, princ["inizio"])], True))
                piano = princ["piano"]
                rec.update(esito="accettata su proposta", orario_promesso=min_a_hhmm(pr.orario_min + sm),
                           spostamento_min=sm)
                if ist.turni:
                    rec.update(spostamento_min=0, turno_promesso=rec["turno_proposto"])
            else:
                motivo = MOTIVO_PROPOSTA_RIFIUTATA
                rec["decisione"] = "proposta rifiutata dal cliente"
        if motivo is not None:
            rec.update(esito="rifiutata", motivo=motivo)
            rifiutate.append(_non_sistemata(ist, pr, ist.opzioni(pr), motivo))
        rec["tempo_s"] = round(time.perf_counter() - t0, 2)
        registro.append(rec)
        dettaglio = ({"accettata": f" nel {rec.get('turno_promesso')} turno",
                      "accettata su proposta": f" nel {rec.get('turno_promesso')} turno (chiesto il "
                                               f"{rec.get('turno_richiesto')})"} if ist.turni else {}).get(rec["esito"])
        dettaglio = dettaglio or {"accettata": f" alle {rec['orario_promesso']}",
                     "accettata su proposta": f" alle {rec['orario_promesso']} (proposte: prima {rec['proposta_prima']},"
                                              f" dopo {rec['proposta_dopo']})"}.get(rec["esito"], f" ({rec['motivo']})")
        extra = f" | {rec['esiti_proposte']}" if rec["esiti_proposte"] else ""
        say(f"{n:2d}. {pr.prenotata_il} {pr.nome} ×{pr.coperti} {rec['orario_richiesto']}: {rec['esito']}{dettaglio}"
            f" [{rec['stato_solver']}{extra}, {rec['tempo_s']} s]")

    # ------------------------------------------------------------ piantina delle 18
    t0 = time.perf_counter()
    base = {"sala": ist.sala.get("nome", ""), "serata": ist.serata.get("serata", ""),
            "modalita": {"accettazione": ORDINE_DI_ARRIVO, "disposizione": disposizione,
                         "cliente_accetta_proposta": politica,
                         "proposta_max_distanza_min": ist.proposta_max_distanza_min,
                         "proposta_a_parita": ist.proposta_a_parita, **modalita_turni(ist)}}
    if accettate:
        mod = _costruisci(ist, accettate, disposizione, non_sistemate_fisse=len(rifiutate))
        stato, finale, info = _risolvi_modello(mod, tempo_piantina_s, worker, seed, log, hint=piano)
        info["origine"] = "solver"
        if finale is None:
            # l'ultimo piano di accettazione è già una soluzione ammissibile della piantina
            finale, info["origine"] = piano, "ultimo piano di accettazione (il solver non ha restituito soluzioni)"
        tavoli, assegnazioni, sedute = _estrai(ist, mod, finale)
        if len(sedute) != len(accettate):
            raise RuntimeError("piantina finale: non tutte le accettate sono sedute")
    else:
        info = {"stato": "non necessario", "obiettivo": 0, "bound": 0, "gap_pct": 0.0, "tempo_s": 0.0,
                "origine": "nessuna prenotazione accettata"}
        tavoli, assegnazioni = [], []
    info["tempo_piantina_s"] = round(time.perf_counter() - t0, 2)
    comp = calcola_componenti(ist, tavoli, assegnazioni, rifiutate)
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
        "decisioni_ammissibili_su_proposta": (stati.count("ammissibile su proposta")
                                              + stati.count("proposta rifiutata dal cliente")),
        "decisioni_impossibili_dimostrate": stati.count("impossibile (dimostrato)"),
        "decisioni_impossibili_a_priori": stati.count("impossibile (a priori)"),
        "decisioni_unknown": stati.count("non decisa (tempo scaduto)"),
        "spostamento_minimo_non_dimostrato": sum(r["spostamento_minimo_dimostrato"] is False for r in registro),
        "tempo_decisioni_s": round(sum(r["tempo_s"] for r in registro), 1),
        "tempo_totale_s": round(time.perf_counter() - t_inizio, 1),
        "tempo_decisione_limite_s": tempo_decisione_s,
        "tempo_spareggio_limite_s": tempo_spareggio_s,
        "tempo_piantina_limite_s": tempo_piantina_s,
        "tempo_proposta_limite_s": tempo_proposta_s,
    }
    return base | {"solver": info, "accettazione": riepilogo, "registro": registro, "obiettivo_componenti": comp,
                   "tavoli": tavoli, "assegnazioni": assegnazioni, "non_sistemate": rifiutate}
