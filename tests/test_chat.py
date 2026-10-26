"""Chat con il proprietario: lettura, stato delle serate, proposte e conferme. L'API non viene MAI chiamata:
l'LLM è sostituito da un lettore finto (o da un client Anthropic finto per provare la gestione delle risposte)."""
import json
import os
from datetime import datetime
from types import SimpleNamespace

import pytest
from conftest import sala_piccola

from ristorante import serate
from ristorante.conversazione import _Conversazione, gestisci_messaggio
from ristorante.lettura import LettoreAnthropic, LetturaLLM, leggi_compatto
from ristorante.serate import Archivio, scrivi_json_atomico

MARTEDI = datetime(2026, 10, 27, 10, 0)       # sabato prossimo = 31/10/2026
SABATO = datetime(2026, 10, 31, 11, 0)


class LettoreFinto:
    """Al posto di Claude: restituisce letture preparate per testo, e conta le chiamate."""
    disponibile = True

    def __init__(self, risposte: dict | None = None):
        self.risposte, self.chiamate = risposte or {}, []

    def leggi(self, testo, ricevuto_il, inizio, fine, contesto=""):
        self.chiamate.append((testo, contesto))
        return LetturaLLM(**self.risposte[testo])


class SenzaLLM:
    disponibile = False


def chat(tmp_path, sala, lettore=None, mittente="proprietario"):
    def invia(testo, ora=MARTEDI, chi=mittente):
        return gestisci_messaggio(testo, ora, chi, tmp_path, sala=sala, lettore=lettore or LettoreFinto())
    return invia


def stato(tmp_path, giorno="2026-10-31"):
    return json.loads((tmp_path / f"{giorno}.json").read_text(encoding="utf-8"))


def test_nuova_che_entra_formato_compatto(tmp_path):
    invia = chat(tmp_path, sala_piccola(300, 300, moduli=1))
    assert invia("Rossi 4 sab 20:30") == "✓ Rossi · 4 persone · sab 31/10 · 20:30"
    (a,) = stato(tmp_path)["accettate"]
    assert (a["nome"], a["coperti"], a["orario"], a["prenotata_il"]) == ("Rossi", 4, "20:30", "2026-10-27T10:00:00")
    assert stato(tmp_path)["messaggi"][0]["testo"] == "Rossi 4 sab 20:30"


def test_formato_compatto_varianti():
    assert leggi_compatto("Rossi 4 sab 20.30").orario == "20:30"
    l2 = leggi_compatto("De Luca 2 31/10 21")
    assert (l2.nome, l2.coperti, l2.testo_data, l2.orario) == ("De Luca", 2, "31/10", "21:00")
    assert leggi_compatto("Rossi 4 sab 20:30 [seggiolone]").note == "seggiolone"
    assert leggi_compatto("domani sera in 2 verso le 8 e mezza, Bianchi") is None     # passa all'LLM


def test_fascia_piena_proposta_poi_conferma_registrata_e_congelata(tmp_path):
    invia = chat(tmp_path, sala_piccola(300, 300, moduli=1))
    invia("Rossi 2 sab 21:00")
    r = invia("Bianchi 2 sab 20:15")
    assert r == "Bianchi · 2 persone · sab 31/10: alle 20:15 sono pieno. Posso alle 19:15. Quale?"
    assert [a["nome"] for a in stato(tmp_path)["accettate"]] == ["Rossi"]          # niente registrato da solo
    assert invia("ok") == "✓ Bianchi · 2 persone · sab 31/10 · 19:15"
    b = next(a for a in stato(tmp_path)["accettate"] if a["nome"] == "Bianchi")
    assert (b["orario"], b["orario_richiesto"]) == ("19:15", "20:15")
    assert stato(tmp_path)["proposte_in_sospeso"] == []


def test_conferma_dopo_un_cambio_di_stato_riproposta(tmp_path):
    lettore = LettoreFinto({"sposta Rossi alle 19:15": {"intento": "modifica", "riferimento_nome": "Rossi",
                                                         "orario": "19:15"}})
    invia = chat(tmp_path, sala_piccola(300, 300, moduli=1), lettore)
    invia("Rossi 2 sab 21:00", chi="sala")
    assert invia("Bianchi 2 sab 20:15", chi="telefono").endswith("Posso alle 19:15. Quale?")
    assert invia("sposta Rossi alle 19:15", chi="sala").startswith("✓ Modificata Rossi · 2 persone · sab 31/10 · 19:15")
    r = invia("ok", chi="telefono")
    assert r == "Le 19:15 non sono più libere. Bianchi · 2 persone · sab 31/10: alle 20:15 sono pieno. Posso alle 21:00. Quale?"
    assert invia("21", chi="telefono") == "✓ Bianchi · 2 persone · sab 31/10 · 21:00"


def test_modifica_dei_coperti(tmp_path):
    lettore = LettoreFinto({"Ferrari diventano 6": {"intento": "modifica", "riferimento_nome": "Ferrari", "coperti": 6}})
    invia = chat(tmp_path, sala_piccola(500, 300, moduli=3), lettore)
    invia("Ferrari 4 sab 20:00")
    assert invia("Ferrari diventano 6") == \
        "✓ Modificata Ferrari · 6 persone · sab 31/10 · 20:00 (prima 4 persone alle 20:00)"
    assert stato(tmp_path)["accettate"][0]["coperti"] == 6


def test_annullamento_libera_il_posto(tmp_path):
    invia = chat(tmp_path, sala_piccola(300, 300, moduli=1))
    invia("Rossi 2 sab 20:00")
    assert "sono pieno" in invia("Bianchi 2 sab 20:00")
    assert stato(tmp_path)["rifiuti"][0]["nome"] == "Bianchi"
    assert invia("annulla Rossi sab") == "✗ Annullata Rossi · sab 31/10 · 20:00"
    assert invia("Bianchi 2 sab 20:00") == "✓ Bianchi · 2 persone · sab 31/10 · 20:00"


def test_nome_ambiguo_chiede_quale(tmp_path):
    lettore = LettoreFinto({"annulla i Rossi di sabato": {"intento": "annulla", "riferimento_nome": "Rossi",
                                                           "riferimento_data": "2026-10-31", "testo_data": "sabato"}})
    invia = chat(tmp_path, sala_piccola(400, 300, moduli=2), lettore)
    invia("Rossi 2 sab 19:00")
    assert invia("Rossi 4 sab 21:00").startswith("C'è già Rossi alle 19:00 per 2 persone")
    assert invia("è un'altra") == "✓ Rossi · 4 persone · sab 31/10 · 21:00"
    r = invia("annulla i Rossi di sabato")
    assert r == ("Ho 2 prenotazioni a nome Rossi: 1) sab 31/10 19:00 · 2 persone; "
                 "2) sab 31/10 21:00 · 4 persone. Quale?")
    assert len(stato(tmp_path)["accettate"]) == 2                                 # nessuna toccata
    assert invia("la seconda") == "✗ Annullata Rossi · sab 31/10 · 21:00"


def test_coperti_mancanti_chiede_solo_quelli(tmp_path):
    lettore = LettoreFinto({"Bianchi domani alle 8": {"intento": "nuova", "nome": "Bianchi", "data": "2026-10-28",
                                                       "orario": "08:00", "testo_data": "domani",
                                                       "campi_mancanti": ["coperti"]}})
    invia = chat(tmp_path, sala_piccola(300, 300, moduli=1), lettore)
    assert invia("Bianchi domani alle 8") == "Bianchi · ? persone · mer 28/10 · 20:00 — Quante persone?"
    assert invia("x 4") == "✓ Bianchi · 4 persone · mer 28/10 · 20:00"
    assert len(lettore.chiamate) == 1                       # la risposta "x 4" si legge senza LLM


def test_data_passata_chiede(tmp_path):
    invia = chat(tmp_path, sala_piccola(300, 300, moduli=1))
    assert invia("Rossi 4 20/10/2026 20:30") == "Rossi · 4 persone · ? · 20:30 — Il 20/10/2026 è già passato: per quale giorno?"
    assert not (tmp_path / "2026-10-20.json").exists()


def test_sabato_scritto_di_sabato_chiede_stasera_o_prossimo(tmp_path):
    invia = chat(tmp_path, sala_piccola(300, 300, moduli=1))
    assert invia("Rossi 4 sab 20:30", ora=SABATO) == "Rossi · 4 persone · ? · 20:30 — Sabato: stasera o sabato prossimo?"
    assert invia("sabato prossimo", ora=SABATO) == "✓ Rossi · 4 persone · sab 07/11 · 20:30"


def test_arrotondamento_dell_orario_detto_nella_risposta(tmp_path):
    invia = chat(tmp_path, sala_piccola(300, 300, moduli=1))
    assert invia("Bianchi 2 sab 20:07") == \
        "✓ Bianchi · 2 persone · sab 31/10 · 20:00 (orario arrotondato al quarto d'ora: 20:07 → 20:00)"


def test_alle_8_di_sera_e_giorno_incoerente(tmp_path):
    lettore = LettoreFinto({"Neri 2 sabato 30/10 alle 8": {"intento": "nuova", "nome": "Neri", "coperti": 2,
                                                            "data": "2026-10-30", "orario": "08:00",
                                                            "testo_data": "sabato 30/10"}})
    invia = chat(tmp_path, sala_piccola(300, 300, moduli=1), lettore)
    assert invia("Neri 2 sabato 30/10 alle 8") == \
        "Neri · 2 persone · ? · 20:00 — Il 30/10 è venerdì, non sabato: quale dei due?"


def test_llm_non_disponibile_indica_il_formato_compatto(tmp_path):
    invia = chat(tmp_path, sala_piccola(300, 300, moduli=1), SenzaLLM())
    r = invia("domani sera in 2 verso le 8 e mezza, Bianchi")
    assert "manca la chiave ANTHROPIC_API_KEY" in r and "Rossi 4 sab 20:30" in r


def test_rifiuto_del_modello_e_risposta_strutturata_con_client_finto(tmp_path):
    def client(risposta):
        return SimpleNamespace(messages=SimpleNamespace(parse=lambda **kw: risposta))
    rifiuto = LettoreAnthropic(client=client(SimpleNamespace(stop_reason="refusal", parsed_output=None)))
    r = chat(tmp_path, sala_piccola(300, 300, moduli=1), rifiuto)("messaggio strano")
    assert "il modello ha rifiutato" in r and "Rossi 4 sab 20:30" in r
    ok = LettoreAnthropic(client=client(SimpleNamespace(stop_reason="end_turn", parsed_output=LetturaLLM(
        intento="riepilogo", data="2026-10-31", testo_data="sabato"))))
    assert chat(tmp_path, sala_piccola(300, 300, moduli=1), ok)("chi c'è sabato?") == "sab 31/10: nessuna prenotazione."


def test_messaggio_che_non_e_una_prenotazione(tmp_path):
    lettore = LettoreFinto({"ricordati il pesce": {"intento": "non_capito"}})
    r = chat(tmp_path, sala_piccola(300, 300, moduli=1), lettore)("ricordati il pesce")
    assert r.startswith("Non è una prenotazione: non registro niente.")


def test_interpretazione_delle_conferme(tmp_path):
    c = _Conversazione(Archivio(tmp_path), sala_piccola(), None, MARTEDI, "x")
    opz = ["20:15", "21:00"]
    assert c._interpreta_conferma("21", opz) == "21:00"
    assert c._interpreta_conferma("la seconda", opz) == "21:00"
    assert c._interpreta_conferma("ok 20:15", opz) == "20:15"
    assert c._interpreta_conferma("ok", opz) == "quale"
    assert c._interpreta_conferma("no grazie", opz) == "nessuna"
    assert c._interpreta_conferma("Rossi 4 sab 20:30", opz) is None


def test_scrittura_atomica_dello_stato(tmp_path, monkeypatch):
    p = tmp_path / "2026-10-31.json"
    scrivi_json_atomico(p, {"versione": 1})

    def dump_rotto(dati, fh, **kw):
        fh.write('{"versione": ')        # scrittura a metà, poi errore
        raise OSError("disco pieno")

    monkeypatch.setattr(serate.json, "dump", dump_rotto)
    with pytest.raises(OSError):
        scrivi_json_atomico(p, {"versione": 2})
    assert json.loads(p.read_text(encoding="utf-8")) == {"versione": 1}           # il vecchio file è intatto
    assert [f.name for f in tmp_path.iterdir()] == ["2026-10-31.json"]           # nessun temporaneo rimasto
    monkeypatch.undo()
    calls = []
    orig = os.replace
    monkeypatch.setattr(serate.os, "replace", lambda a, b: (calls.append((a, b)), orig(a, b)))
    scrivi_json_atomico(p, {"versione": 3})
    assert len(calls) == 1 and json.loads(p.read_text(encoding="utf-8")) == {"versione": 3}


def test_valutazione_parte_compatta_letta_senza_llm(tmp_path):
    """I messaggi in formato compatto del file di valutazione si leggono senza LLM, con i campi attesi."""
    import valuta_lettura
    from conftest import RADICE, sala_esempio
    voci = valuta_lettura.carica_messaggi(RADICE / "valutazione" / "messaggi.jsonl")
    assert len(voci) >= 40
    compatti = 0
    for voce in voci:
        lett = valuta_lettura.leggi(voce, sala_esempio(), tmp_path)
        if lett is None:
            continue
        compatti += 1
        assert valuta_lettura.confronta(lett, voce["atteso"]) == [], voce
    assert compatti >= 7


def test_valutazione_senza_chiave_esce_senza_errore(monkeypatch, capsys):
    import valuta_lettura
    monkeypatch.setattr(valuta_lettura, "trova_chiave", lambda: None)
    assert valuta_lettura.main([]) == 0
    assert "Manca la chiave" in capsys.readouterr().out
