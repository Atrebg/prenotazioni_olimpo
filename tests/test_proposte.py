"""Proposta dell'orario libero più vicino (accettazione in ordine di arrivo) e comando prova.py."""
import json
import subprocess
import sys

from conftest import RADICE, sala_piccola

from ristorante.dati import MOTIVO_PROPOSTA_RIFIUTATA, MOTIVO_SALA_PIENA_ACCETTATE, costruisci_istanza
from ristorante.modello import accetta_in_ordine

PROPOSTE = "proposte entro la distanza massima e fuori dagli spostamenti ammessi"


def _pren(*righe):
    return {"serata": "Sabato di prova", "prenotazioni": [
        {"id": r[0], "nome": r[1], "coperti": r[2], "orario": r[3], "prenotata_il": r[4]} for r in righe]}


def _accetta(sala, pren, verificatore):
    sol = accetta_in_ordine(costruisci_istanza(sala, pren), tempo_decisione_s=20, tempo_piantina_s=20,
                            tempo_proposta_s=20)
    falliti = [(e.nome, e.errori) for e in verificatore.verifica(sala, pren, sol) if not e.ok]
    assert not falliti, falliti
    return sol


# un solo modulo: A (prenotata prima) occupa il tavolo dalle 21:00; B chiede le 20:15 (90 min + 15).
# Negli spostamenti ammessi (20:00-20:45) non entra; alle 19:15 (60 min prima) sì; dopo nessun orario entro le 24:00.
PUNTA = _pren(("A", "Primo", 2, "21:00", "2026-10-20T10:00"), ("B", "Dopo", 2, "20:15", "2026-10-21T10:00"))


def test_ora_di_punta_piena_proposta_60_minuti_prima(verificatore):
    sol = _accetta(sala_piccola(300, 300, moduli=1, proposta="sempre"), PUNTA, verificatore)
    b = sol["registro"][1]
    assert (b["esito"], b["proposta_prima"], b["proposta_dopo"], b["orario_promesso"]) == \
        ("accettata su proposta", "19:15", None, "19:15")
    # l'orario proposto si congela: la piantina finale lo rispetta
    assert {r["id"]: r["orario_assegnato"] for r in sol["assegnazioni"]} == {"A": "21:00", "B": "19:15"}


def test_politica_mai_rifiuta_e_entro_n_rifiuta_se_troppo_lontana(verificatore):
    mai = _accetta(sala_piccola(300, 300, moduli=1, proposta="mai"), PUNTA, verificatore)
    assert mai["non_sistemate"][0]["motivo"] == MOTIVO_SALA_PIENA_ACCETTATE
    assert mai["registro"][1]["proposta_prima"] is None           # con "mai" non si cercano proposte
    entro45 = _accetta(sala_piccola(300, 300, moduli=1, proposta="entro_45_min"), PUNTA, verificatore)
    assert entro45["non_sistemate"][0]["motivo"] == MOTIVO_PROPOSTA_RIFIUTATA
    assert entro45["registro"][1]["proposta_principale"] == "19:15"
    entro60 = _accetta(sala_piccola(300, 300, moduli=1, proposta="entro_60_min"), PUNTA, verificatore)
    assert entro60["registro"][1]["esito"] == "accettata su proposta"


def test_posto_a_meno_45_e_piu_60_principale_la_piu_vicina(verificatore):
    # un modulo e un tondo, pasti da 30 min (+15). P1 e P2 (5 coperti) occupano il tondo 20:00-21:30, Q1 e Q2
    # occupano il singolo 19:30-21:00. B (2 coperti, 20:00): libero il tondo 19:15-20:00 e il singolo dalle 21:00
    sala = sala_piccola(400, 220, moduli=1, tondi=1, proposta="sempre",
                        durate=[{"fino_a_coperti": None, "minuti": 30}])
    pren = _pren(("P1", "Grande1", 5, "20:00", "2026-10-20T10:00"), ("P2", "Grande2", 5, "20:45", "2026-10-20T11:00"),
                 ("Q1", "Coppia1", 2, "19:30", "2026-10-20T12:00"), ("Q2", "Coppia2", 2, "20:15", "2026-10-20T13:00"),
                 ("B", "Ultimo", 2, "20:00", "2026-10-21T10:00"))
    sol = _accetta(sala, pren, verificatore)
    b = sol["registro"][4]
    assert (b["proposta_prima"], b["proposta_dopo"], b["proposta_principale"]) == ("19:15", "21:00", "19:15")
    assert b["esito"] == "accettata su proposta" and b["proposte_piu_vicine_dimostrate"] == {"prima": True, "dopo": True}
    # a parità di distanza si può preferire il dopo: qui le distanze sono diverse, la principale resta -45
    sala["proposta_a_parita"] = "dopo"
    assert _accetta(sala, pren, verificatore)["registro"][4]["proposta_principale"] == "19:15"


def test_nessun_orario_entro_il_massimo_rifiutata_con_motivo(verificatore):
    sala = sala_piccola(300, 300, moduli=1, proposta="sempre", proposta_max=30)
    pren = _pren(("A", "Primo", 2, "20:00", "2026-10-20T10:00"), ("B", "Dopo", 2, "20:00", "2026-10-21T10:00"))
    sol = _accetta(sala, pren, verificatore)
    assert sol["non_sistemate"][0]["motivo"] == "nessun orario libero entro 30 min"
    assert sol["registro"][1]["decisione"] == "impossibile (dimostrato)"


def test_verificatore_segnala_proposta_oltre_la_distanza_massima(verificatore):
    sala = sala_piccola(300, 300, moduli=1, proposta="sempre")
    sol = _accetta(sala, PUNTA, verificatore)                  # proposta a 60 min, massimo 120: PASS
    sala["proposta_max_distanza_min"] = 45                     # la stessa soluzione con un massimo di 45 min
    falliti = {e.nome for e in verificatore.verifica(sala, PUNTA, sol) if not e.ok}
    assert PROPOSTE in falliti
    assert "orari (spostamenti ammessi, durata, entro il servizio)" in falliti


def test_verificatore_segnala_esito_incoerente_con_la_politica(verificatore):
    sala = sala_piccola(300, 300, moduli=1, proposta="sempre")
    sol = _accetta(sala, PUNTA, verificatore)
    sol["modalita"]["cliente_accetta_proposta"] = "entro_30_min"   # dichiarata ma non rispettata
    falliti = {e.nome for e in verificatore.verifica(sala, PUNTA, sol) if not e.ok}
    assert any(n.startswith("esiti coerenti con la politica") for n in falliti)


def test_prova_risponde_nei_tre_modi_senza_scrivere_file(tmp_path):
    sala = sala_piccola(300, 300, moduli=1, proposta="sempre")
    stato = accetta_in_ordine(costruisci_istanza(sala, _pren(("A", "Primo", 2, "21:00", "2026-10-20T10:00"))),
                              tempo_decisione_s=20, tempo_piantina_s=20)
    sala_stretta = dict(sala, proposta_max_distanza_min=30)
    for nome, dati in (("sala.json", sala), ("sala30.json", sala_stretta), ("stato.json", stato)):
        (tmp_path / nome).write_text(json.dumps(dati, ensure_ascii=False), encoding="utf-8")
    prima = sorted(p.name for p in tmp_path.iterdir())

    def chiedi(coperti, orario, sala_file="sala.json"):
        r = subprocess.run([sys.executable, str(RADICE / "prova.py"), "--stato", str(tmp_path / "stato.json"),
                            "--sala", str(tmp_path / sala_file), "--coperti", str(coperti), "--orario", orario],
                           capture_output=True, text=True, encoding="utf-8", cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    assert chiedi(2, "19:00") == "Sì, alle 19:00 c'è posto."
    assert chiedi(2, "19:30") == "Alle 19:30 no, alle 19:15 sì."
    assert chiedi(2, "20:15") == "Alle 20:15 sono pieno. Posso alle 19:15."
    assert chiedi(2, "21:00", "sala30.json") == "Sabato sono pieno fino a 30 minuti dall'orario chiesto."
    assert sorted(p.name for p in tmp_path.iterdir()) == prima      # nessun file scritto
