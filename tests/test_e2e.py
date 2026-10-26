"""End-to-end: risolvi -> JSON + HTML -> verifica indipendente PASS.

- modalità originale ("tutte_insieme", disposizione fissa) sul sabato di esempio (30 s di solver);
- accettazione in ordine di arrivo con disposizione variabile su una sala piccola (pochi secondi).
La demo completa su sabato_pieno (fissa e variabile, minuti) si lancia con confronto.py, non nei test."""
import json
import re

from conftest import RADICE, sala_piccola

import esegui


def _controlla_html(html: str, sol: dict) -> None:
    assert "<svg" in html and "Timeline per tavolo" in html
    # file autonomo: nessuna risorsa esterna (l'unico URL ammesso è il namespace SVG)
    assert not re.search(r"<script[^>]+src=|<link[^>]+href=|@import", html)
    assert set(re.findall(r"https?://[^\s\"'<>]+", html)) <= {"http://www.w3.org/2000/svg"}
    for r in sol["assegnazioni"]:
        assert f'{r["orario_assegnato"]} {r["nome"]} ×{r["coperti"]}' in html


def test_e2e_sabato_tutte_insieme_verifica_pass(tmp_path, capfd):
    rc = esegui.main(["--accettazione", "tutte_insieme", "--disposizione", "fissa",
                      "--prenotazioni", str(RADICE / "dati" / "sabato.json"), "--out", str(tmp_path)])
    out = capfd.readouterr().out
    assert rc == 0, out
    assert "ESITO: PASS" in out
    sol = json.loads((tmp_path / "soluzione.json").read_text(encoding="utf-8"))
    pren = json.loads((RADICE / "dati" / "sabato.json").read_text(encoding="utf-8"))
    assert sol["solver"]["stato"] in ("OPTIMAL", "FEASIBLE")
    ids = sorted([r["id"] for r in sol["assegnazioni"]] + [r["id"] for r in sol["non_sistemate"]])
    assert ids == sorted(p["id"] for p in pren["prenotazioni"])
    assert sol["solver"]["obiettivo_coerente_con_componenti"] is True
    _controlla_html((tmp_path / "serata.html").read_text(encoding="utf-8"), sol)


def test_e2e_ordine_di_arrivo_variabile_sala_piccola(tmp_path, capfd):
    sala = sala_piccola(larghezza=600, altezza=400, moduli=4, tondi=1)
    pren = {"serata": "prova", "prenotazioni": [
        {"id": "A", "nome": "Rossi", "coperti": 2, "orario": "19:00", "prenotata_il": "2026-10-20T09:00"},
        {"id": "B", "nome": "Bianchi", "coperti": 4, "orario": "19:00", "prenotata_il": "2026-10-20T10:00"},
        {"id": "C", "nome": "Verdi", "coperti": 2, "orario": "19:15", "prenotata_il": "2026-10-21T10:00"},
        {"id": "D", "nome": "Neri", "coperti": 8, "orario": "21:30", "prenotata_il": "2026-10-22T10:00",
         "note": "compleanno"},
        {"id": "E", "nome": "Gialli", "coperti": 6, "orario": "21:00", "prenotata_il": "2026-10-23T10:00"},
        {"id": "F", "nome": "Blu", "coperti": 14, "orario": "20:00", "prenotata_il": "2026-10-24T10:00"},
    ]}
    p_sala, p_pren = tmp_path / "sala.json", tmp_path / "pren.json"
    p_sala.write_text(json.dumps(sala), encoding="utf-8")
    p_pren.write_text(json.dumps(pren), encoding="utf-8")
    rc = esegui.main(["--sala", str(p_sala), "--prenotazioni", str(p_pren), "--out", str(tmp_path / "out"),
                      "--accettazione", "ordine_di_arrivo", "--disposizione", "variabile",
                      "--tempo-decisione", "20", "--tempo-piantina", "20"])
    out = capfd.readouterr().out
    assert rc == 0, out
    assert "ESITO: PASS" in out
    sol = json.loads((tmp_path / "out" / "soluzione.json").read_text(encoding="utf-8"))
    assert [r["id"] for r in sol["registro"]] == list("ABCDEF")
    assert sol["accettazione"]["decisioni_unknown"] == 0
    assert {r["id"] for r in sol["non_sistemate"]} == {"F"}          # 14 coperti: nessun tavolo abbastanza grande
    assert sol["solver"]["origine"] == "solver"
    html = (tmp_path / "out" / "serata.html").read_text(encoding="utf-8")
    _controlla_html(html, sol)
    assert "Registro delle accettazioni" in html
