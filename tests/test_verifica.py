"""Test del verificatore su soluzioni scritte a mano (nessun uso del solver): un controllo positivo
e difetti iniettati che devono essere segnalati."""
import copy
import json
import subprocess
import sys

from conftest import RADICE, esiti_per_nome, sala_piccola, serata

SOVRAPPOSIZIONE = "nessuna sovrapposizione sullo stesso tavolo (con riapparecchiatura)"
DENTRO_SALA = "ingombri (tavolo + sedie) dentro la sala"


def _caso_valido():
    sala = sala_piccola(larghezza=600, altezza=400, moduli=5, tondi=1)
    pren = serata(("P1", "Rossi", 2, "19:30"), ("P2", "Bianchi", 6, "20:00"), ("P3", "Verdi", 2, "21:00"))
    sol = {
        "solver": {"stato": "OPTIMAL", "obiettivo": 40},
        "tavoli": [
            {"id": "T1", "tipo": "moduli", "moduli": 1, "orientamento": "orizzontale", "x_cm": 50, "y_cm": 50,
             "larghezza_cm": 80, "altezza_cm": 80, "capienza": 4},
            {"id": "T2", "tipo": "tondo", "moduli": 0, "orientamento": None, "x_cm": 300, "y_cm": 50,
             "larghezza_cm": 120, "altezza_cm": 120, "capienza": 6},
        ],
        "assegnazioni": [
            {"id": "P1", "nome": "Rossi", "coperti": 2, "orario_richiesto": "19:30", "orario_assegnato": "19:30",
             "spostamento_min": 0, "fine": "21:00", "tavolo": "T1"},
            {"id": "P2", "nome": "Bianchi", "coperti": 6, "orario_richiesto": "20:00", "orario_assegnato": "20:00",
             "spostamento_min": 0, "fine": "22:00", "tavolo": "T2"},
            # 21:15 = fine di Rossi (21:00) + 15 min di riapparecchiatura: ammesso
            {"id": "P3", "nome": "Verdi", "coperti": 2, "orario_richiesto": "21:00", "orario_assegnato": "21:15",
             "spostamento_min": 15, "fine": "22:45", "tavolo": "T1"},
        ],
        "non_sistemate": [],
        "obiettivo_componenti": {
            "non_sistemate": {"costo": 0}, "posti_vuoti": {"costo": 40}, "spostamenti": {"costo": 30},
            "accostamenti": {"costo": 0}, "picco_cucina": {"costo": 0}, "totale": 70,
        },
    }
    sol["solver"]["obiettivo"] = 70
    return sala, pren, sol


def test_controllo_positivo_tutto_pass(verificatore):
    sala, pren, sol = _caso_valido()
    esiti = verificatore.verifica(sala, pren, sol)
    assert all(e.ok for e in esiti), [(e.nome, e.errori) for e in esiti if not e.ok]


def test_segnala_sovrapposizione_temporale_iniettata(verificatore):
    sala, pren, sol = _caso_valido()
    # Verdi anticipato alle 21:00 sullo stesso tavolo: Rossi finisce alle 21:00 ma serve la riapparecchiatura
    r = sol["assegnazioni"][2]
    r.update(orario_assegnato="21:00", spostamento_min=0, fine="22:30")
    sol["obiettivo_componenti"]["spostamenti"]["costo"] = 0
    sol["obiettivo_componenti"]["totale"] = sol["solver"]["obiettivo"] = 40
    esiti = esiti_per_nome(verificatore.verifica(sala, pren, sol))
    assert not esiti[SOVRAPPOSIZIONE].ok
    assert "P1" in esiti[SOVRAPPOSIZIONE].errori[0] and "P3" in esiti[SOVRAPPOSIZIONE].errori[0]
    altri_falliti = [n for n, e in esiti.items() if not e.ok and n != SOVRAPPOSIZIONE]
    assert not altri_falliti, altri_falliti


def test_segnala_tavolo_fuori_sala_iniettato(verificatore):
    sala, pren, sol = _caso_valido()
    sol["tavoli"][1]["x_cm"] = 450          # ingombro 400..620 in una sala larga 600
    esiti = esiti_per_nome(verificatore.verifica(sala, pren, sol))
    assert not esiti[DENTRO_SALA].ok
    assert "T2" in esiti[DENTRO_SALA].errori[0]
    altri_falliti = [n for n, e in esiti.items() if not e.ok and n != DENTRO_SALA]
    assert not altri_falliti, altri_falliti


def test_segnala_prenotazione_mancante_e_capienza(verificatore):
    sala, pren, sol = _caso_valido()
    sol2 = copy.deepcopy(sol)
    sol2["assegnazioni"][0]["coperti"] = 6          # dato alterato: 6 coperti su un tavolo da 4
    del sol2["assegnazioni"][2]                     # Verdi sparisce
    esiti = esiti_per_nome(verificatore.verifica(sala, pren, sol2))
    assert not esiti["ogni prenotazione presente esattamente una volta"].ok
    assert not esiti["capienza >= coperti"].ok


def test_cli_exit_code_1_su_fail(tmp_path):
    sala, pren, sol = _caso_valido()
    sol["tavoli"][1]["x_cm"] = 450
    for nome, dati in (("sala.json", sala), ("pren.json", pren), ("sol.json", sol)):
        (tmp_path / nome).write_text(json.dumps(dati), encoding="utf-8")
    esito = subprocess.run([sys.executable, str(RADICE / "verifica.py"), "--sala", str(tmp_path / "sala.json"),
                            "--prenotazioni", str(tmp_path / "pren.json"), "--soluzione", str(tmp_path / "sol.json")],
                           capture_output=True, text=True, encoding="utf-8")
    assert esito.returncode == 1
    assert "FAIL  " + DENTRO_SALA in esito.stdout
    assert "ESITO: FAIL" in esito.stdout


def test_verificatore_non_importa_il_modello():
    testo = (RADICE / "verifica.py").read_text(encoding="utf-8")
    assert "ristorante" not in [riga.split()[1].split(".")[0] for riga in testo.splitlines()
                                if riga.startswith(("import ", "from "))]


# --------------------------------------------------------------------------- piantina variabile e registro

SPAZIO_TEMPO = "ingombri disgiunti tra loro nello spazio-tempo"
INVENTARIO = "inventario in ogni istante (moduli e tondi in uso)"
ESISTENZA = "prenotazioni dentro l'esistenza del loro tavolo"
ORDINE = "registro in ordine di prenotazione"
PROMESSI = "orari finali uguali a quelli promessi nel registro"


def _caso_variabile(moduli=2):
    """Due singoli alle 19:00, smontati alle 20:45; alle 21:30 un blocco da 2 moduli nello stesso spazio."""
    sala = sala_piccola(larghezza=600, altezza=400, moduli=moduli, tondi=0)
    pren = {"serata": "prova", "prenotazioni": [
        {"id": "P1", "nome": "Rossi", "coperti": 2, "orario": "19:00", "prenotata_il": "2026-10-20T10:00"},
        {"id": "P2", "nome": "Bianchi", "coperti": 2, "orario": "19:00", "prenotata_il": "2026-10-20T11:00"},
        {"id": "P3", "nome": "Verdi", "coperti": 6, "orario": "21:30", "prenotata_il": "2026-10-21T09:00"}]}

    def tav(tid, k, x, y, dal, al):
        return {"id": tid, "tipo": "moduli", "moduli": k, "orientamento": "orizzontale", "x_cm": x, "y_cm": y,
                "larghezza_cm": 80 * k, "altezza_cm": 80, "capienza": 2 * k + 2,
                "esiste_dal": dal, "esiste_al": al, "montato_in_servizio": dal != "19:00"}

    sol = {
        "modalita": {"accettazione": "ordine_di_arrivo", "disposizione": "variabile"},
        "solver": {"stato": "OPTIMAL", "obiettivo": 65},
        "tavoli": [tav("T1", 1, 50, 50, "19:00", "20:45"), tav("T2", 1, 230, 50, "19:00", "20:45"),
                   tav("T3", 2, 50, 50, "21:30", "24:15")],
        "assegnazioni": [
            {"id": "P1", "nome": "Rossi", "coperti": 2, "orario_richiesto": "19:00", "orario_assegnato": "19:00",
             "spostamento_min": 0, "fine": "20:30", "tavolo": "T1"},
            {"id": "P2", "nome": "Bianchi", "coperti": 2, "orario_richiesto": "19:00", "orario_assegnato": "19:00",
             "spostamento_min": 0, "fine": "20:30", "tavolo": "T2"},
            {"id": "P3", "nome": "Verdi", "coperti": 6, "orario_richiesto": "21:30", "orario_assegnato": "21:30",
             "spostamento_min": 0, "fine": "23:30", "tavolo": "T3"}],
        "non_sistemate": [],
        "registro": [
            {"ordine": i + 1, "id": pid, "nome": nome, "coperti": c, "orario_richiesto": o, "prenotata_il": ric,
             "esito": "accettata", "orario_promesso": o, "spostamento_min": 0, "motivo": None}
            for i, (pid, nome, c, o, ric) in enumerate([("P1", "Rossi", 2, "19:00", "2026-10-20T10:00"),
                                                         ("P2", "Bianchi", 2, "19:00", "2026-10-20T11:00"),
                                                         ("P3", "Verdi", 6, "21:30", "2026-10-21T09:00")])],
        "obiettivo_componenti": {
            "non_sistemate": {"costo": 0}, "posti_vuoti": {"costo": 40}, "spostamenti": {"costo": 0},
            "accostamenti": {"costo": 5}, "picco_cucina": {"costo": 0}, "riallestimenti": {"costo": 20},
            "totale": 65},
    }
    return sala, pren, sol


def _falliti(verificatore, sala, pren, sol):
    return {e.nome for e in verificatore.verifica(sala, pren, sol) if not e.ok}


def test_variabile_stesso_spazio_in_momenti_diversi_pass(verificatore):
    sala, pren, sol = _caso_variabile()
    assert _falliti(verificatore, sala, pren, sol) == set()


def test_segnala_tavoli_sovrapposti_nello_spazio_e_nel_tempo(verificatore):
    sala, pren, sol = _caso_variabile(moduli=4)        # inventario largo: fallisce solo lo spazio-tempo
    sol["tavoli"][2]["esiste_dal"] = "20:30"           # T3 montato mentre T1 e T2 sono ancora lì
    assert _falliti(verificatore, sala, pren, sol) == {SPAZIO_TEMPO}


def test_segnala_moduli_oltre_l_inventario_in_un_istante(verificatore):
    sala, pren, sol = _caso_variabile(moduli=2)
    t3 = sol["tavoli"][2]
    t3.update(y_cm=250, esiste_dal="20:00")            # spazio libero, ma alle 20:00 servono 1 + 1 + 2 = 4 moduli
    assert _falliti(verificatore, sala, pren, sol) == {INVENTARIO}


def test_segnala_prenotazione_fuori_dall_esistenza_del_tavolo(verificatore):
    sala, pren, sol = _caso_variabile()
    sol["tavoli"][0]["esiste_al"] = "20:30"            # manca la riapparecchiatura prima di smontare
    assert _falliti(verificatore, sala, pren, sol) == {ESISTENZA}


def test_segnala_registro_fuori_ordine_e_orario_non_mantenuto(verificatore):
    sala, pren, sol = _caso_variabile()
    sol["registro"][0], sol["registro"][1] = sol["registro"][1], sol["registro"][0]
    assert _falliti(verificatore, sala, pren, sol) == {ORDINE}
    sala, pren, sol = _caso_variabile()
    sol["registro"][2]["orario_promesso"] = "21:45"    # promesso 21:45, seduto 21:30
    assert _falliti(verificatore, sala, pren, sol) == {PROMESSI}


def test_fissa_dichiarata_ma_tavolo_parziale(verificatore):
    sala, pren, sol = _caso_variabile(moduli=4)
    sol["modalita"]["disposizione"] = "fissa"
    assert "esistenza dei tavoli (griglia, servizio, disposizione)" in _falliti(verificatore, sala, pren, sol)
