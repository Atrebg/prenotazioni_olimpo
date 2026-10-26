"""Confronti per il proprietario, con accettazione in ordine di arrivo.

Uso:
    .venv\\Scripts\\python.exe confronto.py                                   # fissa contro variabile (config)
    .venv\\Scripts\\python.exe confronto.py --modi fissa --politiche mai sempre entro_60_min --out out\\confronto_proposte
    .venv\\Scripts\\python.exe confronto.py --da-json                         # solo mappe, verifiche e tabella dai JSON
    .venv\\Scripts\\python.exe confronto.py --sala dati\\sala_turni.json --combinazioni fissa:mai fissa:sempre variabile:sempre ^
        --out out\\confronto_turni                                             # modalità a turni
Per ogni combinazione scrive <out>\\<nome>\\{soluzione.json, serata.html} e <out>\\confronto.json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent
sys.path.insert(0, str(RADICE))

from esegui import esegui  # noqa: E402
from ristorante.dati import FISSA, ORDINE_DI_ARRIVO, VARIABILE, leggi_json  # noqa: E402
from ristorante.mappa import scrivi_html  # noqa: E402


def riga(nome: str, sol: dict, rc: int) -> dict:
    a, c, s = sol["accettazione"], sol["obiettivo_componenti"], sol["solver"]
    reg = {r["id"]: r for r in sol.get("registro", [])}
    turni = sol["modalita"].get("turni") or []
    spostati = []
    for r in sorted(sol["assegnazioni"], key=lambda r: r["orario_richiesto"]):
        if turni and r.get("turno") != r.get("turno_richiesto"):
            spostati.append(f'{r["nome"]} ×{r["coperti"]} (chiesto alle {r["orario_richiesto"]}): {r["turno_richiesto"]} '
                            f'→ {r["turno"]} turno, su proposta')
        if r["spostamento_min"]:
            q = reg.get(r["id"], {})
            tipo = "proposta" if q.get("esito") == "accettata su proposta" else "spostamento ammesso"
            extra = (f", proposte prima {q.get('proposta_prima') or '—'} / dopo {q.get('proposta_dopo') or '—'}"
                     if tipo == "proposta" else "")
            spostati.append(f'{r["nome"]} ×{r["coperti"]}: {r["orario_richiesto"]} → {r["orario_assegnato"]} '
                            f'({r["spostamento_min"]:+d}′, {tipo}{extra})')
    return {
        "nome": nome,
        "disposizione": sol["modalita"]["disposizione"],
        "politica": sol["modalita"].get("cliente_accetta_proposta"),
        "accettate": a["accettate"],
        "accettate_su_proposta": a.get("accettate_su_proposta", 0),
        "rifiutate": a["rifiutate"],
        "proposte_rifiutate_dal_cliente": a.get("proposte_rifiutate_dal_cliente", 0),
        "coperti_accettati": sum(r["coperti"] for r in sol["assegnazioni"]),
        "coperti_rifiutati": sum(r["coperti"] for r in sol["non_sistemate"]),
        "rifiutate_dettaglio": [f'{r["nome"]} ×{r["coperti"]} {r["orario_richiesto"]}: {r["motivo"]}'
                                for r in sol["non_sistemate"]],
        "spostati": spostati,
        "tavoli": len(sol["tavoli"]),
        "accostati": [f'{t["id"]} da {t["moduli"]} moduli ({t["capienza"]} posti' +
                      (f', {"/".join(t["turni"])} turno)' if turni else ")")
                      for t in sol["tavoli"] if t["tipo"] == "moduli" and t["moduli"] > 1],
        "moduli_oltre_il_primo": c["accostamenti"]["moduli_oltre_il_primo"],
        "per_turno": {t["nome"]: {"prenotazioni": sum(1 for r in sol["assegnazioni"] if r.get("turno") == t["nome"]),
                                  "coperti": sum(r["coperti"] for r in sol["assegnazioni"] if r.get("turno") == t["nome"]),
                                  "tavoli": sum(1 for x in sol["tavoli"] if t["nome"] in x.get("turni", []))}
                      for t in turni},
        "riallestimenti": c["riallestimenti"]["numero"],
        "obiettivo_piantina": s["obiettivo"],
        "obiettivo_senza_rifiuti": c["totale"] - c["non_sistemate"]["costo"],
        "stato_piantina": s["stato"],
        "bound_piantina": s.get("bound"),
        "origine_piantina": s.get("origine"),
        "decisioni_ammissibili": a["decisioni_ammissibili"],
        "decisioni_ammissibili_su_proposta": a.get("decisioni_ammissibili_su_proposta", 0),
        "decisioni_impossibili_dimostrate": a["decisioni_impossibili_dimostrate"],
        "decisioni_impossibili_a_priori": a["decisioni_impossibili_a_priori"],
        "decisioni_unknown": a["decisioni_unknown"],
        "spostamento_minimo_non_dimostrato": a["spostamento_minimo_non_dimostrato"],
        "tempo_decisioni_s": a["tempo_decisioni_s"],
        "tempo_piantina_s": s.get("tempo_piantina_s"),
        "tempo_totale_s": sol.get("tempo_esecuzione_s"),
        "verifica": "PASS" if rc == 0 else "FAIL",
    }


def tabella(righe: list[dict]) -> str:
    voci = [("accettate (su proposta) / rifiutate", lambda r: f'{r["accettate"]} ({r["accettate_su_proposta"]}) / {r["rifiutate"]}'),
            ("coperti accettati / rifiutati", lambda r: f'{r["coperti_accettati"]} / {r["coperti_rifiutati"]}'),
            ("proposte non accettate dal cliente", lambda r: r["proposte_rifiutate_dal_cliente"]),
            ("tavoli · riallestimenti", lambda r: f'{r["tavoli"]} · {r["riallestimenti"]}'),
            ("moduli accostati (oltre il primo)", lambda r: r["moduli_oltre_il_primo"]),
            ("obiettivo piantina (senza rifiuti)", lambda r: f'{r["obiettivo_piantina"]} ({r["obiettivo_senza_rifiuti"]})'),
            ("stato piantina · bound", lambda r: f'{r["stato_piantina"]} · {r["bound_piantina"]}'),
            ("decisioni: ammissibili / con proposta", lambda r: f'{r["decisioni_ammissibili"]} / {r["decisioni_ammissibili_su_proposta"]}'),
            ("impossibili dimostrate (+ a priori)", lambda r: f'{r["decisioni_impossibili_dimostrate"]} (+{r["decisioni_impossibili_a_priori"]})'),
            ("UNKNOWN", lambda r: r["decisioni_unknown"]),
            ("tempo decisioni / piantina / totale (s)", lambda r: f'{r["tempo_decisioni_s"]} / {r["tempo_piantina_s"]} / {r["tempo_totale_s"]}'),
            ("verifica indipendente", lambda r: r["verifica"])]
    if any(r["per_turno"] for r in righe):
        voci.insert(2, ("per turno: prenotazioni / coperti / tavoli", lambda r: " · ".join(
            f'{n} {v["prenotazioni"]}/{v["coperti"]}/{v["tavoli"]}' for n, v in r["per_turno"].items())))
    out = ["| | " + " | ".join(r["nome"] for r in righe) + " |", "|---|" + "---|" * len(righe)]
    for nome, f in voci:
        out.append(f"| {nome} | " + " | ".join(str(f(r)) for r in righe) + " |")
    for r in righe:
        out.append(f'\nSpostati ({r["nome"]}): ' + ("; ".join(r["spostati"]) or "nessuno"))
        out.append(f'Tavoli accostati ({r["nome"]}): ' + ("; ".join(r["accostati"]) or "nessuno"))
        out.append(f'Rifiutate ({r["nome"]}): ' + ("; ".join(r["rifiutate_dettaglio"]) or "nessuna"))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Confronti in ordine di arrivo: disposizione e politica delle proposte")
    ap.add_argument("--sala", default=str(RADICE / "dati" / "sala_esempio.json"))
    ap.add_argument("--prenotazioni", default=str(RADICE / "dati" / "sabato_pieno.json"))
    ap.add_argument("--out", default=str(RADICE / "out" / "confronto"))
    ap.add_argument("--modi", nargs="+", default=[FISSA, VARIABILE], choices=[FISSA, VARIABILE])
    ap.add_argument("--politiche", nargs="+", default=None,
                    help="politiche del cliente da confrontare (mai, sempre, entro_N_min); default: quella della config")
    ap.add_argument("--combinazioni", nargs="+", default=None,
                    help="coppie disposizione:politica (es. fissa:mai variabile:sempre), al posto di --modi × --politiche")
    ap.add_argument("--da-json", action="store_true", help="non risolve: rigenera mappa, verifica e tabella dai JSON")
    ap.add_argument("--tempo-decisione", type=float, default=None)
    ap.add_argument("--tempo-spareggio", type=float, default=None)
    ap.add_argument("--tempo-piantina", type=float, default=None)
    ap.add_argument("--tempo-proposta", type=float, default=None)
    a = ap.parse_args(argv)
    out = Path(a.out)
    combinazioni = [(d, p) for d in a.modi for p in (a.politiche or [None])]
    if a.combinazioni:
        combinazioni = [tuple(c.split(":", 1)) for c in a.combinazioni]
    righe = []
    for disp, pol in combinazioni:
        if pol is None:
            nome = disp
        else:
            nome = pol if len(a.modi) == 1 and not a.combinazioni else f"{disp}_{pol}"
        cartella = out / nome
        print(f"\n=== {nome} ===", flush=True)
        if a.da_json:
            sol = json.loads((cartella / "soluzione.json").read_text(encoding="utf-8"))
            scrivi_html(leggi_json(a.sala), leggi_json(a.prenotazioni), sol, cartella / "serata.html")
            rc = subprocess.run([sys.executable, str(RADICE / "verifica.py"), "--sala", a.sala, "--prenotazioni",
                                 a.prenotazioni, "--soluzione", str(cartella / "soluzione.json")]).returncode
        else:
            sol, rc = esegui(a.sala, a.prenotazioni, cartella, ORDINE_DI_ARRIVO, disp,
                             tempo_decisione=a.tempo_decisione, tempo_spareggio=a.tempo_spareggio,
                             tempo_piantina=a.tempo_piantina, proposta=pol, tempo_proposta=a.tempo_proposta)
        righe.append(riga(nome, sol, rc))
    (out / "confronto.json").write_text(json.dumps(righe, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + tabella(righe))
    return 0 if all(r["verifica"] == "PASS" for r in righe) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
