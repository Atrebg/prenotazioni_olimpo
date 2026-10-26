"""Accettazione in ordine di arrivo e piantina variabile, su sale piccole (pochi secondi)."""
from conftest import sala_piccola

from ristorante.dati import MOTIVO_SALA_PIENA_ACCETTATE, MOTIVO_TEMPO_SCADUTO, costruisci_istanza
from ristorante.modello import accetta_in_ordine, risolvi


def _pren(*righe):
    """righe: (id, nome, coperti, "HH:MM", "prenotata_il")."""
    return {"serata": "prova", "prenotazioni": [
        {"id": r[0], "nome": r[1], "coperti": r[2], "orario": r[3], "prenotata_il": r[4]} for r in righe]}


def _accetta(sala, pren, verificatore, disposizione="fissa"):
    sol = accetta_in_ordine(costruisci_istanza(sala, pren), disposizione=disposizione,
                            tempo_decisione_s=20, tempo_piantina_s=20)
    esiti = verificatore.verifica(sala, pren, sol)
    falliti = [(e.nome, e.errori) for e in esiti if not e.ok]
    assert not falliti, falliti
    return sol


def test_vince_chi_prenota_prima_anche_se_l_altra_e_piu_grande(verificatore):
    sala = sala_piccola(larghezza=300, altezza=300, moduli=1)
    pren = _pren(("A", "Coppia", 2, "20:00", "2026-10-20T10:00"),
                 ("B", "Famiglia", 4, "20:00", "2026-10-21T10:00"))
    # l'ottimizzazione "tutte insieme" preferirebbe la più grande (nessun posto vuoto)
    batch = risolvi(costruisci_istanza(sala, pren))
    assert [r["id"] for r in batch["assegnazioni"]] == ["B"]
    sol = _accetta(sala, pren, verificatore)
    assert [r["id"] for r in sol["assegnazioni"]] == ["A"]
    assert sol["non_sistemate"][0]["id"] == "B"
    assert sol["non_sistemate"][0]["motivo"] == MOTIVO_SALA_PIENA_ACCETTATE
    assert sol["registro"][1]["decisione"] == "impossibile (dimostrato)"


def test_vince_chi_prenota_prima_anche_se_l_altra_ha_l_orario_piu_comodo(verificatore):
    # B alle 19:00 lascerebbe spazio anche a C alle 21:00 (l'ottimizzazione unica siede B e C);
    # A ha prenotato per primo alle 20:30 e resta dentro, B e C vengono rifiutate
    sala = sala_piccola(larghezza=300, altezza=300, moduli=1)
    pren = _pren(("A", "Primo", 2, "20:30", "2026-10-20T10:00"),
                 ("B", "Comodo", 2, "19:00", "2026-10-21T10:00"),
                 ("C", "Tardi", 2, "21:00", "2026-10-22T10:00"))
    batch = risolvi(costruisci_istanza(sala, pren))
    assert sorted(r["id"] for r in batch["assegnazioni"]) == ["B", "C"]
    sol = _accetta(sala, pren, verificatore)
    assert [r["id"] for r in sol["assegnazioni"]] == ["A"]
    assert sol["assegnazioni"][0]["orario_assegnato"] == "20:30"      # spostamento minimo: nessuno
    assert {r["id"]: r["motivo"] for r in sol["non_sistemate"]} == {
        "B": MOTIVO_SALA_PIENA_ACCETTATE, "C": MOTIVO_SALA_PIENA_ACCETTATE}


def test_spostamento_minimo_e_orario_congelato(verificatore):
    # un solo modulo: A alle 20:00 occupa il tavolo fino alle 21:30 + 15 di riapparecchiatura; C chiede le 21:30:
    # 0 e -15 sono impossibili, +15 (21:45) è il minimo e diventa l'orario promesso, che la piantina rispetta
    sala = sala_piccola(larghezza=300, altezza=300, moduli=1)
    pren = _pren(("A", "Primo", 2, "20:00", "2026-10-20T10:00"),
                 ("C", "Dopo", 2, "21:30", "2026-10-21T10:00"))
    sol = _accetta(sala, pren, verificatore)
    promessi = {r["id"]: r["orario_promesso"] for r in sol["registro"]}
    assert promessi == {"A": "20:00", "C": "21:45"}
    assert all(r["spostamento_minimo_dimostrato"] for r in sol["registro"])
    assert sol["registro"][1]["stato_solver"].split(" · ")[0] in ("0′ INFEASIBLE", "0′ CONTEGGIO")
    assert {r["id"]: r["orario_assegnato"] for r in sol["assegnazioni"]} == promessi


def test_sala_da_due_moduli_variabile_entra_fissa_no(verificatore):
    # 360x180: ci stanno due tavoli singoli affiancati oppure un blocco da 2 moduli, non entrambi
    sala = sala_piccola(larghezza=360, altezza=180, moduli=2, tondi=0)
    pren = _pren(("A", "Uno", 2, "19:00", "2026-10-20T10:00"),
                 ("B", "Due", 2, "19:00", "2026-10-20T11:00"),
                 ("C", "Gruppo", 6, "21:30", "2026-10-20T12:00"))
    fissa = _accetta(sala, pren, verificatore, "fissa")
    assert [r["id"] for r in fissa["non_sistemate"]] == ["C"]
    assert fissa["non_sistemate"][0]["motivo"] == MOTIVO_SALA_PIENA_ACCETTATE
    variabile = _accetta(sala, pren, verificatore, "variabile")
    assert not variabile["non_sistemate"]
    tav_c = next(t for t in variabile["tavoli"]
                 if t["id"] == next(r["tavolo"] for r in variabile["assegnazioni"] if r["id"] == "C"))
    assert tav_c["moduli"] == 2 and tav_c["montato_in_servizio"] and tav_c["esiste_dal"] == "21:30"
    assert variabile["obiettivo_componenti"]["riallestimenti"] == {"numero": 1, "costo": 20}


def test_tempo_scaduto_rifiuta_con_motivo_e_conta_a_parte(verificatore):
    # limite di tempo nullo: il solver non risponde (UNKNOWN) e la prenotazione è rifiutata, mai in silenzio
    sala = sala_piccola(larghezza=600, altezza=400, moduli=4, tondi=1)
    pren = _pren(("A", "Uno", 2, "19:00", "2026-10-20T10:00"), ("B", "Due", 4, "20:00", "2026-10-20T11:00"))
    sol = accetta_in_ordine(costruisci_istanza(sala, pren), tempo_decisione_s=0.0, tempo_piantina_s=5)
    assert sol["accettazione"]["decisioni_unknown"] == 2
    assert all(r["motivo"] == MOTIVO_TEMPO_SCADUTO for r in sol["non_sistemate"])
    assert all(r["decisione"] == "non decisa (tempo scaduto)" for r in sol["registro"])
    esiti = verificatore.verifica(sala, pren, sol)
    assert all(e.ok for e in esiti), [(e.nome, e.errori) for e in esiti if not e.ok]


def test_disposizione_fissa_e_variabile_stesso_ottimo_se_non_serve_cambiare(verificatore):
    # una sola prenotazione: in "variabile" nessun riallestimento conviene, stesso obiettivo della "fissa"
    sala = sala_piccola(larghezza=500, altezza=300, moduli=5)
    pren = _pren(("A", "Rossi", 10, "20:00", "2026-10-20T10:00"))
    f = _accetta(sala, pren, verificatore, "fissa")
    v = _accetta(sala, pren, verificatore, "variabile")
    assert f["obiettivo_componenti"]["totale"] == v["obiettivo_componenti"]["totale"] == 15
    assert v["tavoli"][0]["esiste_dal"] == "19:00"


def test_verificatore_distingue_rifiuti_per_inventario_da_quelli_per_spazio(verificatore):
    # inventario: un solo modulo e due coppie alla stessa ora -> il rifiuto è dimostrabile contando i moduli
    sala = sala_piccola(larghezza=300, altezza=300, moduli=1)
    pren = _pren(("A", "Coppia", 2, "20:00", "2026-10-20T10:00"), ("B", "Altra", 2, "20:00", "2026-10-21T10:00"))
    sol = _accetta(sala, pren, verificatore)
    assert verificatore.rifiuti_inevitabili_per_inventario(sala, pren, sol) == (["B"], 1)
    # spazio: con "fissa" il gruppo resta fuori perché i due singoli occupano lo spazio tutta la sera,
    # ma i moduli basterebbero: il conteggio non lo dimostra (e infatti con "variabile" entra)
    sala = sala_piccola(larghezza=360, altezza=180, moduli=2, tondi=0)
    pren = _pren(("A", "Uno", 2, "19:00", "2026-10-20T10:00"), ("B", "Due", 2, "19:00", "2026-10-20T11:00"),
                 ("C", "Gruppo", 6, "21:30", "2026-10-20T12:00"))
    sol = _accetta(sala, pren, verificatore, "fissa")
    assert verificatore.rifiuti_inevitabili_per_inventario(sala, pren, sol) == ([], 1)
