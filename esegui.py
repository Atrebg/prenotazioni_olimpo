"""Comando unico: risolve la serata, scrive soluzione JSON e mappa HTML, lancia la verifica indipendente.

Uso (path assoluti o dalla cartella del progetto):
    .venv\\Scripts\\python.exe esegui.py                                   # config: ordine di arrivo, sabato_pieno
    .venv\\Scripts\\python.exe esegui.py --disposizione variabile --out out\\variabile
    .venv\\Scripts\\python.exe esegui.py --accettazione tutte_insieme --prenotazioni dati\\sabato.json
    .venv\\Scripts\\python.exe esegui.py --sala olimpo\\piantina.html --prenotazioni dati\\olimpo_sabato.json ^
        --disposizione libera --confronto out\\olimpo_sabato_fissa\\soluzione.json --out out\\olimpo_sabato_libera
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
from ristorante.modello_libero import LIBERA, accetta_in_ordine_libera  # noqa: E402
from ristorante.modello_piantina import posti_vuoti  # noqa: E402
from ristorante.piantina import carica_sala  # noqa: E402


def stampa_sintesi(sol: dict, n_pren: int, n_cop: int) -> None:
    s, c = sol["solver"], sol["obiettivo_componenti"]
    ass = sol["assegnazioni"]
    mod = sol.get("modalita", {})
    print(f"Modalità: accettazione {mod.get('accettazione')} · disposizione {mod.get('disposizione')}"
          + (f" · proposta: {mod['cliente_accetta_proposta']}"
             + ("" if mod.get("turni") else f" (max {mod['proposta_max_distanza_min']} min)")
             if mod.get("cliente_accetta_proposta") else "")
          + (" · turni: " + ", ".join(f"{t['nome']} {t['inizio']}-{t['fine']}" for t in mod["turni"])
             if mod.get("turni") else ""))
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
    for t in mod.get("turni") or []:
        nel = [r for r in ass if r.get("turno") == t["nome"]]
        if mod.get("sala_vera"):        # sala vera: tavoli usati, posti vuoti, blocchi divisi, lungo
            div = [f"{x['id']} {'+'.join(str(b - a + 1) for a, b in x['partizioni'][t['nome']])}" for x in sol["tavoli"]
                   if len(x.get("partizioni", {}).get(t["nome"], [])) > 1]
            lungo = [f"{r['nome']} ×{r['coperti']}" for r in nel if r.get("gruppo")]
            print(f"  {t['nome']} turno ({t['inizio']}-{t['fine']}): {len(nel)} prenotazioni, "
                  f"{sum(r['coperti'] for r in nel)} coperti, {len({r['tavolo'] for r in nel})}/{len(sol['tavoli'])} tavoli, "
                  f"{posti_vuoti(nel, {x['id']: x['posti'] for x in sol['tavoli'] if x['tipo'] == 'lungo'})} posti vuoti · blocchi divisi: {', '.join(div) or 'nessuno'}"
                  f" · lungo: {' + '.join(lungo) or 'libero'}")
            continue
        print(f"  {t['nome']} turno ({t['inizio']}-{t['fine']}): {len(nel)} prenotazioni, "
              f"{sum(r['coperti'] for r in nel)} coperti, {sum(1 for x in sol['tavoli'] if t['nome'] in x.get('turni', []))} tavoli")
    for r in sol["non_sistemate"]:
        print(f"  non sistemata: {r['id']} {r['nome']} ×{r['coperti']} {r['orario_richiesto']} — {r['motivo']}")


def stampa_sintesi_libera(sol: dict, n_pren: int, n_cop: int) -> None:
    """Disposizione libera: accettazione, piantina finale, file di quadrati e uso della sala per turno."""
    from ristorante.mappa_libera import riepilogo
    s, a, g = sol["solver"], sol["accettazione"], sol["geometria"]
    mod = sol["modalita"]
    print(f"Modalità: accettazione {mod['accettazione']} · disposizione libera · proposta: {mod['cliente_accetta_proposta']}"
          " · turni: " + ", ".join(f"{t['nome']} {t['inizio']}-{t['fine']}" for t in mod["turni"]))
    print(f"Accettate {a['accettate']} (di cui {a['accettate_su_proposta']} su proposta), rifiutate {a['rifiutate']} · "
          f"decisioni: {a['decisioni_ammissibili']} ammissibili, {a['decisioni_ammissibili_su_proposta']} con proposta, "
          f"{a['decisioni_impossibili_dimostrate']} impossibili (dimostrato), {a['decisioni_unknown']} non decise · "
          f"tempo decisioni {a['tempo_decisioni_s']} s")
    imp = sol.get("impianto") or {}
    dis = imp.get("disegno") or {}
    print(f"Postazioni: {imp.get('postazioni')} file con {imp.get('quadrati')} quadrati e {imp.get('sedie')} sedie · regola "
          f"{imp.get('regola')} · scelta: {imp.get('scelta')} ({', '.join(f'{n} {v}' for n, v in (imp.get('valori') or {}).items())})"
          f" · disegno convertito: {dis.get('file')} file, {dis.get('sedie')} sedie · {imp.get('tempo_s')} s")
    print(f"Piantina: {s['stato']} in {s.get('tempo_piantina_s')} s · obiettivo {s['obiettivo']} · bound {s.get('bound')} · "
          f"origine: {s.get('origine')}")
    file = [t for t in sol["tavoli"] if t.get("tipo") == "fila"]
    print(f"File di quadrati: {len(file)} con {sum(t['moduli'] for t in file)}/{g['quadrati_mobili']} quadrati · "
          + ", ".join(f"{t['id']} {t['moduli']}{'V' if t['orientamento'] == 'verticale' else 'O'} {t['posti']} sedie"
                      for t in file))
    print(f"Sistemate {len(sol['assegnazioni'])}/{n_pren} prenotazioni, "
          f"{sum(r['coperti'] for r in sol['assegnazioni'])}/{n_cop} coperti")
    for nome, x in sol["riepilogo"]["turni"].items():
        print(f"  {nome} turno: {x['prenotazioni']} prenotazioni, {x['coperti']} coperti, {x['tavoli_usati']} tavoli usati "
              f"({x['posti_occupati']} con i pezzi delle file)")
    for r in sol["non_sistemate"]:
        print(f"  non sistemata: {r['id']} {r['nome']} ×{r['coperti']} {r['orario_richiesto']} — {r['motivo']}")
    if g.get("irraggiungibili_secondo_il_motore"):
        print(f"  ATTENZIONE: non raggiungibili secondo il motore: {', '.join(g['irraggiungibili_secondo_il_motore'])}")


def stampa_sintesi_varianti(sol: dict, n_pren: int, n_cop: int) -> None:
    """Disposizione libera dal disegno: variante scelta, accettazione, uso della sala per turno."""
    a, var = sol["accettazione"], sol["variante"]
    print(f"Modalità: disposizione libera dal disegno · disposizione scelta: {var['nome']} ({var['varianti_provate']} provate)")
    from ristorante.libera_varianti import articoli
    for m in var["mosse"]:
        print(articoli(f"  da preparare: {m['mossa']}" + (f" → per {m['per']}, che siede al {m.get('per_tavolo')}" if m.get("per") else "")))
    for pid, chi in (var.get("chi_siede") or {}).items():
        print(articoli(f"  al {pid}: {'; '.join(chi) or 'nessuno'}"))
    if var.get("riserva"):
        print(f"  riserva (solo disegno): {var['riserva']}")
    print(f"Accettate {a['accettate']} (di cui {a['accettate_su_proposta']} su proposta), rifiutate {a['rifiutate']} · "
          f"decisioni: {a['decisioni_impossibili_dimostrate']} impossibili (dimostrato), {a['decisioni_unknown']} non decise · "
          f"tempo decisioni {a['tempo_decisioni_s']} s")
    quadrati = sum(int(t.get("moduli") or 1) for t in sol["tavoli"] if t.get("tipo") in ("quadrato", "blocco"))
    print(f"Sistemate {len(sol['assegnazioni'])}/{n_pren} prenotazioni, {sum(r['coperti'] for r in sol['assegnazioni'])}/{n_cop}"
          f" coperti · quadrati in sala: {quadrati} · tavolo cambiato dopo la conferma: {a.get('tavoli_cambiati', 0)}")
    for nome, x in sol["riepilogo"]["turni"].items():
        print(f"  {nome} turno: {x['prenotazioni']} prenotazioni, {x['coperti']} coperti, {x['tavoli_usati']} tavoli usati")
    for r in sol["non_sistemate"]:
        print(f"  non sistemata: {r['id']} {r['nome']} ×{r['coperti']} {r['orario_richiesto']} — {r['motivo']}")


def esegui_libera(sala_p: str, pren_p: str, out: Path, sala: dict, pren: dict, ist, tempo_decisione: float | None,
                  tempo_piantina: float | None, log: bool, confronto: str | None,
                  corridoio: float | None = None) -> tuple[dict, int]:
    """Disposizione libera dei tavoli mobili sulla sala vera; la verifica indipendente gira dopo, in un processo a sé,
    e il suo esito finisce anche nella mappa."""
    from ristorante.mappa_libera import genera_html, riepilogo
    if corridoio is not None:
        ist.sala["libera"] = dict(ist.sala.get("libera") or {}, corridoio_cm=corridoio)
    n_pren, n_cop = len(ist.prenotazioni), sum(p.coperti for p in ist.prenotazioni)
    tempi = {k: v for k, v in (("tempo_decisione_s", tempo_decisione), ("tempo_piantina_s", tempo_piantina)) if v is not None}
    t0 = time.perf_counter()
    from ristorante.libera_varianti import accetta_in_ordine_varianti
    sol = accetta_in_ordine_varianti(ist, sala, pren, log=log, avanzamento=lambda msg: print(msg, flush=True))
    sol["tempo_esecuzione_s"] = round(time.perf_counter() - t0, 1)
    sol["riepilogo"] = riepilogo(sol, pren)
    if confronto:
        fissa = json.loads(Path(confronto).read_text(encoding="utf-8"))
        sol["confronto_tavoli_fermi"] = riepilogo(fissa, pren) | {"fonte": str(confronto)}
    out.mkdir(parents=True, exist_ok=True)
    p_sol, p_html = out / "soluzione.json", out / "serata.html"
    p_sol.write_text(json.dumps(sol, ensure_ascii=False, indent=2), encoding="utf-8")
    stampa_sintesi_varianti(sol, n_pren, n_cop)
    if confronto:
        c = sol["confronto_tavoli_fermi"]
        print(f"Con i tavoli fermi ({confronto}): {c['prenotazioni']} prenotazioni, {c['coperti']} coperti, "
              f"{c.get('accettate_su_proposta') or 0} nell'altro turno, non sistemate: {', '.join(c['non_sistemate']) or 'nessuna'}"
              + "".join(f" · {n}: {x['prenotazioni']} prenotazioni, {x['coperti']} coperti, {x['tavoli_usati']} tavoli usati"
                        for n, x in c["turni"].items()))
    print(f"Tempo di calcolo: {sol['tempo_esecuzione_s']} s", flush=True)
    print(flush=True)
    esito = subprocess.run([sys.executable, str(RADICE / "verifica.py"), "--sala", sala_p, "--prenotazioni", pren_p,
                            "--soluzione", str(p_sol)], capture_output=True, text=True, encoding="utf-8")
    print(esito.stdout, end="")
    if esito.stderr:
        print(esito.stderr, end="", file=sys.stderr)
    riga = next((r for r in esito.stdout.splitlines() if r.startswith("ESITO:")), None)
    from ristorante.mappa_libera import genera_html_variante
    p_html.write_text(genera_html_variante(sala, pren, sol, riga), encoding="utf-8")
    print(f"Scritti: {p_sol} · {p_html}")
    return sol, esito.returncode


def esegui(sala_p: str, pren_p: str, out: Path, accettazione: str | None, disposizione: str | None,
           tempo: float | None = None, tempo_decisione: float | None = None, tempo_spareggio: float | None = None,
           tempo_piantina: float | None = None, log: bool = False, proposta: str | None = None,
           tempo_proposta: float | None = None, confronto: str | None = None,
           corridoio: float | None = None) -> tuple[dict, int]:
    sala, pren = carica_sala(sala_p), leggi_json(pren_p)
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
    if disposizione == LIBERA:
        if "piantina" not in sala:
            raise SystemExit("--disposizione libera vale solo per la sala vera (--sala olimpo/piantina.html)")
        if accettazione != ORDINE_DI_ARRIVO:
            raise SystemExit("--disposizione libera lavora solo con l'accettazione in ordine di arrivo")
        return esegui_libera(sala_p, pren_p, out, sala, pren, ist, tempo_decisione, tempo_piantina, log, confronto,
                             corridoio)
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
    ap.add_argument("--disposizione", choices=[FISSA, VARIABILE, LIBERA], default=None,
                    help="default: config della sala; libera = tavoli mobili spostati, ruotati, uniti e divisi (sala vera)")
    ap.add_argument("--tempo", type=float, default=None, help="tutte_insieme: limite del solver (s)")
    ap.add_argument("--tempo-decisione", type=float, default=None, help="ordine_di_arrivo: limite per decisione (s)")
    ap.add_argument("--tempo-spareggio", type=float, default=None, help="ordine_di_arrivo: limite dello spareggio (s)")
    ap.add_argument("--tempo-piantina", type=float, default=None, help="ordine_di_arrivo: limite della piantina (s)")
    ap.add_argument("--proposta", default=None, help="politica del cliente: mai | sempre | entro_N_min (default: config)")
    ap.add_argument("--tempo-proposta", type=float, default=None, help="limite per ogni orario proposto provato (s)")
    ap.add_argument("--confronto", default=None, help="libera: soluzione.json del modo a tavoli fermi da confrontare")
    ap.add_argument("--corridoio", type=float, default=None, help="libera: corridoio per il personale in cm (default 60)")
    ap.add_argument("--log", action="store_true", help="mostra il log di ricerca di CP-SAT")
    a = ap.parse_args(argv)
    _, rc = esegui(a.sala, a.prenotazioni, Path(a.out), a.accettazione, a.disposizione, a.tempo,
                   a.tempo_decisione, a.tempo_spareggio, a.tempo_piantina, a.log, a.proposta, a.tempo_proposta,
                   a.confronto, a.corridoio)
    return rc


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
