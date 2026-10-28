from ristorante.orari_liberi import durata, risolvi, verifica, valuta_con_uscita_anticipata
from ristorante.piantina import Piantina
from confronto_orari_liberi import confronta


def p(id, coperti, ora):
    return {"id": id, "coperti": coperti, "orario": ora}


def test_durate_e_riutilizzo_senza_riapparecchiatura():
    pia = Piantina({"tavoli": [{"id": "1", "tipo": "quadrato", "posti": 4}]})
    assert [durata(c) for c in (1, 2, 3, 4, 5, 20)] == [90, 90, 90, 90, 90, 90]
    a = p("a", 2, "20:45")
    assert risolvi(pia, [a, p("b", 2, "22:14")]).stato == "non entra"
    assert risolvi(pia, [a, p("b", 2, "22:15")]).stato == "entra"


def test_blocchi_e_tavolo_lungo():
    blocco = Piantina({"tavoli": [{"id": "5", "tipo": "blocco", "posti": 6, "moduli": 2, "separabile": True}]})
    richieste = [p("a", 4, "20:00"), p("b", 4, "20:30")]
    assert risolvi(blocco, richieste).stato == "entra"
    assert verifica(blocco, richieste, {"a": "t5.q0-1", "b": "t5.q1-1"})
    lungo = Piantina({"tavoli": [{"id": "11", "tipo": "lungo", "posti": 20}]})
    assert risolvi(lungo, [p("a", 8, "20:00"), p("b", 8, "20:00")]).stato == "entra"
    assert risolvi(lungo, [p("a", 9, "20:00"), p("b", 1, "20:00")]).stato == "non entra"


def test_piani_inventati_e_fine_servizio():
    pia = Piantina({"tavoli": [{"id": "1", "tipo": "quadrato", "posti": 2}]})
    richieste = [p("a", 2, "21:00")]
    assert verifica(pia, richieste, {"a": "inventato"})
    assert verifica(pia, richieste, {})
    assert verifica(pia, [p("a", 2, "23:00")], {"a": "t1"})


def test_agente_non_puo_fare_accettare_un_piano_non_valido(monkeypatch):
    import confronto_orari_liberi as confronto
    import sys
    from types import SimpleNamespace

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=lambda: object()))
    pia = Piantina({"tavoli": [{"id": "1", "tipo": "quadrato", "posti": 2}]})
    monkeypatch.setattr(confronto, "piano_agente", lambda *args: {"stato": "entra", "piano": {"a": "inesistente"}})
    risultato = confronta(pia, [p("a", 2, "20:45")], "agente", "test")
    assert risultato["accettate"] == 0
    assert risultato["registro"][0]["stato"] == "piano non valido"


def test_rifiuto_agente_confrontato_con_solver(monkeypatch):
    import confronto_orari_liberi as confronto
    import sys
    from types import SimpleNamespace

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=lambda: object()))
    monkeypatch.setattr(confronto, "piano_agente", lambda *args: {"stato": "non entra", "piano": None})
    pia = Piantina({"tavoli": [{"id": "1", "tipo": "quadrato", "posti": 2}]})
    risultato = confronta(pia, [p("a", 2, "20:45")], "agente", "test")
    assert risultato["registro"][0]["stato"] == "rifiuto errato"


def test_proposta_uscita_alle_21_e_verifica_contro_stato_corrente():
    pia = Piantina({"tavoli": [{"id": "1", "tipo": "quadrato", "posti": 4}]})
    accettate = [p("esistente", 4, "21:00")]
    nuova = p("nuova", 4, "20:00")
    proposta = valuta_con_uscita_anticipata(pia, accettate, nuova)
    assert proposta["stato"] == "proposta"
    assert proposta["fine"] == "21:00"
    assert nuova == p("nuova", 4, "20:00")  # nessuna registrazione o modifica
    concordata = proposta["prenotazione_proposta"]
    assert risolvi(pia, accettate + [concordata]).stato == "entra"
    assert risolvi(pia, accettate + [p("nuova", 4, "20:00")]).stato == "non entra"
    assert risolvi(pia, accettate + [p("altra", 4, "20:15"), concordata]).stato == "non entra"


def test_nessuna_uscita_anticipata_se_c_e_un_tavolo_per_90_minuti():
    pia = Piantina({"tavoli": [{"id": "1", "tipo": "quadrato", "posti": 4},
                               {"id": "2", "tipo": "quadrato", "posti": 4}]})
    assert valuta_con_uscita_anticipata(pia, [p("esistente", 4, "21:00")],
                                       p("nuova", 4, "20:00"))["stato"] == "entra"


def test_uscita_anticipata_e_chiusura():
    pia = Piantina({"tavoli": [{"id": "1", "tipo": "quadrato", "posti": 4}]})
    assert valuta_con_uscita_anticipata(pia, [], p("nuova", 4, "23:00"))["fine"] == "24:00"


def test_non_si_propone_se_il_tavolo_e_occupato_fin_dall_inizio():
    pia = Piantina({"tavoli": [{"id": "1", "tipo": "quadrato", "posti": 4}]})
    assert valuta_con_uscita_anticipata(pia, [p("esistente", 4, "19:30")],
                                       p("nuova", 4, "20:00"))["stato"] == "non entra"
