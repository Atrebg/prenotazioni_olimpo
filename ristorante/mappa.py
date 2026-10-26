"""Mappa HTML/SVG della serata: un unico file autonomo (niente CDN, niente risorse esterne).

Legge solo la configurazione della sala, le prenotazioni e la soluzione JSON (non le variabili del modello).
Se la disposizione cambia durante la serata aggiunge un cursore orario (JavaScript inline) che mostra i tavoli
presenti in quel momento e chi ci siede, più l'elenco dei cambi sala. Se c'è un registro di accettazione lo
riporta in ordine di prenotazione.
"""
from __future__ import annotations

import math
from datetime import datetime
from html import escape
from pathlib import Path

COL_TAVOLO = "#d8b48a"
COL_BORDO_TAVOLO = "#8a5a2b"
COL_SEDIA = "#5d6d7e"
COL_OSTACOLO = "#9e9e9e"
COL_SPOSTATA = "#c0560b"
COL_BARRA = ["#4e79a7", "#59a14f", "#b07aa1", "#76b7b2", "#edc948", "#e15759", "#9c755f", "#f28e2b"]

SEDIA = 36        # lato della sedia disegnata (cm)
STACCO = 7        # distanza sedia-tavolo (cm)


def _min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(minuti: int) -> str:
    return f"{minuti // 60:02d}:{minuti % 60:02d}"


def _esistenza(t: dict, sala: dict) -> tuple[int, int]:
    fine = _min(sala["servizio"]["fine"]) + sala.get("riapparecchiatura_min", 0)
    return _min(t.get("esiste_dal", sala["servizio"]["inizio"])), (_min(t["esiste_al"]) if "esiste_al" in t else fine)


def _disposizione_cambia(sala: dict, sol: dict) -> bool:
    inizio = _min(sala["servizio"]["inizio"])
    fine = _min(sala["servizio"]["fine"]) + sala.get("riapparecchiatura_min", 0)
    return any(_esistenza(t, sala) != (inizio, fine) for t in sol["tavoli"])


def _sedie_lungo(x0, y0, x1, y1, n, nx, ny):
    """n sedie equidistanti lungo il lato (x0,y0)-(x1,y1), spostate verso l'esterno di (nx, ny)."""
    return [(x0 + (x1 - x0) * (i + 0.5) / n + nx * (STACCO + SEDIA / 2),
             y0 + (y1 - y0) * (i + 0.5) / n + ny * (STACCO + SEDIA / 2)) for i in range(n)]


def _sedie_moduli(t: dict, ppm: int, ptest: int) -> list:
    x, y, w, h, k = t["x_cm"], t["y_cm"], t["larghezza_cm"], t["altezza_cm"], t["moduli"]
    lato_a, lato_b = math.ceil(ppm / 2), ppm // 2
    test_a, test_b = math.ceil(ptest / 2), ptest // 2
    if t["orientamento"] == "orizzontale":
        return (_sedie_lungo(x, y, x + w, y, lato_a * k, 0, -1) + _sedie_lungo(x, y + h, x + w, y + h, lato_b * k, 0, 1)
                + _sedie_lungo(x, y, x, y + h, test_a, -1, 0) + _sedie_lungo(x + w, y, x + w, y + h, test_b, 1, 0))
    return (_sedie_lungo(x, y, x, y + h, lato_a * k, -1, 0) + _sedie_lungo(x + w, y, x + w, y + h, lato_b * k, 1, 0)
            + _sedie_lungo(x, y, x + w, y, test_a, 0, -1) + _sedie_lungo(x, y + h, x + w, y + h, test_b, 0, 1))


def _sedie_tondo(t: dict) -> list:
    r = t["larghezza_cm"] / 2
    cx, cy = t["x_cm"] + r, t["y_cm"] + r
    n = t["capienza"]
    rr = r + STACCO + SEDIA / 2
    return [(cx + rr * math.cos(-math.pi / 2 + 2 * math.pi * i / n),
             cy + rr * math.sin(-math.pi / 2 + 2 * math.pi * i / n)) for i in range(n)]


def _per_tavolo(sol: dict) -> dict:
    per_tav: dict[str, list] = {}
    for r in sol["assegnazioni"]:
        per_tav.setdefault(r["tavolo"], []).append(r)
    for lst in per_tav.values():
        lst.sort(key=lambda r: r["orario_assegnato"])
    return per_tav


def _svg_sala(sala: dict, sol: dict, dinamica: bool) -> str:
    W, H = sala["larghezza_cm"], sala["altezza_cm"]
    mg = sala["margine_sedie_cm"]
    mod = sala["inventario"]["moduli"]
    ppm, ptest, lato = mod.get("posti_per_modulo", 2), mod.get("posti_testate", 2), mod["lato_cm"]
    riapp = sala.get("riapparecchiatura_min", 0)
    inizio = _min(sala["servizio"]["inizio"])
    chiusura = _min(sala["servizio"]["fine"]) + riapp
    per_tav = _per_tavolo(sol)
    out = [f'<svg class="sala" viewBox="-30 -30 {W + 60} {H + 60}" xmlns="http://www.w3.org/2000/svg" '
           f'role="img" aria-label="Mappa della sala">',
           '<defs><pattern id="tratteggio" width="16" height="16" patternUnits="userSpaceOnUse" '
           'patternTransform="rotate(45)"><rect width="16" height="16" fill="#f3f6f8"/>'
           '<line x1="0" y1="0" x2="0" y2="16" stroke="#c9d3db" stroke-width="6"/></pattern></defs>',
           f'<rect x="0" y="0" width="{W}" height="{H}" fill="#fffdf8" stroke="#333" stroke-width="4"/>']
    for gx in range(100, W, 100):   # griglia leggera ogni metro
        out.append(f'<line x1="{gx}" y1="0" x2="{gx}" y2="{H}" stroke="#eee8dc" stroke-width="1"/>')
    for gy in range(100, H, 100):
        out.append(f'<line x1="0" y1="{gy}" x2="{W}" y2="{gy}" stroke="#eee8dc" stroke-width="1"/>')
    for c in sala.get("corsie", []):
        out.append(f'<rect x="{c["x0"]}" y="{c["y0"]}" width="{c["x1"] - c["x0"]}" height="{c["y1"] - c["y0"]}" '
                   f'fill="url(#tratteggio)" stroke="#b0bec5" stroke-dasharray="10 6" stroke-width="2">'
                   f'<title>{escape(c.get("nome", ""))} (corsia libera)</title></rect>')
        cx, cy = (c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2
        verticale = (c["y1"] - c["y0"]) > (c["x1"] - c["x0"])
        if not verticale and c["x1"] - c["x0"] > 500:   # corsie lunghe: etichetta a sinistra (al centro può esserci un ostacolo)
            cx = c["x0"] + 220
        rot = f' transform="rotate(-90 {cx} {cy})"' if verticale else ""
        out.append(f'<text x="{cx}" y="{cy + 6}" class="et-corsia" text-anchor="middle"{rot}>{escape(c.get("nome", ""))}</text>')
    for o in sala.get("ostacoli", []):
        out.append(f'<rect x="{o["x0"]}" y="{o["y0"]}" width="{o["x1"] - o["x0"]}" height="{o["y1"] - o["y0"]}" '
                   f'fill="{COL_OSTACOLO}" stroke="#757575" stroke-width="2"><title>{escape(o.get("nome", ""))}</title></rect>')
        if (o["x1"] - o["x0"]) >= 100:
            out.append(f'<text x="{(o["x0"] + o["x1"]) / 2}" y="{(o["y0"] + o["y1"]) / 2 + 6}" class="et-ostacolo" '
                       f'text-anchor="middle">{escape(o.get("nome", ""))}</text>')
        else:
            out.append(f'<text x="{o["x1"] + 6}" y="{o["y1"] + 16}" class="et-ostacolo-scuro">{escape(o.get("nome", ""))}</text>')

    for t in sol["tavoli"]:
        x, y, w, h = t["x_cm"], t["y_cm"], t["larghezza_cm"], t["altezza_cm"]
        dal, al = _esistenza(t, sala)
        prenot = per_tav.get(t["id"], [])
        quando = "" if (dal, al) == (inizio, chiusura) else \
            f'{_hhmm(dal)}–{"chiusura" if al == chiusura else _hhmm(al)}'
        tip = [f'{t["id"]} · {t["capienza"]} posti' + (f' · presente {quando}' if quando else "")]
        tip += [f'{r["orario_assegnato"]}-{r["fine"]} {r["nome"]} ×{r["coperti"]}'
                + (f' (richiesto {r["orario_richiesto"]})' if r["spostamento_min"] else "")
                + (f' — {r["note"]}' if r.get("note") else "") for r in prenot]
        out.append(f'<g class="tavolo" data-dal="{dal}" data-al="{al}"><title>{escape(chr(10).join(tip))}</title>')
        out.append(f'<rect x="{x - mg}" y="{y - mg}" width="{w + 2 * mg}" height="{h + 2 * mg}" fill="none" '
                   f'stroke="#c8b8a0" stroke-dasharray="6 6" stroke-width="1.5"/>')
        sedie = _sedie_tondo(t) if t["tipo"] == "tondo" else _sedie_moduli(t, ppm, ptest)
        for cx, cy in sedie:
            out.append(f'<rect x="{cx - SEDIA / 2:.1f}" y="{cy - SEDIA / 2:.1f}" width="{SEDIA}" height="{SEDIA}" rx="8" '
                       f'fill="{COL_SEDIA}"/>')
        if t["tipo"] == "tondo":
            out.append(f'<circle cx="{x + w / 2}" cy="{y + h / 2}" r="{w / 2}" fill="{COL_TAVOLO}" '
                       f'stroke="{COL_BORDO_TAVOLO}" stroke-width="3"/>')
        else:
            out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{COL_TAVOLO}" '
                       f'stroke="{COL_BORDO_TAVOLO}" stroke-width="3"/>')
            for j in range(1, t["moduli"]):   # giunture tra moduli accostati
                if t["orientamento"] == "orizzontale":
                    out.append(f'<line x1="{x + j * lato}" y1="{y}" x2="{x + j * lato}" y2="{y + h}" '
                               f'stroke="{COL_BORDO_TAVOLO}" stroke-width="1.5" stroke-dasharray="4 3"/>')
                else:
                    out.append(f'<line x1="{x}" y1="{y + j * lato}" x2="{x + w}" y2="{y + j * lato}" '
                               f'stroke="{COL_BORDO_TAVOLO}" stroke-width="1.5" stroke-dasharray="4 3"/>')
        # testo: etichetta + prenotazioni, centrato sul tavolo
        righe = [(f'{t["id"]} · {t["capienza"]} posti', "et-tavolo", "")]
        if quando:
            righe.append((quando, "et-quando", ""))
        for r in prenot:
            sp = r["spostamento_min"]
            segno = f' ({"+" if sp > 0 else "−"}{abs(sp)}′)' if sp else ""
            a = _min(r["orario_assegnato"])
            dati = f' data-inizio="{a}" data-fine="{_min(r["fine"])}"'
            righe.append((f'{r["orario_assegnato"]} {r["nome"]} ×{r["coperti"]}{segno}',
                          "et-pren spostata" if sp else "et-pren", dati))
            if r.get("note"):
                righe.append((f'↳ {r["note"]}', "et-nota", dati))
        passo = 17
        cy0 = y + h / 2 - (len(righe) - 1) * passo / 2 + 5
        for n, (testo, cls, dati) in enumerate(righe):
            out.append(f'<text x="{x + w / 2}" y="{cy0 + n * passo:.1f}" class="{cls}" text-anchor="middle"{dati}>'
                       f'{escape(testo)}</text>')
        out.append('</g>')
    out.append(f'<g class="scala"><line x1="{W - 230}" y1="{H + 18}" x2="{W - 130}" y2="{H + 18}" stroke="#333" stroke-width="3"/>'
               f'<text x="{W - 120}" y="{H + 24}" class="et-scala">1 m</text></g>')
    if dinamica:
        out.append(f'<text x="0" y="{H + 24}" class="et-ora-mappa" id="ora-mappa"></text>')
    out.append('</svg>')
    return "\n".join(out)


def _svg_timeline(sala: dict, sol: dict) -> str:
    inizio, fine = _min(sala["servizio"]["inizio"]), _min(sala["servizio"]["fine"])
    riapp = sala.get("riapparecchiatura_min", 0)
    soglia = sala.get("picco_cucina_soglia_coperti", 30)
    passo = sala.get("passo_orari_min", 15)
    sx = 3.4                    # px per minuto
    sin, riga, top = 190, 34, 34
    tavoli = sol["tavoli"]
    n_righe = len(tavoli)
    alt_cucina = 90
    larg = sin + (fine + riapp - inizio) * sx + 20
    alt = top + n_righe * riga + 30 + alt_cucina + 30
    X = lambda m: sin + (m - inizio) * sx  # noqa: E731
    out = [f'<svg class="timeline" viewBox="0 0 {larg:.0f} {alt}" xmlns="http://www.w3.org/2000/svg" '
           f'role="img" aria-label="Timeline per tavolo">',
           '<defs><pattern id="riapp2" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
           '<rect width="6" height="6" fill="#eeeeee"/><line x1="0" y1="0" x2="0" y2="6" stroke="#b5b5b5" stroke-width="2"/>'
           '</pattern></defs>']
    for m_ in range(inizio, fine + 1, passo):
        forte = (m_ - inizio) % 60 == 0
        out.append(f'<line x1="{X(m_):.1f}" y1="{top - 6}" x2="{X(m_):.1f}" y2="{top + n_righe * riga}" '
                   f'stroke="{"#bbb" if forte else "#e3e3e3"}" stroke-width="1"/>')
        if (m_ - inizio) % 30 == 0:
            out.append(f'<text x="{X(m_):.1f}" y="{top - 12}" class="et-ora" text-anchor="middle">{_hhmm(m_)}</text>')
    per_tav = _per_tavolo(sol)
    for i, t in enumerate(tavoli):
        y = top + i * riga
        if i % 2 == 0:
            out.append(f'<rect x="0" y="{y}" width="{larg:.0f}" height="{riga}" fill="#faf7f2"/>')
        dal, al = _esistenza(t, sala)
        out.append(f'<rect x="{X(dal):.1f}" y="{y + 2}" width="{(al - dal) * sx:.1f}" height="{riga - 4}" fill="#efe6d6" '
                   f'stroke="#d9c9ad" stroke-width="1"><title>{t["id"]} presente {_hhmm(dal)}–{_hhmm(al)}</title></rect>')
        desc = "tondo" if t["tipo"] == "tondo" else (f'{t["moduli"]} moduli' if t["moduli"] > 1 else "1 modulo")
        out.append(f'<text x="8" y="{y + riga / 2 + 5}" class="et-riga"><tspan font-weight="700">{t["id"]}</tspan> · '
                   f'{desc} · {t["capienza"]} posti</text>')
        for j, r in enumerate(per_tav.get(t["id"], [])):
            a, b = _min(r["orario_assegnato"]), _min(r["fine"])
            col = COL_BARRA[(i + j) % len(COL_BARRA)]
            out.append(f'<rect x="{X(b):.1f}" y="{y + 6}" width="{riapp * sx:.1f}" height="{riga - 12}" fill="url(#riapp2)">'
                       f'<title>riapparecchiatura {riapp} min</title></rect>')
            bordo = f' stroke="{COL_SPOSTATA}" stroke-width="3"' if r["spostamento_min"] else ""
            tip = (f'{r["nome"]} ×{r["coperti"]}: {r["orario_assegnato"]}-{r["fine"]} '
                   f'(richiesto {r["orario_richiesto"]})' + (f' — {r["note"]}' if r.get("note") else ""))
            out.append(f'<rect x="{X(a):.1f}" y="{y + 5}" width="{(b - a) * sx:.1f}" height="{riga - 10}" rx="4" '
                       f'fill="{col}"{bordo}><title>{escape(tip)}</title></rect>')
            if r["spostamento_min"]:
                xr = X(_min(r["orario_richiesto"]))
                out.append(f'<line x1="{xr:.1f}" y1="{y + 2}" x2="{xr:.1f}" y2="{y + riga - 2}" stroke="{COL_SPOSTATA}" '
                           f'stroke-width="2" stroke-dasharray="3 2"><title>orario richiesto {r["orario_richiesto"]}</title></line>')
            sp = r["spostamento_min"]
            segno = f' {"+" if sp > 0 else "−"}{abs(sp)}′' if sp else ""
            nota = " ★" if r.get("note") else ""
            out.append(f'<text x="{X(a) + 6:.1f}" y="{y + riga / 2 + 5}" class="et-barra">'
                       f'{escape(r["nome"])} ×{r["coperti"]}{segno}{nota}</text>')
    # carico cucina: coperti che iniziano per passo
    y0 = top + n_righe * riga + 30
    partenze: dict[int, int] = {}
    for r in sol["assegnazioni"]:
        partenze[_min(r["orario_assegnato"])] = partenze.get(_min(r["orario_assegnato"]), 0) + r["coperti"]
    massimo = max([soglia + 5] + list(partenze.values()))
    scala = alt_cucina / massimo
    out.append(f'<text x="8" y="{y0 + alt_cucina / 2}" class="et-riga"><tspan font-weight="700">Cucina</tspan></text>'
               f'<text x="8" y="{y0 + alt_cucina / 2 + 16}" class="et-piccolo">coperti che iniziano</text>')
    out.append(f'<line x1="{sin}" y1="{y0 + alt_cucina}" x2="{X(fine):.1f}" y2="{y0 + alt_cucina}" stroke="#999"/>')
    ys = y0 + alt_cucina - soglia * scala
    out.append(f'<line x1="{sin}" y1="{ys:.1f}" x2="{X(fine):.1f}" y2="{ys:.1f}" stroke="#e15759" stroke-dasharray="5 4"/>'
               f'<text x="{X(fine) - 4:.1f}" y="{ys - 4:.1f}" class="et-piccolo" text-anchor="end" fill="#e15759">soglia {soglia}</text>')
    for m_, c in sorted(partenze.items()):
        hgt = c * scala
        col = "#e15759" if c > soglia else "#8c8c8c"
        out.append(f'<rect x="{X(m_) + 2:.1f}" y="{y0 + alt_cucina - hgt:.1f}" width="{passo * sx - 4:.1f}" height="{hgt:.1f}" '
                   f'fill="{col}"><title>{_hhmm(m_)}: {c} coperti</title></rect>'
                   f'<text x="{X(m_) + passo * sx / 2:.1f}" y="{y0 + alt_cucina - hgt - 4:.1f}" class="et-piccolo" '
                   f'text-anchor="middle">{c}</text>')
    out.append('</svg>')
    return "\n".join(out)


def cambi_sala(sala: dict, sol: dict) -> list[tuple[int, str]]:
    """Elenco dei cambi di disposizione durante il servizio: (minuto, descrizione)."""
    inizio = _min(sala["servizio"]["inizio"])
    chiusura = _min(sala["servizio"]["fine"]) + sala.get("riapparecchiatura_min", 0)
    per_tav = _per_tavolo(sol)
    eventi: dict[int, dict[str, list]] = {}
    for t in sol["tavoli"]:
        dal, al = _esistenza(t, sala)
        if al < chiusura:
            eventi.setdefault(al, {"smonta": [], "monta": []})["smonta"].append(t)
        if dal > inizio:
            eventi.setdefault(dal, {"smonta": [], "monta": []})["monta"].append(t)
    out = []
    for m_, ev in sorted(eventi.items()):
        parti = []
        if ev["smonta"]:
            nomi = ", ".join(f'{t["id"]} ({"tondo" if t["tipo"] == "tondo" else str(t["moduli"]) + " mod."})'
                             for t in ev["smonta"])
            parti.append(("si smonta " if len(ev["smonta"]) == 1 else "si smontano ") + nomi)
        for t in ev["monta"]:
            prima = per_tav.get(t["id"], [{}])[0]
            per = f'per {prima.get("nome", "?")} ×{prima.get("coperti", "?")}'
            if t["tipo"] == "tondo":
                parti.append(f'si porta un tondo {per} ({t["id"]}, {t["capienza"]} posti)')
            elif t["moduli"] > 1:
                parti.append(f'si uniscono {t["moduli"]} moduli {per} ({t["id"]}, {t["capienza"]} posti)')
            else:
                parti.append(f'si aggiunge un tavolo da {t["capienza"]} {per} ({t["id"]})')
        out.append((m_, " · ".join(parti)))
    return out


def _sintesi(sala: dict, sol: dict, totale_coperti: int, totale_pren: int) -> str:
    ass, nons, tav = sol["assegnazioni"], sol["non_sistemate"], sol["tavoli"]
    coperti = sum(r["coperti"] for r in ass)
    spostate = [r for r in ass if r["spostamento_min"]]
    minuti = sum(abs(r["spostamento_min"]) for r in spostate)
    inv = sala["inventario"]
    accostati = [t for t in tav if t["tipo"] == "moduli" and t["moduli"] > 1]
    s = sol["solver"]
    comp = sol["obiettivo_componenti"]
    mod = sol.get("modalita", {})
    acc = sol.get("accettazione")
    # moduli e tondi in uso al massimo in un istante
    picco_m = picco_t = 0
    for t in tav:
        dal = _esistenza(t, sala)[0]
        vivi = [u for u in tav if _esistenza(u, sala)[0] <= dal < _esistenza(u, sala)[1]]
        picco_m = max(picco_m, sum(u["moduli"] for u in vivi if u["tipo"] == "moduli"))
        picco_t = max(picco_t, sum(1 for u in vivi if u["tipo"] == "tondo"))
    righe_ns = "".join(
        f'<li><b>{escape(r["nome"])}</b> ×{r["coperti"]} alle {r["orario_richiesto"]}: {escape(r["motivo"])}</li>'
        for r in nons) or "<li>nessuna</li>"
    bound = f'{s["bound"]}' if s.get("bound") is not None else "—"
    gap = f'{s["gap_pct"]}%' if s.get("gap_pct") is not None else "—"
    voci = [
        ("non sistemate", comp["non_sistemate"]["costo"], f'{comp["non_sistemate"]["numero"]}'),
        ("posti vuoti", comp["posti_vuoti"]["costo"], f'{comp["posti_vuoti"]["posti"]} posti'),
        ("spostamenti", comp["spostamenti"]["costo"], f'{comp["spostamenti"]["quarti_d_ora"]} quarti d\'ora'),
        ("accostamenti", comp["accostamenti"]["costo"], f'{comp["accostamenti"]["moduli_oltre_il_primo"]} moduli oltre il primo'),
        ("picco cucina", comp["picco_cucina"]["costo"], f'{comp["picco_cucina"]["coperti_oltre_soglia"]} coperti oltre {comp["picco_cucina"]["soglia"]}'),
        ("riallestimenti", comp.get("riallestimenti", {}).get("costo", 0), f'{comp.get("riallestimenti", {}).get("numero", 0)} tavoli montati a servizio iniziato'),
    ]
    tab_ob = "".join(f'<tr><td>{n}</td><td class="num">{c}</td><td>{escape(d)}</td></tr>' for n, c, d in voci)
    kpi_acc = ""
    nota_solver = "FEASIBLE = migliore soluzione trovata nel tempo limite, ottimalità non dimostrata."
    if acc:
        kpi_acc = (f'<div class="kpi"><div class="v">{acc["decisioni_ammissibili"]} · {acc.get("decisioni_ammissibili_su_proposta", 0)} · {acc["decisioni_impossibili_dimostrate"] + acc["decisioni_impossibili_a_priori"]} · {acc["decisioni_unknown"]}</div>'
                   f'<div class="l">decisioni: ammissibili · con proposta · impossibili · UNKNOWN</div></div>'
                   f'<div class="kpi"><div class="v">{acc.get("accettate_su_proposta", 0)}</div>'
                   f'<div class="l">accettate su proposta · {acc.get("proposte_rifiutate_dal_cliente", 0)} proposte non accettate</div></div>')
        nota_solver = (f'Piantina finale ({escape(str(s.get("origine", "")))}). ' + nota_solver +
                       f' Decisioni di accettazione: limite {acc["tempo_decisione_limite_s"]} s ciascuna, '
                       f'{acc["tempo_decisioni_s"]} s in tutto.')
    return f"""
<div class="sintesi">
  <div class="kpi"><div class="v">{coperti}/{totale_coperti}</div><div class="l">coperti sistemati</div></div>
  <div class="kpi"><div class="v">{len(ass)}/{totale_pren}</div><div class="l">prenotazioni sistemate</div></div>
  <div class="kpi"><div class="v">{len(spostate)}</div><div class="l">spostate ({minuti} min in tutto)</div></div>
  <div class="kpi"><div class="v">{picco_m}/{inv["moduli"]["quantita"]}</div><div class="l">moduli in uso al massimo · tondi {picco_t}/{inv.get("tondi", {}).get("quantita", 0)}</div></div>
  <div class="kpi"><div class="v">{len(tav)}</div><div class="l">tavoli · {len(accostati)} con moduli accostati · {comp.get("riallestimenti", {}).get("numero", 0)} riallestimenti</div></div>
  <div class="kpi"><div class="v">{escape(s["stato"])}</div><div class="l">stato del solver · {s.get("tempo_s", "—")} s</div></div>
  {kpi_acc}
</div>
<p class="sotto">Accettazione: <b>{escape(str(mod.get("accettazione", "tutte_insieme")).replace("_", " "))}</b> ·
disposizione: <b>{escape(str(mod.get("disposizione", "fissa")))}</b></p>
<div class="due">
  <div class="box"><h3>Non sistemate</h3><ul>{righe_ns}</ul></div>
  <div class="box"><h3>Obiettivo {s.get("obiettivo", "—")} <span class="tenue">(bound {bound}, gap {gap})</span></h3>
    <div class="scorri"><table class="ob"><tr><th>componente</th><th>costo</th><th>dettaglio</th></tr>{tab_ob}</table></div>
    <p class="tenue">OR-Tools {escape(str(s.get("versione_ortools", "")))} · {s.get("worker", "—")} worker · seed {s.get("seed", "—")}.
    {nota_solver}</p>
  </div>
</div>"""


def _data(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return iso or ""


def _registro(sol: dict) -> str:
    righe = []
    etichette = {"accettata": "✓ accettata", "accettata su proposta": "↻ accettata su proposta", "rifiutata": "✗ rifiutata"}
    for r in sol.get("registro", []):
        esito = r["esito"]
        ok = esito in ("accettata", "accettata su proposta")
        sp = r.get("spostamento_min") or 0
        promesso = (f'{r["orario_promesso"]}' + (f' ({"+" if sp > 0 else "−"}{abs(sp)}′)' if sp else "")) if ok else "—"
        proposte = " / ".join(f"{nome} {r[k]}" for nome, k in (("prima", "proposta_prima"), ("dopo", "proposta_dopo"))
                              if r.get(k)) or "—"
        dettaglio = r.get("motivo") or ("spostamento minimo non dimostrato" if r.get("spostamento_minimo_dimostrato") is False else "")
        cls = {"accettata su proposta": "proposta", "rifiutata": "nonsist"}.get(esito, "")
        righe.append(f'<tr class="{cls}"><td class="num">{r["ordine"]}</td><td>{_data(r["prenotata_il"])}</td>'
                     f'<td>{escape(r["nome"])} ×{r["coperti"]}</td><td>{r["orario_richiesto"]}</td>'
                     f'<td>{etichette.get(esito, escape(esito))}</td><td>{promesso}</td><td>{escape(proposte)}</td>'
                     f'<td>{escape(dettaglio)}</td><td>{escape(str(r.get("stato_solver", "")))}</td>'
                     f'<td class="num">{r.get("tempo_s", "")}</td></tr>')
    return ('<div class="scorri"><table class="elenco"><tr><th>n°</th><th>ricevuta il</th><th>cliente</th><th>richiesto</th>'
            '<th>esito</th><th>orario promesso</th><th>proposte</th><th>motivo</th><th>solver (spostamenti ammessi)</th>'
            '<th>s</th></tr>' + "".join(righe) + "</table></div>")


def _elenco(sol: dict) -> str:
    righe = []
    su_proposta = {r["id"] for r in sol.get("registro", []) if r.get("esito") == "accettata su proposta"}
    for r in sorted(sol["assegnazioni"], key=lambda r: (r["orario_assegnato"], int(r["tavolo"][1:]))):
        sp = r["spostamento_min"]
        cls = ' class="proposta"' if r["id"] in su_proposta else (' class="spostata"' if sp else "")
        righe.append(f'<tr{cls}><td>{escape(r["id"])}</td><td>{escape(r["nome"])}</td><td class="num">{r["coperti"]}</td>'
                     f'<td>{r["orario_richiesto"]}</td><td>{r["orario_assegnato"]}</td>'
                     f'<td>{("+" if sp > 0 else "−") + str(abs(sp)) + "′" if sp else ""}</td><td>{r["fine"]}</td>'
                     f'<td>{escape(r["tavolo"])}</td><td>{escape(r.get("note", ""))}</td></tr>')
    for r in sol["non_sistemate"]:
        righe.append(f'<tr class="nonsist"><td>{escape(r["id"])}</td><td>{escape(r["nome"])}</td><td class="num">{r["coperti"]}</td>'
                     f'<td>{r["orario_richiesto"]}</td><td colspan="4">non sistemata: {escape(r["motivo"])}</td>'
                     f'<td>{escape(r.get("note", ""))}</td></tr>')
    return ('<div class="scorri"><table class="elenco"><tr><th>id</th><th>nome</th><th>coperti</th><th>richiesto</th><th>assegnato</th>'
            '<th>spost.</th><th>fine</th><th>tavolo</th><th>note</th></tr>' + "".join(righe) + "</table></div>")


CSS = """
body{font-family:"Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;margin:24px;color:#222;background:#fbfaf7}
h1{font-size:22px;margin:0 0 4px} h2{font-size:17px;margin:26px 0 8px} h3{font-size:15px;margin:0 0 8px}
.sotto{color:#666;margin:0 0 12px}
.sintesi{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px}
.kpi{background:#fff;border:1px solid #e3ddd2;border-radius:8px;padding:10px 14px;min-width:150px;flex:1 1 150px}
.kpi .v{font-size:22px;font-weight:700} .kpi .l{font-size:12px;color:#666}
.due{display:flex;flex-wrap:wrap;gap:12px}
.box{background:#fff;border:1px solid #e3ddd2;border-radius:8px;padding:12px 16px;flex:1 1 300px;min-width:0}
.box ul{margin:0;padding-left:18px}
.tenue{color:#777;font-weight:400;font-size:12px}
.scorri{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%}
table{border-collapse:collapse;font-size:13px} td,th{padding:3px 8px;border-bottom:1px solid #eee;text-align:left;white-space:nowrap}
td.num{text-align:right}
tr.spostata td{color:#c0560b} tr.nonsist td{color:#b00020;font-weight:600}
tr.proposta td{background:#e8f1fb;color:#0b4f9c;font-weight:600}
svg.sala,svg.timeline{width:100%;max-width:1250px;height:auto;background:#fff;border:1px solid #e3ddd2;border-radius:8px}
.et-tavolo{font-size:15px;font-weight:700;fill:#3b2410;paint-order:stroke;stroke:#fff;stroke-width:4px}
.et-quando{font-size:12px;fill:#6d4c2a;font-style:italic;paint-order:stroke;stroke:#fff;stroke-width:4px}
.et-pren{font-size:13.5px;fill:#111;paint-order:stroke;stroke:#fff;stroke-width:4px}
.et-pren.spostata{fill:#c0560b;font-weight:600}
.et-nota{font-size:12.5px;font-style:italic;fill:#6a1b9a;paint-order:stroke;stroke:#fff;stroke-width:4px}
.spenta{opacity:.35} .accesa{font-weight:700}
.et-corsia{font-size:16px;fill:#78909c;font-style:italic}
.et-ostacolo{font-size:16px;fill:#fff;font-weight:600}
.et-ostacolo-scuro{font-size:14px;fill:#616161}
.et-scala{font-size:14px;fill:#333} .et-ora-mappa{font-size:18px;font-weight:700;fill:#333}
.et-ora{font-size:12px;fill:#555} .et-riga{font-size:13px;fill:#222} .et-piccolo{font-size:11px;fill:#666}
.et-barra{font-size:12px;fill:#fff;font-weight:600;paint-order:stroke;stroke:rgba(0,0,0,.35);stroke-width:2px}
.legenda{font-size:12px;color:#555;margin:6px 0 0}
.legenda span{display:inline-block;margin-right:14px}
.q{display:inline-block;width:12px;height:12px;vertical-align:-2px;margin-right:4px;border:1px solid #999}
.cursore{background:#fff;border:1px solid #e3ddd2;border-radius:8px;padding:10px 14px;margin:0 0 8px;max-width:1220px}
.cursore input{width:100%} .cursore .ora{font-size:20px;font-weight:700;margin-right:10px}
.cambi{margin:6px 0 0;padding-left:18px} .cambi li{margin:2px 0}
@media (max-width:640px){
  body{margin:10px} h1{font-size:18px} .kpi{min-width:120px;padding:8px 10px} .kpi .v{font-size:18px}
  table{font-size:12px} td,th{padding:2px 5px}
}
"""

JS = """
(function(){
  var r=document.getElementById('ora'); if(!r) return;
  var et=document.getElementById('ora-testo'), etm=document.getElementById('ora-mappa');
  function hh(m){return String(Math.floor(m/60)).padStart(2,'0')+':'+String(m%60).padStart(2,'0');}
  function aggiorna(){
    var m=+r.value, n=0;
    document.querySelectorAll('svg.sala g.tavolo').forEach(function(g){
      var vivo=(+g.dataset.dal<=m && m<+g.dataset.al); g.style.display=vivo?'':'none'; if(vivo) n++;});
    document.querySelectorAll('svg.sala [data-inizio]').forEach(function(t){
      var s=(+t.dataset.inizio<=m && m<+t.dataset.fine); t.classList.toggle('accesa',s); t.classList.toggle('spenta',!s);});
    et.textContent=hh(m)+' · '+n+' tavoli'; if(etm) etm.textContent=hh(m);
  }
  r.addEventListener('input',aggiorna); aggiorna();
})();
"""


def _ora_di_punta(sala: dict, sol: dict) -> int:
    inizio, fine = _min(sala["servizio"]["inizio"]), _min(sala["servizio"]["fine"])
    passo = sala.get("passo_orari_min", 15)
    migliore, ora = -1, inizio
    for m_ in range(inizio, fine, passo):
        n = sum(r["coperti"] for r in sol["assegnazioni"] if _min(r["orario_assegnato"]) <= m_ < _min(r["fine"]))
        if n > migliore:
            migliore, ora = n, m_
    return ora


def genera_html(sala: dict, prenotazioni: dict, sol: dict) -> str:
    tot_cop = sum(p["coperti"] for p in prenotazioni["prenotazioni"])
    tot_pren = len(prenotazioni["prenotazioni"])
    titolo = f'{sol.get("serata") or prenotazioni.get("serata", "Serata")} — {sol.get("sala") or sala.get("nome", "")}'
    dinamica = _disposizione_cambia(sala, sol)
    inizio, fine = _min(sala["servizio"]["inizio"]), _min(sala["servizio"]["fine"])
    passo = sala.get("passo_orari_min", 15)
    cursore = cambi = ""
    if dinamica:
        cursore = (f'<div class="cursore"><span class="ora" id="ora-testo"></span>'
                   f'<span class="tenue">sposta il cursore per vedere i tavoli presenti e chi ci siede</span>'
                   f'<input type="range" id="ora" min="{inizio}" max="{fine}" step="{passo}" '
                   f'value="{_ora_di_punta(sala, sol)}" aria-label="ora della serata"></div>')
        voci = "".join(f'<li><b>{_hhmm(m_)}</b> {escape(d)}</li>' for m_, d in cambi_sala(sala, sol))
        cambi = f'<h2>Cambi sala durante il servizio</h2><ul class="cambi">{voci}</ul>'
        sotto = "La disposizione cambia durante la serata: la mappa mostra i tavoli presenti all'ora scelta."
    else:
        sotto = "Disposizione dei tavoli fissa per tutta la serata."
    registro = f'<h2>Registro delle accettazioni (in ordine di prenotazione)</h2>{_registro(sol)}' if sol.get("registro") else ""
    return f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titolo)}</title><style>{CSS}</style></head>
<body>
<h1>{escape(titolo)}</h1>
<p class="sotto">{sotto} Sala {sala["larghezza_cm"]}×{sala["altezza_cm"]} cm, servizio {sala["servizio"]["inizio"]}–{sala["servizio"]["fine"]}.</p>
{_sintesi(sala, sol, tot_cop, tot_pren)}
<h2>Mappa della sala</h2>
{cursore}
{_svg_sala(sala, sol, dinamica)}
<p class="legenda"><span><i class="q" style="background:{COL_OSTACOLO}"></i>ostacolo</span>
<span><i class="q" style="background:#e6edf1"></i>corsia da tenere libera</span>
<span><i class="q" style="background:{COL_TAVOLO}"></i>tavolo (tratteggio interno = moduli accostati)</span>
<span><i class="q" style="background:{COL_SEDIA}"></i>sedia</span>
<span><i class="q" style="background:#fff;border-style:dashed"></i>ingombro tavolo + sedie ({sala["margine_sedie_cm"]} cm)</span>
<span style="color:{COL_SPOSTATA}">arancione = orario spostato</span></p>
{cambi}
<h2>Timeline per tavolo</h2>
<div class="scorri">{_svg_timeline(sala, sol)}</div>
<p class="legenda"><span>barra = permanenza al tavolo</span><span><i class="q" style="background:#efe6d6"></i>tavolo presente</span>
<span><i class="q" style="background:#e0e0e0"></i>riapparecchiatura ({sala.get("riapparecchiatura_min", 0)} min)</span>
<span style="color:{COL_SPOSTATA}">bordo arancione = spostata, trattino = orario richiesto</span><span>★ = nota</span></p>
{registro}
<h2>Elenco prenotazioni</h2>
{_elenco(sol)}
{"<script>" + JS + "</script>" if dinamica else ""}
</body></html>
"""


def scrivi_html(sala: dict, prenotazioni: dict, sol: dict, percorso: str | Path) -> None:
    Path(percorso).parent.mkdir(parents=True, exist_ok=True)
    Path(percorso).write_text(genera_html(sala, prenotazioni, sol), encoding="utf-8")
