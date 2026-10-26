"""Modalità a turni: mappatura orario → turno, proposte dell'altro turno, disposizione fissa e variabile, chat con
"1t"/"2t", verificatore (anche negativo) e tabella delle disponibilità per classe × turno."""
import copy
import json
import random
from datetime import date, datetime, timedelta

import pytest
from conftest import sala_piccola

from ristorante import conversazione
from ristorante.conversazione import _Conversazione, gestisci_messaggio, piantina_serata
from ristorante.dati import MOTIVO_TURNO_PIENO, costruisci_istanza
from ristorante.disponibilita import CalcolatoreLocale, Disponibilita
from ristorante.lettura import Lettura, leggi_compatto
from ristorante.modello import accetta_in_ordine
from ristorante.serate import Archivio, serata_vuota

TURNI = [{"nome": "primo", "inizio": "20:00", "fine": "21:30"}, {"nome": "secondo", "inizio": "21:30", "fine": "24:00"}]
MARTEDI = datetime(2026, 10, 27, 10, 0)
SAB = date(2026, 10, 31)


class SenzaLLM:
    disponibile = False


@pytest.fixture(autouse=True)
def senza_disponibilita_globale():
    conversazione.ferma_disponibilita()
    yield
    conversazione.ferma_disponibilita()


def a_turni(sala: dict, **extra) -> dict:
    sala["turni"] = copy.deepcopy(TURNI)
    sala.update(extra)
    return sala


def in_arrivo(*righe) -> dict:
    """righe: (id, coperti, "HH:MM"[, turno]) ricevute in quest'ordine."""
    pren = []
    for i, r in enumerate(righe):
        p = {"id": r[0], "nome": r[0], "coperti": r[1], "orario": r[2], "prenotata_il": f"2026-10-2{i // 10}T1{i % 10}:00"}
        if len(r) > 3:
            p["turno"] = r[3]
        pren.append(p)
    return {"serata": "prova", "prenotazioni": pren}


def test_orario_nel_turno_piu_vicino_con_la_parita():
    righe = [("A", 2, "19:30"), ("B", 2, "20:45"), ("C", 2, "21:00"), ("D", 2, "23:00"), ("E", 2, "19:00", "secondo")]
    ist = costruisci_istanza(a_turni(sala_piccola()), in_arrivo(*righe))
    assert [ist.turno_della(p) for p in ist.prenotazioni] == [0, 0, 1, 1, 1]     # 20:45 è a metà: vince il primo
    ist2 = costruisci_istanza(a_turni(sala_piccola(), turno_a_parita="dopo"), in_arrivo(*righe))
    assert [ist2.turno_della(p) for p in ist2.prenotazioni] == [0, 1, 1, 1, 1]
    # opzioni e proposte: il turno chiesto, poi l'altro (senza limite di distanza)
    b = ist.prenotazioni[1]
    assert ist.opzioni(b) == [(-45, ist.passo_turno(0))]
    assert ist.candidati_proposta(b) == ([], [(45, ist.passo_turno(1))])
    # in chat: le 19:00 e le 23:00 sono lontane da entrambi i turni (oltre 45 min), le 20:45 no
    conv = _Conversazione(Archivio("."), a_turni(sala_piccola()), SenzaLLM(), MARTEDI, "x")
    for orario, atteso in (("19:00", ("19:00", None, 0)), ("23:00", ("23:00", None, 1)), ("20:45", ("20:00", 1, None)),
                           ("21:15", ("21:30", 2, None))):
        lett = Lettura("nuova", "compatto", nome="X", coperti=2, orario=orario, data=SAB)
        conv._metti_nel_turno(lett)
        assert (lett.orario, lett.turno, lett.turno_lontano) == atteso, orario


def test_formato_compatto_con_i_turni():
    for testo, turno, note in (("Rossi 4 sab 1t", 1, None), ("Rossi 4 sab 2t seggiolone", 2, "seggiolone"),
                               ("Rossi 4 sab secondo turno", 2, None), ("Rossi 4 sab primo turno [compleanno]", 1, "compleanno")):
        lett = leggi_compatto(testo)
        assert (lett.intento, lett.nome, lett.coperti, lett.turno, lett.orario, lett.note) == \
               ("nuova", "Rossi", 4, turno, None, note), testo
    assert leggi_compatto("Rossi 4 sab 21").orario == "21:00"


def test_turno_pieno_proposta_dell_altro_turno_e_conferma(tmp_path, verificatore):
    sala = a_turni(sala_piccola(300, 300, moduli=1))     # un solo tavolo da 4: una prenotazione per turno

    def invia(t, minuti=0):
        return gestisci_messaggio(t, MARTEDI + timedelta(minutes=minuti), "p", tmp_path, sala=sala, lettore=SenzaLLM())

    assert invia("Rossi 2 sab 20:00") == "✓ Rossi · 2 persone · sab 31/10 · primo turno (20:00)"
    assert invia("Bianchi 2 sab 1t", 1) == ("Bianchi · 2 persone · sab 31/10: il primo turno è pieno. "
                                           "Posso nel secondo, alle 21:30. Va bene?")
    assert [a["nome"] for a in Archivio(tmp_path).carica(SAB)["accettate"]] == ["Rossi"]   # registra solo dopo il sì
    assert invia("sì", 2) == "✓ Bianchi · 2 persone · sab 31/10 · secondo turno (21:30)"
    assert invia("Verdi 2 sab 2t", 3) == "Verdi · 2 persone · sab 31/10: il secondo turno è pieno, e anche il primo."
    assert invia("riepilogo sab", 4) == ("sab 31/10 · 2 prenotazioni · 4 coperti\n"
                                         "Primo turno (20:00) · 1 prenotazione · 2 coperti\n  Rossi 2\n"
                                         "Secondo turno (21:30) · 1 prenotazione · 2 coperti\n  Bianchi 2")
    stato = Archivio(tmp_path).carica(SAB)
    assert [(a["nome"], a["orario"], a["turno"], a["orario_richiesto"]) for a in stato["accettate"]] == \
           [("Rossi", "20:00", "primo", "20:00"), ("Bianchi", "21:30", "secondo", "20:00")]
    # piantina: lo stesso tavolo nei due turni, verificata
    sol, p_pren, p_sol = piantina_serata(tmp_path, SAB, sala, out=tmp_path / "piantina", tempo_s=20)
    assert len(sol["tavoli"]) == 1 and sorted(r["turno"] for r in sol["assegnazioni"]) == ["primo", "secondo"]
    esiti = verificatore.verifica(sala, json.loads(p_pren.read_text(encoding="utf-8")), sol)
    assert all(e.ok for e in esiti), [(e.nome, e.errori) for e in esiti if not e.ok]


def test_chat_con_1t_2t_orari_lontani_e_senza_turni(tmp_path):
    sala = a_turni(sala_piccola(600, 300, moduli=2))

    def invia(t, minuti=0, s=sala, cartella=tmp_path):
        return gestisci_messaggio(t, MARTEDI + timedelta(minutes=minuti), "p", cartella, sala=s, lettore=SenzaLLM())

    assert invia("Rossi 4 sab 2t") == "✓ Rossi · 4 persone · sab 31/10 · secondo turno (21:30)"
    assert invia("Bianchi 2 sab 20:45", 1) == "✓ Bianchi · 2 persone · sab 31/10 · primo turno (20:00)"
    assert invia("Verdi 3 sab 19:00", 2) == ("Verdi · 3 persone · sab 31/10: alle 19:00 non c'è un turno. Il più vicino è il "
                                            "primo, alle 20:00. Va bene? Non ho ancora registrato niente.")
    assert len(Archivio(tmp_path).carica(SAB)["accettate"]) == 2
    assert invia("ok", 3) == "✓ Verdi · 3 persone · sab 31/10 · primo turno (20:00)"
    acc = {a["nome"]: a for a in Archivio(tmp_path).carica(SAB)["accettate"]}
    assert (acc["Bianchi"]["orario_richiesto"], acc["Verdi"]["orario_richiesto"]) == ("20:45", "19:00")
    # nome già presente: "sposta" lo porta nell'altro turno
    assert invia("Rossi 4 sab 1t", 4) == ("C'è già Rossi nel secondo turno (21:30) per 4 persone (sab 31/10): è un'altra "
                                         "prenotazione o la sposto nel primo turno?")
    # due moduli = due tavoli, già occupati nel primo turno da Bianchi e Verdi: Rossi resta dov'è
    assert invia("sposta", 5) == ("Rossi · 4 persone · sab 31/10: il primo turno è pieno. La prenotazione resta com'è, "
                                  "nel secondo turno (21:30).")
    # senza turni "1t" non vuol dire niente: si chiede l'orario
    senza = sala_piccola()
    assert invia("Neri 2 sab 1t", 6, s=senza, cartella=tmp_path / "b") == \
           "Neri · 2 persone · sab 31/10 · ? — Qui non ci sono turni. A che ora?"


def _ordine(disp: str, politica: str = "mai"):
    sala = a_turni(sala_piccola(600, 400, moduli=4), cliente_accetta_proposta=politica)
    pren = in_arrivo(("A4", 4, "20:00"), ("B4", 4, "20:00"), ("C10", 10, "21:30"))
    ist = costruisci_istanza(sala, pren)
    return sala, pren, accetta_in_ordine(ist, disposizione=disp, tempo_decisione_s=30, tempo_proposta_s=30,
                                         tempo_piantina_s=30)


def test_fissa_stessi_tavoli_e_accostamenti_nei_due_turni(verificatore):
    sala, pren, sol = _ordine("fissa")
    assert sol["accettazione"]["accettate"] == 2
    assert sol["non_sistemate"][0]["id"] == "C10" and sol["non_sistemate"][0]["motivo"] == MOTIVO_TURNO_PIENO
    assert all(t["turni"] == ["primo", "secondo"] and not t["montato_in_servizio"] for t in sol["tavoli"])
    esiti = verificatore.verifica(sala, pren, sol)
    assert all(e.ok for e in esiti), [(e.nome, e.errori) for e in esiti if not e.ok]
    # negativo: un tavolo che c'è solo nel primo turno non è "fissa"
    rotta = copy.deepcopy(sol)
    rotta["tavoli"][0]["esiste_al"], rotta["tavoli"][0]["turni"] = "21:30", ["primo"]
    falliti = {e.nome for e in verificatore.verifica(sala, pren, rotta) if not e.ok}
    assert "disposizione fissa: stessi tavoli e stessi accostamenti in tutti i turni" in falliti


def test_variabile_il_gruppo_da_10_usa_i_moduli_dei_due_tavoli_da_4(verificatore):
    sala, pren, sol = _ordine("variabile")
    assert sol["accettazione"]["accettate"] == 3
    per_id = {r["id"]: r for r in sol["assegnazioni"]}
    tav = {t["id"]: t for t in sol["tavoli"]}
    grande = tav[per_id["C10"]["tavolo"]]
    assert (grande["moduli"], grande["turni"], grande["montato_in_servizio"]) == (4, ["secondo"], True)
    piccoli = [tav[per_id[i]["tavolo"]] for i in ("A4", "B4")]
    assert all(t["turni"] == ["primo"] and t["moduli"] == 1 for t in piccoli)
    assert sol["obiettivo_componenti"]["riallestimenti"]["numero"] == 1
    esiti = verificatore.verifica(sala, pren, sol)
    assert all(e.ok for e in esiti), [(e.nome, e.errori) for e in esiti if not e.ok]


def test_verificatore_rifiuta_un_turno_promesso_cambiato(verificatore):
    sala, pren, sol = _ordine("fissa", "sempre")
    assert all(e.ok for e in verificatore.verifica(sala, pren, sol))
    rotta = copy.deepcopy(sol)
    r = next(x for x in rotta["assegnazioni"] if x["id"] == "A4")      # promessa nel primo, spostata nel secondo
    r.update(turno="secondo", orario_assegnato="21:30", fine="24:00")
    falliti = {e.nome for e in verificatore.verifica(sala, pren, rotta) if not e.ok}
    assert "turno finale = turno promesso (e orari uguali a quelli promessi)" in falliti
    assert "turni delle prenotazioni (turno chiesto, orari del turno)" in falliti


def test_tabella_a_turni_uguale_al_calcolo_diretto(tmp_path):
    rnd = random.Random(11)
    sala = a_turni(sala_piccola(600, 400, moduli=4, tondi=1))
    casi = 0
    for prova in range(3):
        cartella = tmp_path / f"s{prova}"
        arch = Archivio(cartella)
        stato = serata_vuota(SAB)
        conv = _Conversazione(arch, sala, SenzaLLM(), MARTEDI, "x")
        for i in range(rnd.randint(4, 9)):
            c, o = rnd.choice([2, 2, 3, 4, 4, 5, 6, 8]), rnd.choice(["20:00", "21:30"])
            if conv._valuta_diretta(stato, c, o).esito == "entra":
                stato["accettate"].append({"id": f"A{i}", "nome": f"N{i}", "coperti": c, "orario": o})
        stato["versione"] = prova + 1
        arch.salva(stato)
        disp = Disponibilita(cartella, sala, CalcolatoreLocale(cartella), cartella_geometria=tmp_path / "geo")
        disp.aggiorna(stato)
        assert disp.tabella_pronta(SAB)
        for _ in range(5):
            c, o = rnd.choice([1, 2, 3, 4, 5, 6, 8, 10]), rnd.choice(["20:00", "21:30"])
            a, b = disp.valuta(stato, c, o), conv._valuta_diretta(stato, c, o)
            assert (a.esito, a.opzioni) == (b.esito, b.opzioni), (stato["accettate"], c, o)
            casi += 1
    assert casi == 15


def test_lettura_llm_con_il_turno_e_contesto_dei_turni(tmp_path):
    """Con l'LLM (client finto): "Rossi in 4 al secondo turno sabato" arriva come turno = 2; nel contesto c'è l'elenco
    dei turni, così il modello sa che cosa vuol dire "secondo turno"."""
    from test_chat import LettoreFinto
    lettore = LettoreFinto({"Rossi in 4 al secondo turno sabato": {
        "intento": "nuova", "nome": "Rossi", "coperti": 4, "data": "2026-10-31", "turno": 2, "testo_data": "sabato"}})
    sala = a_turni(sala_piccola(600, 300, moduli=2))
    r = gestisci_messaggio("Rossi in 4 al secondo turno sabato", MARTEDI, "p", tmp_path, sala=sala, lettore=lettore)
    assert r == "✓ Rossi · 4 persone · sab 31/10 · secondo turno (21:30)"
    assert "primo turno alle 20:00" in lettore.chiamate[0][1] and "secondo turno alle 21:30" in lettore.chiamate[0][1]


def test_sala_a_turni_uguale_alla_sala_di_esempio_salvo_i_turni():
    """dati/sala_turni.json è la sala di esempio più i turni: il resto (geometria, inventario, pesi) non deve divergere."""
    from conftest import RADICE
    base = json.loads((RADICE / "dati" / "sala_esempio.json").read_text(encoding="utf-8"))
    turni = json.loads((RADICE / "dati" / "sala_turni.json").read_text(encoding="utf-8"))
    solo_turni = {"nome", "turni", "turno_a_parita", "turni_vicino_min"}
    assert {k: v for k, v in turni.items() if k not in solo_turni} == {k: v for k, v in base.items() if k not in solo_turni}
    assert [t["inizio"] for t in turni["turni"]] == ["20:00", "21:30"]
