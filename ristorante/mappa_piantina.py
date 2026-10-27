"""Mappa della serata sulla sala vera: le posizioni vengono dalla piantina (unità del disegno, non in scala).

Una vista per turno (su telefono si scorre: prima il primo turno, poi il secondo), con chi siede a ogni tavolo; i blocchi
divisi si vedono come quadrati separati con chi ci siede, il lungo con uno o due gruppi. Sotto, l'elenco ordinato per
tavolo con i due turni affiancati, le non sistemate e il registro delle accettazioni. File unico, senza risorse esterne.
"""
from __future__ import annotations

import math
from html import escape

from .mappa import _registro
from .modello_piantina import posti_vuoti

LATO, GAP = 32, 2
STILE = {
    "quadrato": ("#eceae4", "#888780"), "blocco": ("#d6efe6", "#1d9e75"), "lungo": ("#dbe9f8", "#378add"),
    "rettangolare": ("#fae1d8", "#d85a30"), "panca": ("#f8e7c7", "#ba7517"), "tondo": ("#e7e4fb", "#7f77dd"),
}
PIENO = "#ffd98a"              # tavolo o pezzo occupato nel turno


def _ruota(px: float, py: float, cx: float, cy: float, gradi: float) -> tuple[float, float]:
    a = math.radians(gradi or 0)
    dx, dy = px - cx, py - cy
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)


def _breve(nome: str, n: int = 9) -> str:
    return nome if len(nome) <= n else nome[:n - 1] + "…"


def _testo(x: float, y: float, testo: str, cls: str) -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="middle">{escape(testo)}</text>'


def _quadrati_blocco(t: dict) -> list[tuple[float, float]]:
    """Angoli in alto a sinistra dei quadrati del blocco, prima della rotazione (come nella piantina)."""
    k = int(t["moduli"])
    L = k * LATO + (k - 1) * GAP
    out = []
    for i in range(k):
        off = -L / 2 + i * (LATO + GAP)
        if t.get("verso") == "orizzontale":
            out.append((t["x"] + off, t["y"] - LATO / 2))
        else:
            out.append((t["x"] - LATO / 2, t["y"] + off))
    return out


def _svg_turno(dati: dict, sol: dict, turno: str) -> str:
    per_tav: dict[str, list] = {}
    for r in sol["assegnazioni"]:
        if r["turno"] == turno:
            per_tav.setdefault(r["tavolo"], []).append(r)
    part = {t["id"]: t.get("partizioni", {}).get(turno) for t in sol["tavoli"]}
    out = ['<svg class="sala" viewBox="30 10 420 665" xmlns="http://www.w3.org/2000/svg" role="img" '
           f'aria-label="Sala nel {escape(turno)} turno">',
           '<rect x="40" y="40" width="400" height="625" rx="6" fill="none" stroke="#b4b2a9" stroke-dasharray="6 4"/>']
    e = dati.get("ingresso")
    if e:
        out.append(f'<rect x="{e["x"]}" y="{e["y"]}" width="{e["w"]}" height="{e["h"]}" rx="2" fill="#ef9f27"/>'
                   + _testo(e["x"] + e["w"] / 2, e["y"] - 4, "ingresso", "et-piccola"))
    for p in dati.get("passaggi", []):
        out.append(f'<rect x="{p["x"]}" y="{p["y"]}" width="{p["w"]}" height="{p["h"]}" fill="#eef5fc" stroke="#85b7eb" '
                   f'stroke-width="0.8"/>')
    for o in dati.get("ostacoli", []):
        out.append(f'<polygon points="{o["punti"]}" fill="#d3d1c7" stroke="#5f5e5a" stroke-width="1"/>')
        if o.get("etichetta"):
            out.append(_testo(o["etichetta"]["x"], o["etichetta"]["y"], o["nome"], "et-piccola"))
    for d in dati.get("muri", []):
        out.append(f'<path d="{d}" fill="none" stroke="#2c2c2a" stroke-width="3"/>')
    for t in dati["tavoli"]:
        tid = str(t["id"])
        fill, stroke = STILE.get(t["tipo"], ("#eee", "#888"))
        chi = per_tav.get(tid, [])
        rot = f' transform="rotate({t["rot"]} {t["x"]} {t["y"]})"' if t.get("rot") else ""
        if t["tipo"] == "tondo":
            out.append(f'<circle cx="{t["x"]}" cy="{t["y"]}" r="{t["r"]}" fill="{PIENO if chi else fill}" '
                       f'stroke="{stroke}" stroke-width="1.2"/>')
            out.append(_testo(t["x"], t["y"] - 2, tid, "et-id"))
            if chi:
                out.append(_testo(t["x"], t["y"] + 8, f'{_breve(chi[0]["nome"])} {chi[0]["coperti"]}', "et-chi"))
        elif t["tipo"] == "blocco":
            quadrati = _quadrati_blocco(t)
            pezzi = part.get(tid) or [[0, int(t["moduli"]) - 1]]
            for a, b in pezzi:
                seduto = next((r for r in chi if r.get("quadrati") == [a, b]), None)
                for i in range(a, b + 1):
                    x, y = quadrati[i]
                    out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{LATO}" height="{LATO}" rx="2" '
                               f'fill="{PIENO if seduto else fill}" stroke="{stroke}" stroke-width="1"{rot}/>')
                (x0, y0), (x1, y1) = quadrati[a], quadrati[b]
                cx, cy = _ruota((x0 + x1) / 2 + LATO / 2, (y0 + y1) / 2 + LATO / 2, t["x"], t["y"], t.get("rot"))
                if len(pezzi) > 1:      # pezzo separato: contorno marcato
                    w = (x1 - x0) + LATO
                    h = (y1 - y0) + LATO
                    out.append(f'<rect x="{x0 - 1.5:.1f}" y="{y0 - 1.5:.1f}" width="{w + 3:.1f}" height="{h + 3:.1f}" '
                               f'rx="3" fill="none" stroke="#c0560b" stroke-width="1.4" stroke-dasharray="3 2"{rot}/>')
                if seduto:
                    out.append(_testo(cx, cy + 3, f'{_breve(seduto["nome"], 7)} {seduto["coperti"]}', "et-chi"))
            cx, cy = _ruota(*(_quadrati_blocco(t)[0]), t["x"], t["y"], t.get("rot"))
            out.append(_testo(cx + 3, cy + 2, tid, "et-id-blocco"))
        else:
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
    out.append("</svg>")
    return "\n".join(out)


def _posto(r: dict, t: dict) -> str:
    if r.get("quadrati") and t.get("moduli") and r["quadrati"] != [0, int(t["moduli"]) - 1]:
        a, b = r["quadrati"]
        return f"quadrat{'o' if a == b else 'i'} {a + 1}{'' if a == b else '-' + str(b + 1)}"
    if r.get("gruppo") == 2 or (r.get("gruppo") == 1 and t.get("due_gruppi")):
        return f"gruppo {r['gruppo']}"
    return ""


def _elenco_tavoli(dati: dict, sol: dict, turni: list[dict]) -> str:
    per = {}
    for r in sol["assegnazioni"]:
        per.setdefault((r["tavolo"], r["turno"]), []).append(r)
    righe = []
    for t in dati["tavoli"]:
        tid = str(t["id"])
        celle = []
        for tu in turni:
            lst = sorted(per.get((tid, tu["nome"]), []), key=lambda r: ((r.get("quadrati") or [0])[0], r.get("gruppo") or 0))
            t2 = dict(t, due_gruppi=len(lst) == 2)
            celle.append("<br>".join(f'<b>{escape(r["nome"])}</b> {r["coperti"]}'
                                     + (f' <span class="tenue">({_posto(r, t2)}, {r["posti_tavolo"]} posti)</span>'
                                        if _posto(r, t2) else "")
                                     + (f' <span class="nota">{escape(r["note"])}</span>' if r.get("note") else "")
                                     for r in lst) or '<span class="tenue">libero</span>')
        righe.append(f'<tr><td class="num">{escape(tid)}</td><td>{escape(t["tipo"])} · {t["posti"]}</td>'
                     + "".join(f"<td>{c}</td>" for c in celle) + "</tr>")
    testa = "".join(f'<th>{escape(tu["nome"])} turno ({tu["inizio"]})</th>' for tu in turni)
    return (f'<div class="scorri"><table class="elenco"><tr><th>tavolo</th><th>tipo · posti</th>{testa}</tr>'
            + "".join(righe) + "</table></div>")


def genera_html(sala: dict, prenotazioni: dict, sol: dict) -> str:
    dati = sala["piantina"]
    turni = sol.get("modalita", {}).get("turni") or sala.get("turni") or []
    ass, nons = sol["assegnazioni"], sol["non_sistemate"]
    comp = sol.get("obiettivo_componenti", {})
    tot_cop = sum(p["coperti"] for p in prenotazioni["prenotazioni"])
    titolo = f'{sol.get("serata") or prenotazioni.get("serata", "Serata")} — {dati.get("nome", "")}'
    kpi = [(f'{sum(r["coperti"] for r in ass)}/{tot_cop}', "coperti sistemati"),
           (f'{len(ass)}/{len(prenotazioni["prenotazioni"])}', "prenotazioni sistemate")]
    for tu in turni:
        nel = [r for r in ass if r["turno"] == tu["nome"]]
        vuoti = posti_vuoti(nel, {str(t["id"]): int(t["posti"]) for t in dati["tavoli"] if t["tipo"] == "lungo"})
        kpi.append((f'{sum(r["coperti"] for r in nel)}', f'coperti nel {tu["nome"]} turno ({tu["inizio"]}) · '
                    f'{len(nel)} prenotazioni · {len({r["tavolo"] for r in nel})} tavoli · {vuoti} posti vuoti'))
    kpi.append((f'{comp.get("divisioni_blocchi", {}).get("numero", 0)}', "divisioni dei blocchi (pezzi in più) · "
                f'{comp.get("riallestimenti", {}).get("numero", 0)} blocchi con partizione diversa tra i turni'))
    s = sol.get("solver", {})
    kpi.append((escape(str(s.get("stato", ""))), f'stato del solver · {s.get("tempo_s", "—")} s'))
    viste = "".join(f'<h2 id="t{i}">{escape(tu["nome"].capitalize())} turno · {tu["inizio"]}–{tu["fine"]}</h2>'
                    f'<div class="vista">{_svg_turno(dati, sol, tu["nome"])}</div>' for i, tu in enumerate(turni))
    salti = " · ".join(f'<a href="#t{i}">{escape(tu["nome"])} turno</a>' for i, tu in enumerate(turni)) + \
        ' · <a href="#elenco">elenco per tavolo</a>'
    righe_ns = "".join(f'<li><b>{escape(r["nome"])}</b> ×{r["coperti"]} alle {r["orario_richiesto"]}: {escape(r["motivo"])}</li>'
                       for r in nons) or "<li>nessuna</li>"
    registro = (f'<h2>Registro delle accettazioni (in ordine di prenotazione)</h2>{_registro(sol)}'
                if sol.get("registro") else "")
    return f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titolo)}</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>{escape(titolo)}</h1>
<p class="sotto">Sala vera dalla piantina (aggiornata il {escape(str(dati.get("aggiornata", "")))}): i tavoli non si spostano.
Giallo = occupato nel turno; contorno arancione tratteggiato = pezzo di un blocco separato. {salti}</p>
<div class="sintesi">{"".join(f'<div class="kpi"><div class="v">{v}</div><div class="l">{escape(l)}</div></div>' for v, l in kpi)}</div>
<div class="box"><h3>Non sistemate</h3><ul>{righe_ns}</ul></div>
{viste}
<h2 id="elenco">Elenco per tavolo</h2>
{_elenco_tavoli(dati, sol, turni)}
{registro}
</div></body></html>
"""


CSS = """
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;margin:0;padding:14px;color:#2c2c2a;background:#faf9f6}
.wrap{max-width:820px;margin:0 auto}
h1{font-size:20px;margin:0 0 4px} h2{font-size:17px;margin:22px 0 8px} h3{font-size:15px;margin:0 0 6px}
.sotto{color:#5f5e5a;font-size:13px;margin:0 0 10px}
.sintesi{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}
.kpi{background:#fff;border:1px solid #e3e1da;border-radius:10px;padding:8px 12px;flex:1 1 150px}
.kpi .v{font-size:20px;font-weight:700} .kpi .l{font-size:12px;color:#5f5e5a}
.box{background:#fff;border:1px solid #e3e1da;border-radius:10px;padding:10px 14px;margin-bottom:10px}
.box ul{margin:0;padding-left:18px;font-size:14px}
.vista{background:#fff;border:1px solid #e3e1da;border-radius:10px;padding:6px}
svg.sala{width:100%;height:auto;display:block}
.et-id{font-size:9px;font-weight:700;fill:#2c2c2a;paint-order:stroke;stroke:#fff;stroke-width:2.5px}
.et-id-blocco{font-size:8px;font-weight:700;fill:#0f6e50;paint-order:stroke;stroke:#fff;stroke-width:2.5px}
.et-chi{font-size:7.5px;fill:#111;paint-order:stroke;stroke:#fff;stroke-width:2.2px}
.et-piccola{font-size:9px;fill:#5f5e5a}
.scorri{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;font-size:13px;width:100%} td,th{padding:4px 6px;border-bottom:1px solid #eeece6;text-align:left;vertical-align:top}
td.num{font-weight:700;white-space:nowrap} .tenue{color:#777;font-size:12px} .nota{color:#6a1b9a;font-style:italic;font-size:12px}
tr.proposta td{background:#e8f1fb} tr.nonsist td{color:#b00020}
a{color:#185fa5}
"""
