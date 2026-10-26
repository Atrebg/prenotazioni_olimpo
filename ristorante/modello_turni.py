"""Modello CP-SAT della modalità a turni: senza il tempo continuo ogni turno è un problema di sola sistemazione.

- Ogni prenotazione occupa un tavolo per tutto il suo turno: durate, riapparecchiatura e picco della cucina non
  contano. Su un tavolo c'è al massimo una prenotazione per turno.
- "fissa": stessi tavoli e stessi accostamenti in tutti i turni; un solo NoOverlap2D, moduli entro l'inventario.
- "variabile": ogni turno ha la sua disposizione (NoOverlap2D e inventario per turno). Il tavolo s del turno k è
  "lo stesso" del tavolo s del turno k-1 se hanno forma e posizione uguali (u = 1); altrimenti è montato a servizio
  iniziato (r = 1) e paga il riallestimento. Gli accostamenti si contano sui tavoli fisici: quelli del primo turno
  più quelli montati dopo, così una disposizione che non cambia costa come in "fissa".

Variabili (stessi nomi del modello a orari, così gli hint restano validi): slot p, b[f], x, y; prenotazioni a[i,s],
o[i,spostamento]; in "variabile" le chiavi degli slot portano il turno ("m3k1") e in più u, r per slot e turno.
"""
from __future__ import annotations

from ortools.sat.python import cp_model

from .dati import VARIABILE, ErroreDati, Istanza
from .modello import _Modello, _Slot, _Voce, _pesi


def _opzioni_turno(ist: Istanza, v: _Voce) -> list[tuple[int, int, int]]:
    """Le opzioni (spostamento, passo) della prenotazione come (spostamento, passo, turno)."""
    out = []
    for sm, st in v.opzioni:
        k = ist.turno_da_passo(st)
        if k is None:
            raise ErroreDati(f"{v.pr.id}: l'opzione al passo {st} non è l'inizio di un turno")
        out.append((sm, st, k))
    return out


def _slot_moduli(m, ist: Istanza, chiave: str, proiezioni: bool) -> tuple[_Slot, tuple]:
    forme = ist.forme_moduli
    W, H = ist.larghezza_g, ist.altezza_g
    min_l, min_h = min(f.ingombro_l for f in forme), min(f.ingombro_h for f in forme)
    dom_l = cp_model.Domain.from_values(sorted({0} | {f.ingombro_l for f in forme}))
    dom_h = cp_model.Domain.from_values(sorted({0} | {f.ingombro_h for f in forme}))
    p = m.new_bool_var(f"p_{chiave}")
    bs = [(f, m.new_bool_var(f"b_{chiave}_{f.nome}")) for f in forme]
    m.add(sum(b for _, b in bs) == p)
    x = m.new_int_var(0, W - min_l, f"x_{chiave}")
    y = m.new_int_var(0, H - min_h, f"y_{chiave}")
    w = m.new_int_var_from_domain(dom_l, f"w_{chiave}")
    h = m.new_int_var_from_domain(dom_h, f"h_{chiave}")
    m.add(w == sum(f.ingombro_l * b for f, b in bs))
    m.add(h == sum(f.ingombro_h * b for f, b in bs))
    xe = m.new_int_var(0, W, f"xe_{chiave}")
    ye = m.new_int_var(0, H, f"ye_{chiave}")
    m.add(xe == x + w)
    m.add(ye == y + h)
    box = (m.new_optional_interval_var(x, w, xe, p, f"ix_{chiave}"), m.new_optional_interval_var(y, h, ye, p, f"iy_{chiave}"))
    if proiezioni:      # ridondante: x e y tra le posizioni libere della forma nella sala vuota
        for f, b in bs:
            xs, ys = ist.posizioni[f.nome]
            m.add_linear_expression_in_domain(x, cp_model.Domain.from_values(xs)).only_enforce_if(b)
            m.add_linear_expression_in_domain(y, cp_model.Domain.from_values(ys)).only_enforce_if(b)
    m.add(x == 0).only_enforce_if(~p)
    m.add(y == 0).only_enforce_if(~p)
    sl = _Slot(chiave, "moduli", p, x, y, bs, sum(f.capienza * b for f, b in bs), sum(f.moduli * b for f, b in bs),
               max(f.capienza for f in forme))
    return sl, box


def _slot_tondo(m, ist: Istanza, chiave: str, proiezioni: bool) -> tuple[_Slot, tuple]:
    ft = ist.forma_tondo
    p = m.new_bool_var(f"p_{chiave}")
    x = m.new_int_var(0, ist.larghezza_g - ft.ingombro_l, f"x_{chiave}")
    y = m.new_int_var(0, ist.altezza_g - ft.ingombro_h, f"y_{chiave}")
    box = (m.new_optional_fixed_size_interval_var(x, ft.ingombro_l, p, f"ix_{chiave}"),
           m.new_optional_fixed_size_interval_var(y, ft.ingombro_h, p, f"iy_{chiave}"))
    if proiezioni:
        xs, ys = ist.posizioni[ft.nome]
        m.add_linear_expression_in_domain(x, cp_model.Domain.from_values(xs)).only_enforce_if(p)
        m.add_linear_expression_in_domain(y, cp_model.Domain.from_values(ys)).only_enforce_if(p)
    m.add(x == 0).only_enforce_if(~p)
    m.add(y == 0).only_enforce_if(~p)
    return _Slot(chiave, "tondo", p, x, y, [(ft, p)], ft.capienza * p, 0, ft.capienza), box


def _rompi_simmetrie(m, mod_slots: list[_Slot], tondi: list[_Slot]) -> None:
    """Slot intercambiabili: moduli non crescenti (quindi presenza non crescente), a parità x non decrescente."""
    for s1, s2 in zip(mod_slots, mod_slots[1:]):
        m.add(s1.moduli >= s2.moduli)
        m.add(s1.p >= s2.p)
        uguali = m.new_bool_var(f"ugk_{s1.chiave}")
        m.add(s1.moduli == s2.moduli).only_enforce_if(uguali)
        m.add(s1.moduli != s2.moduli).only_enforce_if(~uguali)
        m.add(s1.x <= s2.x).only_enforce_if(uguali)
    for s1, s2 in zip(tondi, tondi[1:]):
        m.add(s1.p >= s2.p)
        m.add(s1.x <= s2.x).only_enforce_if(s2.p)


def costruisci_turni(ist: Istanza, voci: list[_Voce], disposizione: str, obiettivo: str = "completo",
                     non_sistemate_fisse: int = 0, proiezioni: bool = True, rinforzo: bool = True) -> _Modello:
    """Stessa interfaccia di `modello._costruisci`, per una sala a turni."""
    pesi = _pesi(ist)
    m = cp_model.CpModel()
    K = len(ist.turni)
    variabile = disposizione == VARIABILE
    mod = _Modello(m, [], voci, disposizione=disposizione, turni=True)
    forme, ft = ist.forme_moduli, ist.forma_tondo
    cap_mod = max((f.capienza for f in forme), default=0)
    opz = {v.pr.id: _opzioni_turno(ist, v) for v in voci}
    # quante prenotazioni possono sedersi in ogni turno: più slot di così non servono mai
    el_mod, el_t = [0] * K, [0] * K
    for v in voci:
        for k in {k for _, _, k in opz[v.pr.id]}:
            el_mod[k] += v.pr.coperti <= cap_mod
            el_t[k] += ft is not None and v.pr.coperti <= ft.capienza
    fx_box = [m.new_fixed_size_interval_var(r.x0, r.x1 - r.x0, f"fx_{r.nome}") for r in ist.fissi_disgiunti_g]
    fy_box = [m.new_fixed_size_interval_var(r.y0, r.y1 - r.y0, f"fy_{r.nome}") for r in ist.fissi_disgiunti_g]
    per_turno: list[list[_Slot]] = [[] for _ in range(K)]       # slot che esistono nel turno k
    accostamenti, riallestimenti = [], []

    if not variabile:
        n_m = min(ist.n_moduli, max(el_mod, default=0)) if forme else 0
        n_t = min(ist.n_tondi, max(el_t, default=0)) if ft is not None else 0
        boxes = []
        for s in range(n_m):
            sl, bx = _slot_moduli(m, ist, f"m{s}", proiezioni)
            mod.slots.append(sl)
            boxes.append(bx)
            mod.info_slot[sl.chiave] = ("m", s, None)
        for r_ in range(n_t):
            sl, bx = _slot_tondo(m, ist, f"t{r_}", proiezioni)
            mod.slots.append(sl)
            boxes.append(bx)
            mod.info_slot[sl.chiave] = ("t", r_, None)
        mod_slots = [sl for sl in mod.slots if sl.tipo == "moduli"]
        _rompi_simmetrie(m, mod_slots, [sl for sl in mod.slots if sl.tipo == "tondo"])
        m.add_no_overlap_2d([b[0] for b in boxes] + fx_box, [b[1] for b in boxes] + fy_box)
        if mod_slots:
            m.add(sum(sl.moduli for sl in mod_slots) <= ist.n_moduli)
        for k in range(K):
            per_turno[k] = list(mod.slots)
        accostamenti = [sl.moduli - sl.p for sl in mod_slots]
    else:
        n_m = [min(ist.n_moduli, el_mod[k]) if forme else 0 for k in range(K)]
        n_t = [min(ist.n_tondi, el_t[k]) if ft is not None else 0 for k in range(K)]
        per_chiave: dict[tuple, _Slot] = {}
        for k in range(K):
            boxes = []
            for pref, n, crea in (("m", n_m[k], _slot_moduli), ("t", n_t[k], _slot_tondo)):
                for s in range(n):
                    sl, bx = crea(m, ist, f"{pref}{s}k{k}", proiezioni)
                    mod.slots.append(sl)
                    per_turno[k].append(sl)
                    boxes.append(bx)
                    per_chiave[(pref, s, k)] = sl
                    mod.info_slot[sl.chiave] = (pref, s, k)
            if boxes:
                m.add_no_overlap_2d([b[0] for b in boxes] + fx_box, [b[1] for b in boxes] + fy_box)
            ms = [sl for sl in per_turno[k] if sl.tipo == "moduli"]
            if ms:
                m.add(sum(sl.moduli for sl in ms) <= ist.n_moduli)
            if k == 0:      # nel primo turno gli slot sono intercambiabili; dopo l'indice lega allo slot di prima
                _rompi_simmetrie(m, ms, [sl for sl in per_turno[k] if sl.tipo == "tondo"])
                accostamenti += [sl.moduli - sl.p for sl in ms]
        kmax = max((f.moduli for f in forme), default=1)
        for k in range(1, K):
            for pref, n in (("m", n_m[k]), ("t", n_t[k])):
                for s in range(n):
                    cur = per_chiave[(pref, s, k)]
                    prev = per_chiave.get((pref, s, k - 1))
                    r = m.new_bool_var(f"r_{cur.chiave}")        # montato a servizio iniziato
                    if prev is None:
                        m.add(r == cur.p)
                    else:
                        u = m.new_bool_var(f"u_{cur.chiave}")    # stesso tavolo del turno prima
                        m.add_implication(u, cur.p)
                        m.add_implication(u, prev.p)
                        for (_, b1), (_, b2) in zip(cur.forme, prev.forme):
                            m.add(b1 == b2).only_enforce_if(u)
                        m.add(cur.x == prev.x).only_enforce_if(u)
                        m.add(cur.y == prev.y).only_enforce_if(u)
                        m.add(r + u == cur.p)
                    cur.riall = r
                    riallestimenti.append(r)
                    if cur.tipo == "moduli":                     # accostamenti del tavolo montato (uguaglianza esatta)
                        ex = m.new_int_var(0, kmax - 1, f"ex_{cur.chiave}")
                        m.add(ex == cur.moduli - cur.p).only_enforce_if(r)
                        m.add(ex == 0).only_enforce_if(~r)
                        accostamenti.append(ex)
    mod.turni_slot = {sl.chiave: [k for k in range(K) if sl in per_turno[k]] for sl in mod.slots}

    # ------------------------------------------------------------ prenotazioni
    occ: dict[tuple, list] = {}          # (slot, turno) -> letterali "c'è una prenotazione"
    per_slot: dict[str, list] = {sl.chiave: [] for sl in mod.slots}
    spreco, non_sedute = [], []
    in_turno: list[list[tuple[int, object]]] = [[] for _ in range(K)]    # (coperti, letterale) per i ridondanti
    for v in voci:
        pr = v.pr
        olits = []
        for sm, st, k in opz[pr.id]:
            ov = m.new_bool_var(f"o_{pr.id}_{sm}")
            mod.o[(pr.id, sm)] = ov
            olits.append((k, ov))
            in_turno[k].append((pr.coperti, ov))
        if v.obbligatoria:
            seduta = 1
        else:
            seduta = m.new_bool_var(f"seduta_{pr.id}")
            non_sedute.append(1 - seduta)
        m.add(sum(ov for _, ov in olits) == seduta)

        def assegna(sl: _Slot):
            av = m.new_bool_var(f"a_{pr.id}_{sl.chiave}")
            mod.a[(pr.id, sl.chiave)] = av
            per_slot[sl.chiave].append(av)
            m.add_implication(av, sl.p)
            if sl.tipo == "moduli":
                m.add(sl.capienza >= pr.coperti).only_enforce_if(av)
                sp = m.new_int_var(0, sl.cap_max - pr.coperti, f"vuoti_{pr.id}_{sl.chiave}")
                m.add(sp == sl.capienza - pr.coperti).only_enforce_if(av)
                m.add(sp == 0).only_enforce_if(~av)
                spreco.append(sp)
            else:
                spreco.append((sl.cap_max - pr.coperti) * av)
            return av

        n_eleggibili = 0
        if not variabile:
            lits = []
            for sl in mod.slots:
                if pr.coperti > sl.cap_max:
                    continue
                av = assegna(sl)
                lits.append(av)
                if len(olits) == 1:
                    occ.setdefault((sl.chiave, olits[0][0]), []).append(av)
                else:            # più turni possibili: z = seduta su sl E nel turno k
                    for k, ov in olits:
                        z = m.new_bool_var(f"z_{pr.id}_{sl.chiave}_{k}")
                        m.add(z <= av)
                        m.add(z <= ov)
                        m.add(z >= av + ov - 1)
                        occ.setdefault((sl.chiave, k), []).append(z)
            n_eleggibili = len(lits)
            if lits:
                m.add(sum(lits) == seduta)
            elif not v.obbligatoria:
                m.add(seduta == 0)
        else:
            for k, ov in olits:
                lits = []
                for sl in per_turno[k]:
                    if pr.coperti <= sl.cap_max:
                        av = assegna(sl)
                        lits.append(av)
                        occ.setdefault((sl.chiave, k), []).append(av)
                n_eleggibili += len(lits)
                m.add(sum(lits) == ov) if lits else m.add(ov == 0)
        if v.obbligatoria and not n_eleggibili:
            raise ErroreDati(f"{pr.id}: obbligatoria ma senza tavoli possibili")

    # al più una prenotazione per tavolo e per turno; un tavolo presente ospita almeno una prenotazione
    for sl in mod.slots:
        for k in mod.turni_slot[sl.chiave]:
            lst = occ.get((sl.chiave, k), [])
            if len(lst) > 1:
                m.add(sum(lst) <= sl.p)
        if per_slot[sl.chiave]:
            m.add(sum(per_slot[sl.chiave]) >= sl.p)
        else:
            m.add(sl.p == 0)

    if rinforzo:
        # ridondanti: in ogni turno, per ogni soglia c di coperti, i tavoli con capienza >= c sono almeno quante
        # le prenotazioni del turno con almeno c coperti
        for k in range(K):
            for c in sorted({cop for cop, _ in in_turno[k]}):
                rhs = [ov for cop, ov in in_turno[k] if cop >= c]
                grandi = []
                for sl in per_turno[k]:
                    if sl.tipo == "moduli":
                        grandi += [b for f, b in sl.forme if f.capienza >= c]
                    elif sl.cap_max >= c:
                        grandi.append(sl.p)
                m.add(sum(grandi) >= sum(rhs))

    totale = (pesi["non_sistemata"] * (sum(non_sedute) + non_sistemate_fisse)
              + pesi["posto_vuoto"] * sum(spreco)
              + pesi["accostamento_per_modulo"] * sum(accostamenti)
              + pesi["riallestimento"] * sum(riallestimenti))
    if obiettivo == "completo":
        m.minimize(totale)
    elif obiettivo != "nessuno":
        raise ValueError(obiettivo)
    return mod


def estrai_turni(ist: Istanza, mod: _Modello, piano: dict) -> tuple[list, list, set]:
    """Tavoli fisici e assegnazioni dal piano. In "variabile" un tavolo che resta uguale nel turno dopo è lo stesso
    tavolo: esiste dall'inizio del primo turno in cui c'è alla fine dell'ultimo."""
    from .dati import min_a_hhmm

    def V(x):
        return x if isinstance(x, int) else piano[x.name]

    g, mg = ist.griglia, ist.margine
    K = len(ist.turni)
    catene: list[dict] = []
    di_slot: dict[str, dict] = {}         # chiave slot -> catena (tavolo fisico)
    ultimo: dict[tuple, dict] = {}        # (pref, s) -> catena del turno precedente
    presenti = [sl for sl in mod.slots if V(sl.p)]
    for sl in sorted(presenti, key=lambda sl: (mod.turni_slot[sl.chiave][0], sl.chiave)):
        pref, s, k = mod.info_slot[sl.chiave]
        forma = next(f for f, b in sl.forme if V(b))
        if mod.disposizione == VARIABILE and k > 0 and not V(sl.riall) and (pref, s) in ultimo:
            c = ultimo[(pref, s)]
            c["turni"].append(k)
        else:
            c = {"forma": forma, "fx": V(sl.x), "fy": V(sl.y), "turni": list(mod.turni_slot[sl.chiave])}
            catene.append(c)
        di_slot[sl.chiave] = c
        ultimo[(pref, s)] = c
    catene.sort(key=lambda c: (c["turni"][0], c["fy"], c["fx"]))
    tavoli = []
    for n, c in enumerate(catene, start=1):
        c["id"] = f"T{n}"
        f = c["forma"]
        x_cm, y_cm = c["fx"] * g + mg, c["fy"] * g + mg
        k0, k1 = c["turni"][0], c["turni"][-1]
        tav = {"id": c["id"], "tipo": f.tipo, "moduli": f.moduli,
               "orientamento": f.orientamento if f.tipo == "moduli" else None,
               "x_cm": x_cm, "y_cm": y_cm, "larghezza_cm": f.larghezza_cm, "altezza_cm": f.altezza_cm,
               "capienza": f.capienza,
               "ingombro_cm": {"x0": x_cm - mg, "y0": y_cm - mg, "x1": x_cm + f.larghezza_cm + mg,
                               "y1": y_cm + f.altezza_cm + mg},
               "esiste_dal": min_a_hhmm(ist.turni[k0].inizio_min), "esiste_al": min_a_hhmm(ist.turni[k1].fine_min),
               "fino_a_chiusura": k1 == K - 1, "montato_in_servizio": k0 > 0,
               "turni": [ist.turni[k].nome for k in c["turni"]]}
        if f.tipo == "tondo":
            tav["diametro_cm"] = f.larghezza_cm
        tavoli.append(tav)
    assegnazioni, sedute = [], set()
    for v in mod.voci:
        chiave = next((ch for (pid, ch), av in mod.a.items() if pid == v.pr.id and V(av)), None)
        if chiave is None:
            continue
        sm = next(sm for (pid, sm), ov in mod.o.items() if pid == v.pr.id and V(ov))
        k = ist.turno_da_passo(next(st for s_, st in v.opzioni if s_ == sm))
        tu = ist.turni[k]
        sedute.add(v.pr.id)
        assegnazioni.append({
            "id": v.pr.id, "nome": v.pr.nome, "coperti": v.pr.coperti,
            "orario_richiesto": min_a_hhmm(v.pr.orario_min), "orario_assegnato": min_a_hhmm(tu.inizio_min),
            "spostamento_min": 0, "fine": min_a_hhmm(tu.fine_min), "tavolo": di_slot[chiave]["id"],
            "note": v.pr.note, "turno": tu.nome, "turno_richiesto": ist.turni[ist.turno_della(v.pr)].nome,
        })
    assegnazioni.sort(key=lambda r: (r["orario_assegnato"], int(r["tavolo"][1:])))
    return tavoli, assegnazioni, sedute


def impossibile_per_conteggio_turni(ist: Istanza, accettate: list[_Voce], pr, st: int,
                                    disposizione: str | None = None) -> bool:
    """Condizione SUFFICIENTE di impossibilità a turni: in un turno le prenotazioni chiedono più moduli
    dell'inventario, anche usando al meglio i tondi. In "fissa" i tavoli servono tutti i turni: il j-esimo tavolo più
    grande deve bastare alla j-esima prenotazione più grande di OGNI turno, quindi si conta il loro massimo."""
    K = len(ist.turni)
    cap_t = ist.forma_tondo.capienza if ist.forma_tondo is not None else 0
    n_t = ist.n_tondi if ist.forma_tondo is not None else 0

    def kmin(c):
        return min((f.moduli for f in ist.forme_moduli if f.capienza >= c), default=None)

    def troppi(coperti: list[int]) -> bool:
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
        return liberi < 0 or moduli - sum(sorted(risparmi, reverse=True)[:liberi]) > ist.n_moduli

    per_turno: list[list[int]] = [[] for _ in range(K)]
    for v in accettate:
        per_turno[ist.turno_da_passo(v.opzioni[0][1])].append(v.pr.coperti)
    per_turno[ist.turno_da_passo(st)].append(pr.coperti)
    if any(troppi(cop) for cop in per_turno):
        return True
    if disposizione != VARIABILE and disposizione is not None:
        ordinati = [sorted(c, reverse=True) for c in per_turno]
        n = max(len(c) for c in ordinati)
        unione = [max(c[j] if j < len(c) else 0 for c in ordinati) for j in range(n)]
        return troppi([c for c in unione if c > 0])
    return False
