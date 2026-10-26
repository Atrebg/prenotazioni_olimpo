"""Comando unico: risolve la serata, scrive soluzione JSON e mappa HTML, lancia la verifica indipendente.

Uso (path assoluti o dalla cartella del progetto):
    .venv\\Scripts\\python.exe esegui.py                                   # config: ordine di arrivo, sabato_pieno
    .venv\\Scripts\\python.exe esegui.py --disposizione variabile --out out\\variabile
    .venv\\Scripts\\python.exe esegui.py --accettazione tutte_insieme --prenotazioni dati\\sabato.json
Exit code = esito del verificatore (0 = tutti i controlli PASS).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent
sys.path.insert(0, str(RADICE))

from ristorante.dati import (  # noqa: E402
    FISSA, MAI, ORDINE_DI_ARRIVO, SEMPRE, TUTTE_INSIEME, VARIABILE, costruisci_istanza, entro_minuti, leggi_json)
from ristorante.mappa import scrivi_html  # noqa: E402
from ristorante.modello import accetta_in_ordine, risolvi  # noqa: E402


def stampa_sintesi(sol: dict, n_pren: int, n_cop: int) -> None:
    s, c = sol["solver"], sol["obiettivo_componenti"]
    ass = sol["assegnazioni"]
    mod = sol.get("modalita", {})
    print(f"Modalità: accettazione {mod.get('accettazione')} · disposizione {mod.get('disposizione')}"
          + (f" · proposta: {mod['cliente_accetta_proposta']} (max {mod['proposta_max_distanza_min']} min)"
             if mod.get("cliente_accetta_proposta") else ""))
    if "accettazione" in sol:
        a = sol["accettazione"]
        print(f"Accettate {a['accettate']} (di cui {a['accettate_su_proposta']} su proposta), rifiutate {a['rifiutate']} "
              f"(di cui {a['proposte_rifiutate_dal_cliente']} per proposta non accettata)")
        print(f"Decisioni: {a['decisioni_ammissibili']} ammissibili, {a['decisioni_ammissibili_su_proposta']} con proposta, "
              f"{a['decisioni_impossibili_dimostrate']} impossibili "
              f"(dimostrato), {a['decisioni_impossibili_a_priori']} impossibili a priori, {a['decisioni_unknown']} UNKNOWN "
              f"· tempo decisioni {a['tempo_decisioni_s']} s")
    print(f"Piantina: {s['stato']} in {s.get('tempo_s')} s · obiettivo {s['obiettivo']} · bound {s.get('bound')} · "
          f"gap {s.get('gap_pct')}%" + (f" · origine: {s['origine']}" if s.get("origine") else ""))
    print(f"Componenti: non sistemate {c['non_sistemate']['costo']} · posti vuoti {c['posti_vuoti']['costo']} "
          f"({c['posti_vuoti']['posti']}) · spostamenti {c['spostamenti']['costo']} ({c['spostamenti']['quarti_d_ora']} quarti) · "
          f"accostamenti {c['accostamenti']['costo']} · picco cucina {c['picco_cucina']['costo']} · "
          f"riallestimenti {c['riallestimenti']['costo']} ({c['riallestimenti']['numero']})")
    print(f"Sistemate {len(ass)}/{n_pren} prenotazioni, {sum(r['coperti'] for r in ass)}/{n_cop} coperti, "
          f"{len(sol['tavoli'])} tavoli")
    for r in sol["non_sistemate"]:
        print(f"  non sistemata: {r['id']} {r['nome']} ×{r['coperti']} {r['orario_richiesto']} — {r['motivo']}")


def esegui(sala_p: str, pren_p: str, out: Path, accettazione: str | None, disposizione: str | None,
           tempo: float | None = None, tempo_decisione: float | None = None, tempo_spareggio: float | None = None,
           tempo_piantina: float | None = None, log: bool = False, proposta: str | None = None,
           tempo_proposta: float | None = None) -> tuple[dict, int]:
    sala, pren = leggi_json(sala_p), leggi_json(pren_p)
    ist = costruisci_istanza(sala, pren)
    if proposta:
        if proposta not in (MAI, SEMPRE):
            entro_minuti(proposta)
        ist.cliente_accetta_proposta = proposta
    accettazione = accettazione or ist.accettazione
    disposizione = disposizione or ist.disposizione
    n_pren, n_cop = len(ist.prenotazioni), sum(p.coperti for p in ist.prenotazioni)
    print(f"Sala: {sala.get('nome', '')} · serata: {pren.get('serata', '')} · {n_pren} prenotazioni, {n_cop} coperti",
          flush=True)
    t0 = time.perf_counter()
    if accettazione == ORDINE_DI_ARRIVO:
        sol = accetta_in_ordine(ist, disposizione=disposizione, tempo_decisione_s=tempo_decisione,
                                tempo_spareggio_s=tempo_spareggio, tempo_piantina_s=tempo_piantina, log=log,
                                avanzamento=lambda msg: print(msg, flush=True), tempo_proposta_s=tempo_proposta)
    else:
        sol = risolvi(ist, tempo_limite_s=tempo, log=log, disposizione=disposizione)
    sol["tempo_esecuzione_s"] = round(time.perf_counter() - t0, 1)

    out.mkdir(parents=True, exist_ok=True)
    p_sol, p_html = out / "soluzione.json", out / "serata.html"
    p_sol.write_text(json.dumps(sol, ensure_ascii=False, indent=2), encoding="utf-8")
    scrivi_html(sala, pren, sol, p_html)
    stampa_sintesi(sol, n_pren, n_cop)
    print(f"Scritti: {p_sol} · {p_html}")
    print(flush=True)
    # verifica INDIPENDENTE in un processo separato (non condivide codice né memoria col modello)
    esito = subprocess.run([sys.executable, str(RADICE / "verifica.py"), "--sala", sala_p,
                            "--prenotazioni", pren_p, "--soluzione", str(p_sol)])
    return sol, esito.returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Organizza la sala del ristorante per una serata (OR-Tools CP-SAT)")
    ap.add_argument("--sala", default=str(RADICE / "dati" / "sala_esempio.json"))
    ap.add_argument("--prenotazioni", default=str(RADICE / "dati" / "sabato_pieno.json"))
    ap.add_argument("--out", default=str(RADICE / "out"), help="cartella di uscita (soluzione.json, serata.html)")
    ap.add_argument("--accettazione", choices=[ORDINE_DI_ARRIVO, TUTTE_INSIEME], default=None,
                    help="default: config della sala")
    ap.add_argument("--disposizione", choices=[FISSA, VARIABILE], default=None, help="default: config della sala")
    ap.add_argument("--tempo", type=float, default=None, help="tutte_insieme: limite del solver (s)")
    ap.add_argument("--tempo-decisione", type=float, default=None, help="ordine_di_arrivo: limite per decisione (s)")
    ap.add_argument("--tempo-spareggio", type=float, default=None, help="ordine_di_arrivo: limite dello spareggio (s)")
    ap.add_argument("--tempo-piantina", type=float, default=None, help="ordine_di_arrivo: limite della piantina (s)")
    ap.add_argument("--proposta", default=None, help="politica del cliente: mai | sempre | entro_N_min (default: config)")
    ap.add_argument("--tempo-proposta", type=float, default=None, help="limite per ogni orario proposto provato (s)")
    ap.add_argument("--log", action="store_true", help="mostra il log di ricerca di CP-SAT")
    a = ap.parse_args(argv)
    _, rc = esegui(a.sala, a.prenotazioni, Path(a.out), a.accettazione, a.disposizione, a.tempo,
                   a.tempo_decisione, a.tempo_spareggio, a.tempo_piantina, a.log, a.proposta, a.tempo_proposta)
    return rc


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
