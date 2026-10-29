"""Mappa della serata con la disposizione LIBERA dei tavoli mobili (stesso stile di `mappa_piantina.py`).

Una vista per turno: il resto della sala come nella piantina (muri, ostacoli, porte, passaggi, tavoli fissi), le file di
quadrati dove le ha messe il motore, con le sedie disegnate (una per lato da un quadrato) e chi siede dove. Sopra, il
riepilogo: prenotazioni e coperti, tavoli usati, confronto con il modo a tavoli fermi (se c'è), tempi, esito della
verifica, e l'elenco delle misure prese dalla piantina o da un default. File unico, senza risorse esterne.
"""
from __future__ import annotations

from html import escape

from .mappa import _registro
from .mappa_piantina import CSS, GRIGIO, LATO, PIENO, SALA, STILE, _breve, _muro, _num, _ostacolo, _rett, _ruota_attr, \
    _segno, _testo
from .modello_piantina import posti_vuoti

SEDIA = ("#f3f1ec", "#8d8a80")          # sedia libera
SEDIA_PIENA = ("#f4c25b", "#9a6b12")    # sedia di un pezzo occupato nel turno


def _zone_sedie(t: dict, cpu: float, sedie_cm: float) -> list[tuple[str, int, float, float, float, float]]:
    """Zone delle sedie di una fila, in unità del disegno: (lato, quadrato, x, y, w, h)."""
    x, y, k = t["x_cm"] / cpu, t["y_cm"] / cpu, int(t["moduli"])
    lato, sd = t["larghezza_cm"] / cpu / (k if t["orientamento"] == "orizzontale" else 1), sedie_cm / cpu
    vert = t["orientamento"] == "verticale"
    w, h = t["larghezza_cm"] / cpu, t["altezza_cm"] / cpu
    s, out = t["sedie"], []
    for q in range(k):
        if s["lato_a"][q]:
            out.append(("a", q, x - sd, y + q * lato, sd, lato) if vert else ("a", q, x + q * lato, y - sd, lato, sd))
        if s["lato_b"][q]:
            out.append(("b", q, x + w, y + q * lato, sd, lato) if vert else ("b", q, x + q * lato, y + h, lato, sd))
    if s["testa"]:
        out.append(("testa", 0, x, y - sd, w, sd) if vert else ("testa", 0, x - sd, y, sd, h))
    if s["coda"]:
        out.append(("coda", k - 1, x, y + h, w, sd) if vert else ("coda", k - 1, x + w, y, sd, h))
    return out


def _sedia(zx: float, zy: float, zw: float, zh: float, verso_tavolo: tuple[float, float], piena: bool) -> str:
    """Una sedia (40 x 35 cm circa) dentro la sua zona, appoggiata al tavolo."""
    fill, stroke = SEDIA_PIENA if piena else SEDIA
    lungo, corto = 15.0, 13.0
    if zw >= zh:          # zona orizzontale (sopra o sotto il tavolo)
        w, h = lungo, corto
        x = zx + (zw - w) / 2
        y = zy + (zh - h - 1.5 if verso_tavolo[1] > 0 else 1.5)
    else:
        w, h = corto, lungo
        y = zy + (zh - h) / 2
        x = zx + (zw - w - 1.5 if verso_tavolo[0] > 0 else 1.5)
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="3" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="0.8"/>')


def _svg_turno(dati: dict, sol: dict, turno: str) -> str:
    geo = sol.get("geometria") or {}
    cpu = float(geo.get("cm_per_unita") or 2.5)
    sedie_cm = float(geo.get("sedie_cm") or 50)
    per_tav: dict[str, list] = {}
    for r in sol["assegnazioni"]:
        if r["turno"] == turno:
            per_tav.setdefault(r["tavolo"], []).append(r)
    sala = _rett(dati.get("sala")) or tuple(SALA.values())
    sx, sy, sw, sh = sala
    out = [f'<svg class="sala" viewBox="{sx - 10:g} {sy - 30:g} {sw + 20:g} {sh + 40:g}" xmlns="http://www.w3.org/2000/svg" '
           f'role="img" aria-label="Sala nel {escape(turno)} turno">',
           f'<rect x="{sx:g}" y="{sy:g}" width="{sw:g}" height="{sh:g}" rx="6" fill="none" stroke="#b4b2a9" stroke-dasharray="6 4"/>']
    e = dati.get("ingresso")
    if _rett(e):
        out.append(f'<rect x="{e["x"]}" y="{e["y"]}" width="{e["w"]}" height="{e["h"]}" rx="2" fill="#ef9f27"'
                   f'{_ruota_attr(e, _num(e["x"]) + _num(e["w"]) / 2, _num(e["y"]) + _num(e["h"]) / 2)}/>'
                   + _testo(_num(e["x"]) + _num(e["w"]) / 2, _num(e["y"]) - 4, "ingresso", "et-piccola"))
    for p in dati.get("passaggi", []):
        r = _rett(p)
        if r:
            out.append(f'<rect x="{r[0]:g}" y="{r[1]:g}" width="{r[2]:g}" height="{r[3]:g}" fill="#eef5fc" stroke="#85b7eb" '
                       f'stroke-width="0.8"{_ruota_attr(p, r[0] + r[2] / 2, r[1] + r[3] / 2)}/>')
    ostacoli = [o for o in dati.get("ostacoli", []) if isinstance(o, dict)]
    for n, o in enumerate(ostacoli):
        out.append(_ostacolo(o, ostacoli[:n]))
    for p in dati.get("porte", []):
        out.append(_segno(p, "#fff", "#ba7517"))
    for f in dati.get("finestre", []):
        out.append(_segno(f, "#e3f2fc", "#5b9bd5"))
    for m in dati.get("muri", []):
        out.append(_muro(m, cpu))
    # tavoli fissi, dove sono nella piantina
    fissi = {str(t["id"]) for t in sol["tavoli"] if t.get("fisso")}
    for t in dati["tavoli"]:
        tid = str(t["id"])
        if tid not in fissi:
            continue
        fill, stroke = STILE.get(t["tipo"], GRIGIO)
        chi = per_tav.get(tid, [])
        rot = f' transform="rotate({t["rot"]} {t["x"]} {t["y"]})"' if t.get("rot") else ""
        if t["tipo"] == "tondo":
            out.append(f'<circle cx="{t["x"]}" cy="{t["y"]}" r="{t.get("r", 16)}" fill="{PIENO if chi else fill}" '
                       f'stroke="{stroke}" stroke-width="1.2"/>')
            out.append(_testo(t["x"], t["y"] - 2, tid, "et-id"))
            if chi:
                out.append(_testo(t["x"], t["y"] + 8, f'{_breve(chi[0]["nome"])} {chi[0]["coperti"]}', "et-chi"))
            continue
        w, h = t.get("w") or LATO, t.get("h") or LATO
        out.append(f'<rect x="{t["x"] - w / 2}" y="{t["y"] - h / 2}" width="{w}" height="{h}" rx="2" '
                   f'fill="{PIENO if chi else fill}" stroke="{stroke}" stroke-width="1.2"{rot}/>')
        if t["tipo"] == "lungo":
            out.append(_testo(t["x"], t["y"] - h / 2 + 9, f'{tid} · lungo', "et-id"))
            gruppi = sorted(chi, key=lambda r: r.get("gruppo") or 0)
            if len(gruppi) == 2:
                out.append(f'<line x1="{t["x"]}" y1="{t["y"] - h / 2 + 11}" x2="{t["x"]}" y2="{t["y"] + h / 2}" '
                           f'stroke="#378add" stroke-dasharray="3 2"/>')
                for r, dx in zip(gruppi, (-w / 4, w / 4)):
                    out.append(_testo(t["x"] + dx, t["y"] + 9, f'{_breve(r["nome"])} {r["coperti"]}', "et-chi"))
            elif gruppi:
                out.append(_testo(t["x"], t["y"] + 9, f'{gruppi[0]["nome"]} {gruppi[0]["coperti"]}', "et-chi"))
        else:
            out.append(_testo(t["x"], t["y"] - 2, tid, "et-id"))
            if chi:
                out.append(_testo(t["x"], t["y"] + 8, f'{_breve(chi[0]["nome"], 7)} {chi[0]["coperti"]}', "et-chi"))
    # postazioni progettate (tratteggio): dove la serata può mettere una fila; le file messe ci stanno sopra
    for p in sol.get("postazioni") or []:
        out.append(f'<rect x="{p["x_cm"] / cpu:.1f}" y="{p["y_cm"] / cpu:.1f}" width="{p["larghezza_cm"] / cpu:.1f}" '
                   f'height="{p["altezza_cm"] / cpu:.1f}" rx="2" fill="none" stroke="#b4b2a9" stroke-width="0.9" '
                   f'stroke-dasharray="3 3"/>')
    # file di quadrati, con le sedie
    fill, stroke = STILE["blocco"]
    for t in sol["tavoli"]:
        if t.get("tipo") != "fila":
            continue
        tid, k = t["id"], int(t["moduli"])
        vert = t["orientamento"] == "verticale"
        x0, y0 = t["x_cm"] / cpu, t["y_cm"] / cpu
        lato = (t["altezza_cm"] if vert else t["larghezza_cm"]) / cpu / k
        chi = per_tav.get(tid, [])
        pezzi = t.get("partizioni", {}).get(turno) or [[0, k - 1]]
        occupato = {}
        for a, b in pezzi:
            seduto = next((r for r in chi if r.get("quadrati") == [a, b]), None)
            for q in range(a, b + 1):
                occupato[q] = seduto
        for lato_s, q, zx, zy, zw, zh in _zone_sedie(t, cpu, sedie_cm):
            out.append(f'<rect x="{zx:.1f}" y="{zy:.1f}" width="{zw:.1f}" height="{zh:.1f}" fill="#f6f4ee" stroke="none" opacity="0.8"/>')
            if not vert and lato_s in ("a", "b"):          # da che parte sta il tavolo, vista dalla zona
                verso = (0, 1 if lato_s == "a" else -1)
            elif vert and lato_s in ("a", "b"):
                verso = (1 if lato_s == "a" else -1, 0)
            elif not vert:
                verso = (1 if lato_s == "testa" else -1, 0)
            else:
                verso = (0, 1 if lato_s == "testa" else -1)
            out.append(_sedia(zx, zy, zw, zh, verso, occupato.get(q) is not None))
        for q in range(k):
            qx, qy = (x0, y0 + q * lato) if vert else (x0 + q * lato, y0)
            out.append(f'<rect x="{qx + 0.6:.1f}" y="{qy + 0.6:.1f}" width="{lato - 1.2:.1f}" height="{lato - 1.2:.1f}" rx="2" '
                       f'fill="{PIENO if occupato.get(q) else fill}" stroke="{stroke}" stroke-width="1"/>')
        for a, b in pezzi:
            seduto = occupato.get(a)
            px, py = (x0, y0 + a * lato) if vert else (x0 + a * lato, y0)
            pw, ph = (lato, (b - a + 1) * lato) if vert else ((b - a + 1) * lato, lato)
            if len(pezzi) > 1:
                out.append(f'<rect x="{px - 1.5:.1f}" y="{py - 1.5:.1f}" width="{pw + 3:.1f}" height="{ph + 3:.1f}" rx="3" '
                           f'fill="none" stroke="#c0560b" stroke-width="1.4" stroke-dasharray="3 2"/>')
            if seduto:
                out.append(_testo(px + pw / 2, py + ph / 2 + 3, f'{_breve(seduto["nome"], 7)} {seduto["coperti"]}', "et-chi"))
        out.append(_testo(x0 + 7, y0 + 8, tid, "et-id-blocco"))
    out.append("</svg>")
    return "\n".join(out)


def _elenco_tavoli(sol: dict, turni: list[dict]) -> str:
    per = {}
    for r in sol["assegnazioni"]:
        per.setdefault((r["tavolo"], r["turno"]), []).append(r)
    righe = []
    for t in sol["tavoli"]:
        tid = str(t["id"])
        celle = []
        for tu in turni:
            lst = sorted(per.get((tid, tu["nome"]), []), key=lambda r: ((r.get("quadrati") or [0])[0], r.get("gruppo") or 0))
            celle.append("<br>".join(
                f'<b>{escape(r["nome"])}</b> {r["coperti"]}'
                + (f' <span class="tenue">(quadrat{"o" if r["quadrati"][0] == r["quadrati"][1] else "i"} '
                   f'{r["quadrati"][0] + 1}{"" if r["quadrati"][0] == r["quadrati"][1] else "-" + str(r["quadrati"][1] + 1)}, '
                   f'{r["posti_tavolo"]} sedie)</span>' if r.get("quadrati") and r["quadrati"] != [0, int(t.get("moduli", 1)) - 1] else "")
                + (f' <span class="tenue">(gruppo {r["gruppo"]})</span>' if r.get("gruppo") == 2 or (r.get("gruppo") and len(lst) == 2) else "")
                + (f' <span class="nota">{escape(r["note"])}</span>' if r.get("note") else "")
                for r in lst) or '<span class="tenue">libero</span>')
        if t.get("tipo") == "fila":
            tipo = (f'fila di {t["moduli"]} {"quadrato" if t["moduli"] == 1 else "quadrati"} {t["orientamento"]} · '
                    f'{t["posti"]} sedie')
        else:
            tipo = f'{escape(t["tipo"])} fisso · {t["posti"]}'
        righe.append(f'<tr><td class="num">{escape(tid)}</td><td>{tipo}</td>' + "".join(f"<td>{c}</td>" for c in celle) + "</tr>")
    testa = "".join(f'<th>{escape(tu["nome"])} turno ({tu["inizio"]})</th>' for tu in turni)
    return (f'<div class="scorri"><table class="elenco"><tr><th>tavolo</th><th>tipo · posti</th>{testa}</tr>'
            + "".join(righe) + "</table></div>")


def piantina_variante(dati: dict, sol: dict) -> dict:
    """La piantina della disposizione scelta: i tavoli fissi del disegno più i pezzi mobili della soluzione (quelli
    rimasti come nel disegno sono quelli del disegno)."""
    import copy
    d = copy.deepcopy(dati)
    pezzi = (sol.get("variante") or {}).get("pezzi")
    if pezzi is None:
        return d
    mobili = {str(t["id"]): t for t in d["tavoli"] if t.get("tipo") in ("quadrato", "blocco") and not t.get("fisso")}
    out = [t for t in d["tavoli"] if str(t["id"]) not in mobili]
    for p in pezzi:
        if p.get("stato") == "disegno" and str(p["id"]) in mobili:
            out.append(mobili[str(p["id"])])
            continue
        t = {"id": p["id"], "tipo": p["tipo"], "x": p["x"], "y": p["y"], "rot": p.get("rot") or 0, "posti": p["posti"],
             "fisso": False, "separabile": bool(p.get("separabile"))}
        if p["tipo"] == "blocco":
            t.update(moduli=p["moduli"], verso=p.get("verso"))
        if "spazio_u" in p:
            t["spazio_u"] = p["spazio_u"]
        out.append(t)
    d["tavoli"] = out
    return d


def _sedie_ruotate(p: dict) -> list[str]:
    """Le sedie di un pezzo allungato (anche di traverso): una per lato lungo di ogni quadrato, più testa e coda, al
    massimo i posti del pezzo; in unità del disegno."""
    import math
    k, rot = int(p.get("moduli") or 1), float(p.get("rot") or 0)
    a = math.radians(rot)
    ax = (math.cos(a), math.sin(a)) if p.get("verso") == "orizzontale" else (-math.sin(a), math.cos(a))
    px, py = -ax[1], ax[0]
    L = k * LATO + (k - 1) * 2
    punti = []
    for q in range(k):
        off = -L / 2 + LATO / 2 + q * (LATO + 2)
        for s in (-1, 1):
            punti.append((off, s * (LATO / 2 + 8)))
    for s in (-1, 1):
        punti.append((s * (L / 2 + 8), 0.0))
    out = []
    for sa, sl in punti[:int(p.get("posti") or 0)]:
        x, y = p["x"] + ax[0] * sa + px * sl, p["y"] + ax[1] * sa + py * sl
        out.append(f'<rect x="{x - 7:.1f}" y="{y - 6:.1f}" width="14" height="12" rx="3" fill="{SEDIA[0]}" '
                   f'stroke="{SEDIA[1]}" stroke-width="0.8" transform="rotate({rot:g} {x:.1f} {y:.1f})"/>')
    return out


def _verso_tavolo(lato: str, vert: bool) -> tuple[float, float]:
    if not vert:
        return {"a": (0, 1), "b": (0, -1), "testa": (1, 0), "coda": (-1, 0)}[lato]
    return {"a": (1, 0), "b": (-1, 0), "testa": (0, 1), "coda": (0, -1)}[lato]


def genera_html_variante(sala: dict, prenotazioni: dict, sol: dict, esito_verifica: str | None = None) -> str:
    """Mappa della disposizione libera dal disegno: la mappa della sala vera con i pezzi della disposizione nella loro
    posizione, le sedie dei tavoli nuovi, la sezione «Da preparare in sala» (una riga per mossa) e chi cambia tavolo."""
    from .mappa_piantina import genera_html as mappa_disegno
    dati = piantina_variante(sala["piantina"], sol)
    html = mappa_disegno(dict(sala, piantina=dati), prenotazioni, sol)
    var = sol.get("variante") or {}
    geo = sol.get("geometria") or {}
    cpu, sd = float(geo.get("cm_per_unita") or 2.5), float(geo.get("sedie_cm") or 50)
    sedie = []
    for p in var.get("pezzi") or []:
        if p.get("stato") == "allungato":           # sedie a 25 cm dal bordo, ruotate con il pezzo
            sedie += _sedie_ruotate(p)
            continue
        if p.get("stato") != "nuovo":
            continue
        vert = p["orientamento"] == "verticale"
        for lato, _q, zx, zy, zw, zh in _zone_sedie(p, cpu, sd):
            sedie.append(_sedia(zx, zy, zw, zh, _verso_tavolo(lato, vert), False))
    if sedie:
        html = html.replace("</svg>", f'<g class="sedie-nuove">{"".join(sedie)}</g></svg>')
    mosse = var.get("mosse") or []
    righe = "".join(f'<li>{escape(m["mossa"])}</li>' for m in mosse) or "<li>niente: la sala resta come nel disegno</li>"
    pezzi = {p["id"]: p for p in var.get("pezzi") or []}
    stati = {"allungato": "allungato", "accorciato": "diviso", "nuovo": "nuovo"}
    for pid, chi in (var.get("chi_siede") or {}).items():
        p = pezzi.get(pid, {})
        righe += (f'<li><b>il {escape(pid)} {stati.get(p.get("stato"), "")} a {p.get("posti", "?")} posti</b>: '
                  f'{escape("; ".join(chi)) if chi else "nessuno"}</li>')
    per = {}
    for m in mosse:
        if m.get("per"):
            per[m["per"]] = m.get("per_tavolo")
    for nome, tav in per.items():
        righe += f'<li>così entra <b>{escape(nome)}</b>, che siede al {escape(str(tav or "?"))}</li>'

    cambi = [r for r in sol.get("registro") or [] if r.get("tavolo_cambiato")]
    righe_c = "".join(f'<li><b>{escape(r["nome"])}</b> ×{r["coperti"]}: confermato al {escape(str(r["tavolo_alla_conferma"]))}, '
                      f'a cena al {escape(str(r["tavolo_finale"]))}</li>' for r in cambi) or "<li>nessuno</li>"
    riserva = var.get("riserva") or {}
    nota = ""
    if riserva.get("scartate_mosse"):
        nota = (f'<p class="tenue">Le mosse provate davano {riserva["prenotazioni"]} prenotazioni e {riserva["coperti"]} '
                f'coperti, meno del solo disegno: si tiene il disegno.</p>')
    esito = f'<p class="tenue">Verifica indipendente: {escape(esito_verifica)}</p>' if esito_verifica else ""
    prep = (f'<div class="box"><h3>Da preparare in sala (prima delle 20:00)</h3><ul>{righe}</ul>{nota}{esito}</div>'
            f'<div class="box"><h3>Chi ha cambiato tavolo dopo la conferma ({len(cambi)})</h3><ul>{righe_c}</ul></div>')
    from .libera_varianti import articoli
    prep = articoli(prep)
    html = html.replace('<div class="box"><h3>Non sistemate</h3>', prep + '<div class="box"><h3>Non sistemate</h3>', 1)
    html = html.replace("i tavoli non si spostano.", "disposizione libera dal disegno: i pezzi cambiati sono in "
                        "«Da preparare in sala», con le loro sedie.", 1)
    return html


def riepilogo(sol: dict, prenotazioni: dict) -> dict:
    """Numeri del riepilogo (anche per il confronto con il modo a tavoli fermi)."""
    ass = sol["assegnazioni"]
    turni = sol.get("modalita", {}).get("turni") or []
    out = {"prenotazioni": f'{len(ass)}/{len(prenotazioni["prenotazioni"])}',
           "coperti": f'{sum(r["coperti"] for r in ass)}/{sum(p["coperti"] for p in prenotazioni["prenotazioni"])}',
           "accettate_su_proposta": (sol.get("accettazione") or {}).get("accettate_su_proposta"),
           "non_sistemate": [f'{r["nome"]} ×{r["coperti"]}' for r in sol["non_sistemate"]], "turni": {}}
    for tu in turni:
        nel = [r for r in ass if r["turno"] == tu["nome"]]
        out["turni"][tu["nome"]] = {"prenotazioni": len(nel), "coperti": sum(r["coperti"] for r in nel),
                                    "tavoli_usati": len({r["tavolo"] for r in nel}),
                                    "posti_occupati": len({(r["tavolo"], tuple(r.get("quadrati") or ()), r.get("gruppo")) for r in nel})}
    file = [t for t in sol["tavoli"] if t.get("tipo") == "fila"]
    if file:
        out["file"] = len(file)
        out["quadrati_usati"] = sum(int(t["moduli"]) for t in file)
        out["sedie_alle_file"] = sum(int(t["posti"]) for t in file)
    out["tempo_s"] = sol.get("tempo_esecuzione_s")
    return out


def genera_html(sala: dict, prenotazioni: dict, sol: dict, esito_verifica: str | None = None) -> str:
    dati = sala["piantina"]
    turni = sol.get("modalita", {}).get("turni") or sala.get("turni") or []
    ass, nons = sol["assegnazioni"], sol["non_sistemate"]
    geo = sol.get("geometria") or {}
    comp = sol.get("obiettivo_componenti", {})
    rie = riepilogo(sol, prenotazioni)
    titolo = f'{sol.get("serata") or prenotazioni.get("serata", "Serata")} — {dati.get("nome", "")} · tavoli mobili liberi'
    kpi = [(rie["coperti"], "coperti sistemati"), (rie["prenotazioni"], "prenotazioni sistemate"
                                                    + (f' (di cui {rie["accettate_su_proposta"]} nell\'altro turno)'
                                                       if rie.get("accettate_su_proposta") else ""))]
    lunghi = {str(t["id"]): int(t["posti"]) for t in dati["tavoli"] if t["tipo"] == "lungo"}
    for tu in turni:
        x = rie["turni"][tu["nome"]]
        kpi.append((f'{x["coperti"]}', f'coperti nel {tu["nome"]} turno ({tu["inizio"]}) · {x["prenotazioni"]} prenotazioni · '
                    f'{x["tavoli_usati"]} tavoli usati ({x["posti_occupati"]} con i pezzi delle file)'))
    kpi.append((f'{rie.get("file", 0)}', f'file di quadrati · {rie.get("quadrati_usati", 0)}/{geo.get("quadrati_mobili", "?")} '
                f'quadrati usati · {rie.get("sedie_alle_file", 0)} sedie'))
    kpi.append((f'{comp.get("divisioni_blocchi", {}).get("numero", 0)}', "divisioni delle file nei turni · "
                f'{comp.get("riallestimenti", {}).get("numero", 0)} file con pezzi diversi tra i turni'))
    kpi.append((f'{sol.get("tempo_esecuzione_s", "—")} s', "tempo di calcolo"))
    if esito_verifica:
        kpi.append((escape(esito_verifica.split("(")[0].replace("ESITO:", "").strip()),
                    "verifica indipendente · " + escape(esito_verifica.split("(", 1)[1].rstrip(")") if "(" in esito_verifica else "")))
    conf = sol.get("confronto_tavoli_fermi")
    box_conf = ""
    if conf:
        righe = [("prenotazioni sistemate", rie["prenotazioni"], conf["prenotazioni"]),
                 ("coperti sistemati", rie["coperti"], conf["coperti"]),
                 ("nell'altro turno (su proposta)", rie.get("accettate_su_proposta") or 0, conf.get("accettate_su_proposta") or 0),
                 ("non sistemate", ", ".join(rie["non_sistemate"]) or "nessuna", ", ".join(conf["non_sistemate"]) or "nessuna")]
        for tu in turni:
            a, b = rie["turni"][tu["nome"]], conf["turni"].get(tu["nome"], {})
            righe.append((f'{tu["nome"]} turno: prenotazioni · coperti · tavoli usati',
                          f'{a["prenotazioni"]} · {a["coperti"]} · {a["tavoli_usati"]}',
                          f'{b.get("prenotazioni", "—")} · {b.get("coperti", "—")} · {b.get("tavoli_usati", "—")}'))
        righe.append(("tempo di calcolo", f'{rie.get("tempo_s", "—")} s', f'{conf.get("tempo_s", "—")} s'))
        box_conf = ('<div class="box"><h3>Confronto con i tavoli fermi (stesse prenotazioni)</h3><div class="scorri">'
                    '<table class="elenco"><tr><th></th><th>tavoli mobili liberi</th><th>tavoli fermi</th></tr>'
                    + "".join(f'<tr><td>{escape(str(a))}</td><td>{escape(str(b))}</td><td>{escape(str(c))}</td></tr>'
                              for a, b, c in righe) + "</table></div></div>")
    misure = "".join(f'<tr><td>{escape(m["cosa"])}</td><td>{escape(m["valore"])}</td><td>{escape(m["fonte"])}</td></tr>'
                     for m in sol.get("misure_usate") or [])
    box_misure = ('<div class="box"><h3>Misure usate (dalla piantina o da un default)</h3><div class="scorri"><table class="elenco">'
                  f'<tr><th>che cosa</th><th>valore</th><th>da dove viene</th></tr>{misure}</table></div></div>') if misure else ""
    viste = "".join(f'<h2 id="t{i}">{escape(tu["nome"].capitalize())} turno · {tu["inizio"]}–{tu["fine"]}</h2>'
                    f'<div class="vista">{_svg_turno(dati, sol, tu["nome"])}</div>' for i, tu in enumerate(turni))
    salti = " · ".join(f'<a href="#t{i}">{escape(tu["nome"])} turno</a>' for i, tu in enumerate(turni)) + \
        ' · <a href="#elenco">elenco per tavolo</a> · <a href="#misure">misure</a>'
    righe_ns = "".join(f'<li><b>{escape(r["nome"])}</b> ×{r["coperti"]} alle {r["orario_richiesto"]}: {escape(r["motivo"])}</li>'
                       for r in nons) or "<li>nessuna</li>"
    registro = (f'<h2>Registro delle accettazioni (in ordine di prenotazione)</h2>{_registro(sol)}'
                if sol.get("registro") else "")
    regole = (f'Le file di quadrati ({geo.get("lato_quadrato_cm", 80):g} cm) si mettono a 0° o a 90°, fino a {geo.get("k_max", 4)} '
              f'quadrati in fila; una sedia per ogni lato da un quadrato con {geo.get("sedie_cm", 50):g} cm liberi davanti; '
              f'ogni tavolo ha almeno un lato su un corridoio di {geo.get("corridoio_cm", 60):g} cm e si raggiunge dall\'ingresso; '
              'le strade dall\'ingresso alla cucina e ai bagni restano libere; i tavoli fissi restano dove sono. '
              'Una sola disposizione per la serata: tra i turni cambia solo chi siede dove e come si dividono le file.')
    return f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titolo)}</title><style>{CSS}{CSS_LIBERA}</style></head>
<body><div class="wrap">
<h1>{escape(titolo)}</h1>
<p class="sotto">Sala vera dalla piantina (aggiornata il {escape(str(dati.get("aggiornata", "")))}). {escape(regole)}
Giallo = occupato nel turno; rettangolini = sedie; contorno arancione tratteggiato = pezzo di una fila divisa; riquadro grigio tratteggiato = postazione progettata dal motore (stasera senza quadrati o con meno quadrati). {salti}</p>
<div class="sintesi">{"".join(f'<div class="kpi"><div class="v">{v}</div><div class="l">{escape(l)}</div></div>' for v, l in kpi)}</div>
{box_conf}
<div class="box"><h3>Non sistemate</h3><ul>{righe_ns}</ul></div>
{viste}
<h2 id="elenco">Elenco per tavolo</h2>
{_elenco_tavoli(sol, turni)}
<h2 id="misure">Misure</h2>
{box_misure}
{registro}
</div></body></html>
"""


CSS_LIBERA = """
.box table.elenco td{font-size:12.5px}
"""
