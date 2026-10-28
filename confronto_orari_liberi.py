"""Confronto isolato: solver Python o agente Claude, stesse richieste e sala.

Non interagisce con la chat né scrive prenotazioni reali.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from ristorante.orari_liberi import durata, risolvi, valida_richieste, verifica
from ristorante.piantina import Piantina, leggi_blocco_sala

RADICE = Path(__file__).resolve().parent


def piano_agente(client, modello, pia, richieste):
    unita = [{"id": u.chiave, "tavolo": u.tavolo, "tipo": u.tipo, "posti": u.posti,
              "quadrati": u.quadrati, "gruppo": u.gruppo} for u in pia.unita()]
    dati = [{"id": p["id"], "coperti": p["coperti"], "orario": p["orario"],
             "durata_min": durata(p["coperti"])} for p in richieste]
    prompt = ("Sei un agente che assegna prenotazioni ai tavoli. Rispondi SOLO JSON: "
              '{"stato":"entra","piano":{"id_prenotazione":"id_unita"}} oppure '
              '{"stato":"non entra","piano":null}. Assegna TUTTE le prenotazioni se possibile. '
              "Intervalli [inizio, fine), senza riapparecchiatura. Nessuna sovrapposizione sulla "
              "stessa unità. Parti di uno stesso blocco non possono sovrapporsi se condividono un "
              "quadrato. Il tavolo lungo consente al massimo due gruppi contemporanei, uno per "
              "ciascuna unità; se sono due, entrambi devono avere al massimo 8 coperti. "
              "Rispetta la capienza. Non aggiungere né spostare prenotazioni.\n" +
              json.dumps({"prenotazioni": dati, "unita": unita}, ensure_ascii=False))
    risposta = client.messages.create(model=modello, max_tokens=4096,
                                      messages=[{"role": "user", "content": prompt}])
    if risposta.stop_reason != "end_turn":
        raise ValueError(f"risposta incompleta o rifiutata: {risposta.stop_reason}")
    testo = "".join(x.text for x in risposta.content if x.type == "text").strip()
    result = json.loads(testo)
    if result.get("stato") not in ("entra", "non entra"):
        raise ValueError("stato non valido")
    return result


def confronta(pia, richieste, metodo, modello=None, tempo_s=20):
    if metodo == "agente":
        if not os.environ.get("ANTHROPIC_API_KEY") or not modello:
            raise ValueError("Per l'agente servono ANTHROPIC_API_KEY e --modello")
        import anthropic
        client = anthropic.Anthropic()
    accettate, registro = [], []
    for p in richieste:
        inizio = time.perf_counter()
        decisione_secondi = None
        candidato = accettate + [p]
        try:
            valida_richieste(candidato)
            if metodo == "python":
                esito = risolvi(pia, candidato, tempo_s)
                stato, piano, errori = esito.stato, esito.piano, []
            else:
                risposta = piano_agente(client, modello, pia, candidato)
                decisione_secondi = time.perf_counter() - inizio
                stato, piano = risposta["stato"], risposta.get("piano")
                if stato == "entra":
                    errori = verifica(pia, candidato, piano) if isinstance(piano, dict) else ["piano non valido"]
                    if errori:
                        stato = "piano non valido"
                else:
                    # Un rifiuto dell'agente non è una prova di impossibilità.
                    riferimento = risolvi(pia, candidato, tempo_s)
                    errori = []
                    stato = {"entra": "rifiuto errato", "non entra": "non entra",
                             "non verificato": "rifiuto non verificato"}[riferimento.stato]
            if stato == "entra":
                accettate.append(p)
        except Exception as exc:
            stato, piano, errori = "errore", None, [str(exc)]
        registro.append({"id": p.get("id"), "stato": stato, "errori": errori,
                         "secondi": round(time.perf_counter() - inizio, 3),
                         "secondi_decisione": round(decisione_secondi, 3) if decisione_secondi is not None else None,
                         **({"piano": piano} if stato == "entra" else {})})
    return {"metodo": metodo, "modello": modello if metodo == "agente" else None,
            "richieste": len(richieste), "accettate": len(accettate), "registro": registro}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sala", default=str(RADICE / "olimpo/piantina.html"))
    parser.add_argument("--prenotazioni", default=str(RADICE / "dati/olimpo_venerdi.json"))
    parser.add_argument("--metodo", choices=["python", "agente", "entrambi"], default="python")
    parser.add_argument("--modello", help="modello Anthropic da usare per l'agente")
    parser.add_argument("--tempo", type=float, default=20)
    args = parser.parse_args()
    pia = Piantina(leggi_blocco_sala(args.sala))
    with open(args.prenotazioni, encoding="utf-8") as f:
        dati = json.load(f)
    richieste = sorted(dati["prenotazioni"], key=lambda p: p.get("prenotata_il", ""))
    try:
        if args.metodo == "entrambi":
            risultato = {m: confronta(pia, richieste, m, args.modello, args.tempo) for m in ("python", "agente")}
        else:
            risultato = confronta(pia, richieste, args.metodo, args.modello, args.tempo)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(risultato, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
