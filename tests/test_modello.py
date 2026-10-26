"""Test del modello su sale piccole (risolte all'ottimo in pochi secondi)."""
from conftest import sala_esempio, sala_piccola, serata

from ristorante.dati import (
    MOTIVO_SALA_PIENA,
    MOTIVO_TROPPO_GRANDE,
    Rettangolo,
    costruisci_istanza,
    decomponi_in_disgiunti,
)
from ristorante.modello import risolvi


def _risolvi_e_verifica(sala, pren, verificatore):
    sol = risolvi(costruisci_istanza(sala, pren))
    esiti = verificatore.verifica(sala, pren, sol)
    falliti = [(e.nome, e.errori) for e in esiti if not e.ok]
    assert not falliti, falliti
    return sol


def test_gruppo_da_10_su_blocco_da_4_moduli(verificatore):
    # 500x300: entrano sia il blocco da 4 (420x180 di ingombro) sia quello da 5 (500x180)
    sala = sala_piccola(larghezza=500, altezza=300, moduli=5)
    pren = serata(("P1", "Rossi", 10, "20:00"))
    sol = _risolvi_e_verifica(sala, pren, verificatore)
    assert sol["solver"]["stato"] == "OPTIMAL"
    assert not sol["non_sistemate"]
    (tav,) = sol["tavoli"]
    assert tav["tipo"] == "moduli" and tav["moduli"] == 4 and tav["capienza"] == 10
    assert sol["assegnazioni"][0]["tavolo"] == tav["id"]
    assert sol["obiettivo_componenti"]["accostamenti"]["costo"] == 15   # 3 moduli oltre il primo x 5


def test_due_prenotazioni_stessa_ora_un_modulo_una_non_sistemata(verificatore):
    # durate standard: 90 min + 15 di riapparecchiatura, lo spostamento massimo (+30) non basta
    sala = sala_piccola(larghezza=300, altezza=300, moduli=1)
    pren = serata(("P1", "Rossi", 2, "20:00"), ("P2", "Bianchi", 2, "20:00"))
    sol = _risolvi_e_verifica(sala, pren, verificatore)
    assert sol["solver"]["stato"] == "OPTIMAL"
    assert len(sol["assegnazioni"]) == 1 and len(sol["non_sistemate"]) == 1
    assert sol["non_sistemate"][0]["motivo"] == MOTIVO_SALA_PIENA
    assert sol["assegnazioni"][0]["spostamento_min"] == 0


def test_due_prenotazioni_stessa_ora_un_modulo_una_spostata(verificatore):
    # pasto di 15 min + 15 di riapparecchiatura: con lo spostamento di +30 entrano entrambe
    sala = sala_piccola(larghezza=300, altezza=300, moduli=1,
                        durate=[{"fino_a_coperti": None, "minuti": 15}])
    pren = serata(("P1", "Rossi", 2, "20:00"), ("P2", "Bianchi", 2, "20:00"))
    sol = _risolvi_e_verifica(sala, pren, verificatore)
    assert sol["solver"]["stato"] == "OPTIMAL"
    assert len(sol["assegnazioni"]) == 2 and not sol["non_sistemate"]
    assert any(r["spostamento_min"] != 0 for r in sol["assegnazioni"])
    assert sol["obiettivo_componenti"]["spostamenti"]["costo"] == 60   # 2 quarti d'ora in tutto x 30
    assert len({r["tavolo"] for r in sol["assegnazioni"]}) == 1


def test_prenotazione_da_14_non_sistemata_con_motivo(verificatore):
    sala = sala_piccola(larghezza=700, altezza=400, moduli=5, tondi=1)
    pren = serata(("P1", "Grande", 14, "20:00"), ("P2", "Piccola", 4, "20:00"))
    ist = costruisci_istanza(sala, pren)
    assert ist.capienza_massima == 12
    sol = _risolvi_e_verifica(sala, pren, verificatore)
    assert [r["id"] for r in sol["non_sistemate"]] == ["P1"]
    assert sol["non_sistemate"][0]["motivo"] == MOTIVO_TROPPO_GRANDE
    assert [r["id"] for r in sol["assegnazioni"]] == ["P2"]


def test_ostacoli_sovrapposti_non_rendono_infattibile(verificatore):
    # nella sala di esempio il pilastro sta dentro la corsia centrale: NoOverlap2D sui rettangoli
    # originali sarebbe infattibile; il modello usa la loro unione scomposta in pezzi disgiunti
    sala = sala_esempio()
    sala["solver"]["tempo_limite_s"] = 10
    pren = serata(("P1", "Rossi", 2, "20:00"))
    sol = _risolvi_e_verifica(sala, pren, verificatore)
    assert sol["solver"]["stato"] == "OPTIMAL" and len(sol["assegnazioni"]) == 1


def test_scomposizione_fissi_disgiunta_e_uguale_all_unione():
    fissi = [Rettangolo("a", 0, 0, 10, 4), Rettangolo("b", 3, 2, 6, 8), Rettangolo("c", 4, 3, 5, 5)]
    pezzi = decomponi_in_disgiunti(12, 10, fissi)
    celle_unione = {(x, y) for r in fissi for x in range(r.x0, r.x1) for y in range(r.y0, r.y1)}
    celle_pezzi = [(x, y) for r in pezzi for x in range(r.x0, r.x1) for y in range(r.y0, r.y1)]
    assert len(celle_pezzi) == len(set(celle_pezzi))          # disgiunti
    assert set(celle_pezzi) == celle_unione                    # stessa copertura
