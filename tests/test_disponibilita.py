"""Tabella delle disponibilità: stesse risposte del calcolo diretto, mai una tabella vecchia, risposte parziali che
non dichiarano "pieno" ciò che non è dimostrato, domanda sul nome già presente, stato coerente sotto raffica."""
import json
import random
import threading
from datetime import date, datetime, timedelta

import pytest
from conftest import sala_piccola

from ristorante import conversazione
from ristorante.conversazione import _Conversazione, gestisci_messaggio
from ristorante.disponibilita import ENTRA, CalcolatoreLocale, Disponibilita, classi_coperti, istanza
from ristorante.serate import Archivio, serata_vuota

MARTEDI = datetime(2026, 10, 27, 10, 0)
SAB = date(2026, 10, 31)


class SenzaLLM:
    disponibile = False


@pytest.fixture(autouse=True)
def senza_disponibilita_globale():
    yield
    conversazione.ferma_disponibilita()


def _stato_casuale(rnd, sala, tmp_path, n):
    """Stato ammissibile: prenotazioni casuali aggiunte solo se entrano all'orario chiesto (calcolo diretto)."""
    arch = Archivio(tmp_path)
    stato = serata_vuota(SAB)
    conv = _Conversazione(arch, sala, SenzaLLM(), MARTEDI, "x")
    for i in range(n):
        c = rnd.choice([2, 2, 3, 4, 4, 5, 6, 8])
        o = rnd.choice(["19:00", "19:30", "20:00", "20:15", "20:30", "21:00", "21:30", "22:00"])
        if conv._valuta_diretta(stato, c, o).esito == "entra":
            stato["accettate"].append({"id": f"A{i}", "nome": f"N{i}", "coperti": c, "orario": o})
    stato["versione"] = rnd.randint(1, 1000)
    arch.salva(stato)
    return stato, conv


def test_classi_di_coperti_equivalenti_nella_sala_di_esempio():
    from conftest import sala_esempio
    ist, _, _ = istanza(sala_esempio(), "2026-10-31", [], 2, "20:00")
    assert [k.nome for k in classi_coperti(ist)] == ["1-2", "3-4", "5-6", "7-8", "9-10", "11-12"]


def test_tabella_uguale_al_calcolo_diretto_su_30_casi(tmp_path):
    rnd = random.Random(5)
    sala = sala_piccola(600, 400, moduli=4, tondi=1)
    casi = 0
    for prova in range(5):
        cartella = tmp_path / f"s{prova}"
        stato, conv = _stato_casuale(rnd, sala, cartella, rnd.randint(4, 8))
        disp = Disponibilita(cartella, sala, CalcolatoreLocale(cartella), cartella_geometria=tmp_path / "geo")
        disp.aggiorna(stato)
        assert disp.tabella_pronta(SAB)
        for _ in range(6):
            c = rnd.choice([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
            o = rnd.choice(["19:00", "19:15", "19:45", "20:00", "20:30", "21:00", "21:15", "21:45", "22:15"])
            dalla_tabella = disp.valuta(stato, c, o)
            diretto = conv._valuta_diretta(stato, c, o)
            assert dalla_tabella.dettaglio == "tabella"
            assert (dalla_tabella.esito, dalla_tabella.opzioni) == (diretto.esito, diretto.opzioni), (stato, c, o)
            casi += 1
    assert casi == 30


def test_una_tabella_vecchia_non_viene_mai_usata(tmp_path):
    sala = sala_piccola(300, 300, moduli=1)
    arch = Archivio(tmp_path)
    stato = serata_vuota(SAB) | {"versione": 1}
    arch.salva(stato)
    disp = Disponibilita(tmp_path, sala, CalcolatoreLocale(tmp_path), cartella_geometria=tmp_path / "geo")
    disp.aggiorna(stato)
    assert disp.valuta(stato, 2, "20:00").esito == "entra"          # tabella della versione 1: sala vuota
    # lo stato cambia (versione 2: il tavolo è occupato alle 20:00) ma la tabella non è stata ricalcolata
    stato["accettate"].append({"id": "A", "nome": "Rossi", "coperti": 2, "orario": "20:00"})
    stato["versione"] = 2
    arch.salva(stato)
    v = disp.valuta(stato, 2, "20:00")
    assert v.esito != "entra" and v.tabella_pronta is False and v.dettaglio != "tabella"
    assert not disp.tabella_pronta(SAB)


def test_i_processi_fermano_subito_i_calcoli_di_una_versione_superata(tmp_path):
    """Quattro dimostrazioni da qualche secondo l'una in coda a un solo processo: appena lo stato cambia versione,
    quella in corso si interrompe e le altre non partono (versione in memoria condivisa, nessun file letto)."""
    import time
    import misura_chat
    from conftest import sala_esempio
    from ristorante.disponibilita import Calcolatore
    misura_chat.stato_iniziale(tmp_path)
    acc = [a for a in Archivio(tmp_path).carica(SAB)["accettate"] if a["nome"] != "Rizzo"] + [
        {"id": "G", "nome": "Gallo", "coperti": 5, "orario": "20:00"},
        {"id": "N", "nome": "Neri", "coperti": 4, "orario": "21:30"}]
    calc = Calcolatore(tmp_path, 1, 1)
    arrivati, tutti = [], threading.Event()

    def arrivato(r):
        arrivati.append(r)
        if len(arrivati) == 4:
            tutti.set()

    try:
        assert calc.attendi_avvio(120)
        for orario in ("21:45", "21:30", "22:00", "20:15"):     # "non entra" dimostrato dal solver in 2-5 s ciascuna
            calc.invia({"sala": sala_esempio(), "data": "2026-10-31", "versione": 0, "accettate": acc, "coperti": 2,
                        "orario": orario, "spostamento": 0, "disposizione": "fissa", "tempo_s": 60}, arrivato)
        time.sleep(0.5)
        t0 = time.monotonic()
        calc.imposta_versione("2026-10-31", 1)
        assert tutti.wait(10)
        assert time.monotonic() - t0 < 3
        assert sum(r["esito"] == "superata" for r in arrivati) >= 3
    finally:
        calc.chiudi()


class CalcolatoreFinto:
    """Le verifiche non finiscono finché il test non lo decide (simula un calcolo lungo in background)."""

    def __init__(self, entra_subito=()):
        self.in_attesa, self.entra_subito = [], set(entra_subito)

    def attendi_avvio(self, timeout=0):
        return True

    def invia(self, task, callback, urgente=False):
        if task.get("tipo") == "geometria":
            return None
        orario = conversazione.min_a_hhmm(conversazione.hhmm_a_min(task["orario"]) + task["spostamento"])
        if orario in self.entra_subito:
            callback({"id": "x", "esito": ENTRA, "come": "solver", "piano": None})
        else:
            self.in_attesa.append((orario, callback))

    def completa(self, orario, esito):
        for o, cb in self.in_attesa:
            if o == orario:
                cb({"id": "x", "esito": esito, "come": "solver", "piano": None})

    def annulla_urgenti_fino_a(self, token):
        pass

    def chiudi(self):
        pass


def _con_disponibilita_finta(tmp_path, sala, calc):
    disp = Disponibilita(tmp_path, sala, calc, attesa_max_s=0.3, cartella_geometria=tmp_path / "geo")
    disp.geo_pronta.set()
    conversazione._DISP = disp
    return disp


def test_risposta_parziale_non_dichiara_pieno_e_poi_aggiorna(tmp_path):
    sala = sala_piccola(400, 300, moduli=2)
    arch = Archivio(tmp_path)
    arch.salva(serata_vuota(SAB) | {"accettate": [{"id": "A", "nome": "Rossi", "coperti": 2, "orario": "20:30",
                                                   "note": ""}], "versione": 3})
    calc = CalcolatoreFinto(entra_subito={"21:15"})
    _con_disponibilita_finta(tmp_path, sala, calc)
    r = gestisci_messaggio("Bianchi 2 sab 20:30", MARTEDI, "p", tmp_path, sala=sala, lettore=SenzaLLM())
    assert r == "Bianchi · 2 persone · sab 31/10: alle 20:30 sto ancora verificando; di sicuro posso alle 21:15. Quale?"
    assert "pieno" not in r
    assert [a["nome"] for a in arch.carica(SAB)["accettate"]] == ["Rossi"]      # niente registrato
    calc.completa("20:30", ENTRA)                                               # la verifica finisce in background
    r2 = gestisci_messaggio("riepilogo sab", MARTEDI + timedelta(minutes=1), "p", tmp_path, sala=sala, lettore=SenzaLLM())
    assert r2.startswith("Aggiornamento: Bianchi · 2 persone · sab 31/10, alle 20:30 c'è posto")
    calc2 = CalcolatoreFinto()
    _con_disponibilita_finta(tmp_path / "b", sala, calc2)
    Archivio(tmp_path / "b").salva(serata_vuota(SAB) | {"versione": 1, "accettate": [
        {"id": "A", "nome": "Rossi", "coperti": 2, "orario": "20:30", "note": ""}]})
    r3 = gestisci_messaggio("Verdi 2 sab 20:30", MARTEDI, "p", tmp_path / "b", sala=sala, lettore=SenzaLLM())
    assert r3 == "Verdi · 2 persone · sab 31/10: alle 20:30 sto ancora verificando, ti scrivo appena so. Non ho registrato niente."


def test_nome_gia_presente_altra_oppure_sposta(tmp_path):
    sala = sala_piccola(400, 300, moduli=2)

    def invia(t, minuti=0):
        return gestisci_messaggio(t, MARTEDI + timedelta(minutes=minuti), "p", tmp_path, sala=sala, lettore=SenzaLLM())

    assert invia("Rossi 4 sab 20:30") == "✓ Rossi · 4 persone · sab 31/10 · 20:30"
    assert invia("Rossi 4 sab 21:00", 1) == ("C'è già Rossi alle 20:30 per 4 persone (sab 31/10): è un'altra "
                                             "prenotazione o la sposto alle 21:00?")
    assert invia("sposta", 2) == "✓ Modificata Rossi · 4 persone · sab 31/10 · 21:00 (prima 4 persone alle 20:30)"
    assert invia("Rossi 2 sab 19:00", 3).startswith("C'è già Rossi alle 21:00 per 4 persone")
    assert invia("è un'altra", 4) == "✓ Rossi · 2 persone · sab 31/10 · 19:00"
    acc = sorted((a["orario"], a["coperti"]) for a in Archivio(tmp_path).carica(SAB)["accettate"])
    assert acc == [("19:00", 2), ("21:00", 4)]


def test_stato_coerente_con_richieste_ravvicinate_mentre_la_tabella_si_ricalcola(tmp_path):
    sala = sala_piccola(600, 400, moduli=4, tondi=1)
    sala["chat"]["tempo_cella_s"] = 10
    disp = conversazione.avvia_disponibilita(tmp_path, sala, processi=2, worker=1, cartella_geometria=tmp_path / "geo")
    messaggi = [f"N{i} {c} sab {o}" for i, (c, o) in enumerate(
        [(2, "19:00"), (4, "19:30"), (2, "20:00"), (5, "20:00"), (2, "20:30"), (4, "21:00"), (2, "21:30"),
         (2, "22:00"), (3, "19:15"), (2, "21:45")])]
    risposte, errori = [], []

    def manda(i, testo):
        try:
            risposte.append(gestisci_messaggio(testo, MARTEDI + timedelta(seconds=i), f"m{i}", tmp_path, sala=sala,
                                               lettore=SenzaLLM()))
        except Exception as e:  # noqa: BLE001
            errori.append(e)

    fili = [threading.Thread(target=manda, args=(i, m)) for i, m in enumerate(messaggi)]
    for f in fili:
        f.start()
    for f in fili:
        f.join(120)
    assert not errori and len(risposte) == len(messaggi)
    stato = json.loads((tmp_path / "2026-10-31.json").read_text(encoding="utf-8"))
    registrate = sum(r.startswith("✓") for r in risposte)
    assert len(stato["accettate"]) == registrate and stato["versione"] == registrate
    assert (tmp_path / "2026-10-31.versione").read_text() == str(registrate)
    # le accettate stanno insieme davvero: la piantina della serata esiste ed è verificata
    sol, p_pren, p_sol = conversazione.piantina_serata(tmp_path, SAB, sala, out=tmp_path / "piantina", tempo_s=30)
    assert len(sol["assegnazioni"]) == registrate
    import verifica
    esiti = verifica.verifica(sala, json.loads(p_pren.read_text(encoding="utf-8")), sol)
    assert all(e.ok for e in esiti), [(e.nome, e.errori) for e in esiti if not e.ok]
    # la tabella finale è quella della versione corrente e dà le stesse risposte del calcolo diretto
    ok, _ = disp.attendi_tabella(SAB, timeout=120)
    assert ok and disp.tabelle["2026-10-31"].versione == stato["versione"]
    conv = _Conversazione(Archivio(tmp_path), sala, SenzaLLM(), MARTEDI, "x")
    for c, o in ((2, "20:00"), (4, "21:00"), (6, "19:30")):
        a, b = disp.valuta(stato, c, o), conv._valuta_diretta(stato, c, o)
        assert (a.esito, a.opzioni) == (b.esito, b.opzioni)
