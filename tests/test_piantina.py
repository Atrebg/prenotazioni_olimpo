"""Sala vera dell'Olimpo dalla piantina: lettura del blocco, blocchi separabili, tavolo lungo, gruppi grandi, posti vuoti,
ordine di arrivo e proposta dell'altro turno, chat con i tavoli solo nel riepilogo, verificatore (anche negativo),
tabella delle disponibilità."""
import copy
import json
import math
import random
import re
from datetime import date, datetime, timedelta

import pytest
from conftest import RADICE

from ristorante import conversazione
from ristorante.conversazione import _Conversazione, gestisci_messaggio
from ristorante.dati import MOTIVO_TURNO_PIENO, costruisci_istanza
from ristorante.disponibilita import CalcolatoreLocale, Disponibilita
from ristorante.modello import accetta_in_ordine
from ristorante.piantina import ErrorePiantina, IMPOSTAZIONI, Piantina, carica_sala, leggi_blocco_sala
from ristorante.serate import Archivio, serata_vuota

PIANTINA = RADICE / "olimpo" / "piantina.html"
MARTEDI = datetime(2026, 10, 27, 10, 0)
SAB = date(2026, 10, 31)
TURNI = [{"nome": "primo", "inizio": "20:00", "fine": "21:30"}, {"nome": "secondo", "inizio": "21:30", "fine": "24:00"}]
BLOCCO3 = {"id": "5", "tipo": "blocco", "x": 0, "y": 0, "moduli": 3, "verso": "verticale", "posti": 8, "separabile": True}
LUNGO = {"id": "11", "tipo": "lungo", "x": 0, "y": 0, "w": 104, "h": 32, "posti": 20}
TONDO10 = {"id": "10", "tipo": "tondo", "x": 0, "y": 0, "r": 27, "posti": 10}
DA2 = {"id": "25", "tipo": "quadrato", "x": 0, "y": 0, "posti": 2}


class SenzaLLM:
    disponibile = False


@pytest.fixture(autouse=True)
def senza_disponibilita_globale():
    conversazione.ferma_disponibilita()
    yield
    conversazione.ferma_disponibilita()


def sala_vera(*tavoli, politica="mai") -> dict:
    """Una sala vera ridotta, con gli stessi campi della piantina."""
    dati = {"nome": "prova", "turni": ["20:00", "21:30"], "posti_quadrato_separato": 4,
            "tavoli": [copy.deepcopy(t) for t in tavoli]}
    return copy.deepcopy(IMPOSTAZIONI) | {"nome": "prova", "turni": copy.deepcopy(TURNI), "piantina": dati,
                                          "cliente_accetta_proposta": politica}


def in_arrivo(*righe) -> dict:
    """(id, coperti, "HH:MM") ricevute in quest'ordine."""
    return {"serata": "prova", "prenotazioni": [
        {"id": r[0], "nome": r[0], "coperti": r[1], "orario": r[2], "prenotata_il": f"2026-10-25T1{i}:00"}
        for i, r in enumerate(righe)]}


def ordine(sala: dict, pren: dict) -> dict:
    return accetta_in_ordine(costruisci_istanza(sala, pren), tempo_decisione_s=30, tempo_proposta_s=30,
                             tempo_piantina_s=30)


def verifica_ok(verificatore, sala, pren, sol):
    esiti = verificatore.verifica(sala["piantina"], pren, sol)
    assert all(e.ok for e in esiti), [(e.nome, e.errori) for e in esiti if not e.ok]


def test_lettura_del_blocco_dalla_piantina(tmp_path):
    dati = leggi_blocco_sala(PIANTINA)
    assert len(dati["tavoli"]) == 30 and dati["turni"] == ["20:00", "21:30"]
    sala = carica_sala(PIANTINA)
    assert sala["turni"] == TURNI and sala["piantina"] == dati
    p = Piantina(dati)
    assert p.posti_per_turno() == 151 and p.capacita() == [2, 3, 4, 6, 8, 10, 20]
    # attributi in un altro ordine, testo intorno: si trova lo stesso; senza blocco: errore chiaro
    altro = tmp_path / "altra.html"
    altro.write_text('<html><body><p>x</p><script id="sala" type="application/json">'
                     '{"turni": ["20:00"], "tavoli": [{"id": "1", "tipo": "panca", "x": 1, "y": 1, "posti": 4}]}'
                     '</script></body></html>', encoding="utf-8")
    assert carica_sala(altro)["turni"] == [{"nome": "primo", "inizio": "20:00", "fine": "24:00"}]
    vuoto = tmp_path / "vuota.html"
    vuoto.write_text("<html><body></body></html>", encoding="utf-8")
    with pytest.raises(ErrorePiantina):
        carica_sala(vuoto)
    # il verificatore legge il blocco da sé, con il suo codice
    import verifica
    assert verifica.leggi_sala(str(PIANTINA)) == dati


def test_piantina_salvata_dall_editor(verificatore):
    """`tests/piantina_salvata_editor.html` è il file scaricato con "Salva piantina" dall'editor della piantina (prova del
    27/10/2026 in Chromium): 25 spostato, 26 da 3 posti, aggiunto il quadrato 30, eliminato il 29 (e la sua unione).
    Il motore, il verificatore e la mappa della serata lo leggono come la piantina."""
    from ristorante.mappa_piantina import genera_html
    salvata = RADICE / "tests" / "piantina_salvata_editor.html"
    dati = leggi_blocco_sala(salvata)
    per_id = {t["id"]: t for t in dati["tavoli"]}
    assert "29" not in per_id and (per_id["30"]["tipo"], per_id["30"]["posti"], per_id["30"]["fisso"]) == ("quadrato", 4, False)
    assert per_id["26"]["posti"] == 3 and (per_id["25"]["x"], per_id["25"]["y"]) != (384, 367)
    assert all("29" not in u["tavoli"] for u in dati["unioni"]) and dati["storico"][-1].endswith("· modificata nell'editor")
    # campi nuovi: fisso per ogni tavolo, scala, ostacoli rettangolari (bancone a L in due pezzi, cucina), porta della cucina
    assert all(isinstance(t["fisso"], bool) for t in dati["tavoli"]) and dati["scala"] == {"lato_quadrato_cm": 80}
    assert {o["tipo"] for o in dati["ostacoli"]} == {"bancone", "cucina"} and all({"x", "y", "w", "h"} <= set(o) for o in dati["ostacoli"])
    assert [p["nome"] for p in dati["porte"]] == ["porta cucina"]
    sala = carica_sala(salvata)
    assert sala["turni"] == TURNI and sala["piantina"] == dati
    p = Piantina(dati)
    assert len(p.tavoli) == 30 and p.posti_per_turno() == 151 - 2 + 1 + 4 and p.capacita() == [2, 3, 4, 6, 8, 10, 20]
    assert verificatore.leggi_sala(str(salvata)) == dati
    pren = in_arrivo(("A", 3, "20:00"), ("B", 4, "21:30"))
    sol = ordine(sala, pren)
    assert sol["accettazione"]["accettate"] == 2
    verifica_ok(verificatore, sala, pren, sol)
    mappa = genera_html(sala, pren, sol)
    assert mappa.count(">cucina<") == 2 and mappa.count(">porta cucina<") == 2      # una vista per turno


def test_piantina_salvata_dall_editor_con_elementi_fissi(verificatore):
    """`tests/piantina_salvata_editor_2.html`: file scaricato dalla seconda versione dell'editor (prova del 27/10/2026 in
    Chromium, desktop): sala larga 1050 cm, 26 spostato con i campi in cm, 11 di 500 x 100 cm, 3 ruotato di 30°, un muro a
    3 vertici spesso 20 cm, pilastri, zona vietata, bagni, cassa, credenza, pedana, blocco "frigo vini", porta e finestra."""
    from ristorante.mappa_piantina import genera_html
    salvata = RADICE / "tests" / "piantina_salvata_editor_2.html"
    dati = leggi_blocco_sala(salvata)
    per_id = {t["id"]: t for t in dati["tavoli"]}
    assert dati["sala"] == {"x": 40, "y": 40, "w": 420, "h": 625} and dati["scala"] == {"lato_quadrato_cm": 80}
    assert (per_id["26"]["x"], per_id["26"]["y"]) == (376, 416) and (per_id["11"]["w"], per_id["11"]["h"]) == (200, 40)
    assert per_id["3"]["rot"] == 30
    tipi = {o["tipo"] for o in dati["ostacoli"]}
    assert tipi == {"bancone", "cucina", "pilastro", "zona_vietata", "bagni", "cassa", "mobile", "pedana", "blocco"}
    assert any(o["tipo"] == "pilastro" and o.get("forma") == "tondo" for o in dati["ostacoli"])
    assert any(o["tipo"] == "blocco" and o["nome"] == "frigo vini" for o in dati["ostacoli"])
    assert all(isinstance(m, dict) and len(m["punti"]) >= 2 and m["spessore_cm"] > 0 for m in dati["muri"])
    assert any(len(m["punti"]) == 3 and m["spessore_cm"] == 20 for m in dati["muri"])
    assert [p["spazio_libero_cm"] for p in dati["porte"]] == [90, 90] and len(dati["finestre"]) == 1
    sala = carica_sala(salvata)
    assert sala["turni"] == TURNI and sala["piantina"] == dati
    p = Piantina(dati)
    assert len(p.tavoli) == 30 and p.posti_per_turno() == 151 and p.capacita() == [2, 3, 4, 6, 8, 10, 20]
    assert verificatore.leggi_sala(str(salvata)) == dati
    pren = in_arrivo(("A", 6, "20:00"), ("B", 2, "21:30"))
    sol = ordine(sala, pren)
    assert sol["accettazione"]["accettate"] == 2
    verifica_ok(verificatore, sala, pren, sol)
    mappa = genera_html(sala, pren, sol)
    assert mappa.count('viewBox="30 10 440 665"') == 2                       # il contorno viene dalla sala salvata
    assert mappa.count(">frigo vini<") == 2 and mappa.count(">zona vietata<") == 2 and "<ellipse" in mappa
    assert 'fill="#e3f2fc"' in mappa and 'stroke-width="8.0"' in mappa       # finestra; muro da 20 cm = 8 unità


def test_mappa_della_serata_con_elementi_sconosciuti_o_incompleti():
    """La mappa della serata disegna in grigio, col nome, i tipi che non conosce e salta gli elementi senza misure,
    senza rompersi; muri nel formato di prima (percorso) e in quello nuovo (punti e spessore)."""
    from ristorante.mappa_piantina import genera_html
    sala = sala_vera(DA2)
    sala["piantina"] |= {
        "ostacoli": [{"nome": "acquario", "tipo": "acquario", "x": 50, "y": 60, "w": 40, "h": 20, "rot": 30},
                     {"tipo": "bancone"}, {"nome": "senza tipo", "x": 100, "y": 100, "w": 50, "h": 30}, "rotto"],
        "muri": ["M10 10 L20 20", {"punti": [[0, 0], [10, 0], [10, 10]], "spessore_cm": 25}, {"punti": [[1, 1]]}, {}],
        "porte": [{"nome": "porta", "x": 60, "y": 30, "w": 36, "h": 4, "rot": 90}, {"nome": "senza misure"}],
        "finestre": [{"nome": "vetrata", "x": 200, "y": 36, "w": 48, "h": 4}, {"x": "boh"}],
        "passaggi": [{"nome": "corridoio", "x": 300, "y": 100}],
    }
    pren = in_arrivo(("A", 2, "20:00"))
    sol = ordine(sala, pren)
    mappa = genera_html(sala, pren, sol)
    assert 'viewBox="30 10 420 665"' in mappa                                  # senza "sala": il contorno di prima
    assert '>acquario<' in mappa and 'fill="#d9d7d0"' in mappa and "rotate(30" in mappa
    assert '>senza tipo<' in mappa and '>vetrata<' in mappa and 'd="M10 10 L20 20"' in mappa
    assert 'd="M0 0 L10 0 L10 10"' in mappa and 'stroke-width="10.0"' in mappa  # 25 cm con il quadrato da 80 cm
    assert "senza misure" not in mappa and "corridoio" not in mappa


def test_mappa_della_serata_ingresso_ruotato_ed_etichette_che_non_stanno():
    """L'ingresso storto della piantina (rot -28,5) si disegna ruotato attorno al suo centro, come nell'editor; un'etichetta
    che non sta nel rettangolo (né dritta né girata) non si scrive, una che ci sta sì (anche girata nel verso lungo)."""
    from ristorante.mappa_piantina import genera_html
    sala = sala_vera(DA2)
    sala["piantina"] |= {
        "ingresso": {"x": 153.8, "y": 90, "w": 100, "h": 8, "rot": -28.5, "spazio_libero_cm": 90},
        "ostacoli": [{"nome": "elemento in angolo (da chiarire)", "tipo": "mobile", "x": 66, "y": 180, "w": 36, "h": 20},
                     {"nome": "bancone", "tipo": "bancone", "x": 50, "y": 270, "w": 20, "h": 210},
                     {"nome": "cucina", "tipo": "cucina", "x": 50, "y": 480, "w": 224, "h": 208}],
    }
    pren = in_arrivo(("A", 2, "20:00"))
    sol = ordine(sala, pren)
    mappa = genera_html(sala, pren, sol)
    assert mappa.count('fill="#ef9f27" transform="rotate(-28.5 203.8 94.0)"') == 2           # una vista per turno
    assert mappa.count(">ingresso<") == 2
    assert "elemento in angolo" not in mappa                                                  # 32 caratteri in 36 x 20 unità
    assert mappa.count(">cucina<") == 2 and mappa.count(">bancone<") == 2
    assert mappa.count('transform="rotate(-90 60.0 375.0)"') == 2                             # bancone stretto e lungo: girato


def _arco(a, b, prof, n):
    """n punti di un arco di cerchio da a a b (estremi esclusi): a metà dista `prof` dalla corda."""
    c = math.dist(a, b)
    tx, ty = (b[0] - a[0]) / c, (b[1] - a[1]) / c
    nx, ny = -ty, tx
    r = (c * c / 4 + prof * prof) / (2 * prof)
    th = math.asin(c / 2 / r)
    ox, oy = (a[0] + b[0]) / 2 + nx * (prof - r), (a[1] + b[1]) / 2 + ny * (prof - r)
    ang = [-th + 2 * th * k / (n + 1) for k in range(1, n + 1)]
    return [[round(ox + r * (math.cos(f) * nx + math.sin(f) * tx), 2), round(oy + r * (math.cos(f) * ny + math.sin(f) * ty), 2)] for f in ang]


def test_muro_curvo_dal_comando_curva_dell_editor(tmp_path, verificatore):
    """Il comando Curva dell'editor lascia nel muro una spezzata con tanti vertici (nessun campo nuovo): il motore, il verificatore
    e la mappa della serata la leggono come una piantina qualunque. Qui un tratto del primo muro diventa un arco da 30 punti."""
    from ristorante.mappa_piantina import genera_html
    testo = PIANTINA.read_text(encoding="utf-8")
    dati = leggi_blocco_sala(PIANTINA)
    muro = dati["muri"][0]
    punti_prima = len(muro["punti"])
    a, b = muro["punti"][1], muro["punti"][2]                                  # il lato sinistro, verticale
    arco = _arco(a, b, 40, 30)                                                 # 100 cm di profondità
    assert len(arco) == 30 and max(abs(p[0] - a[0]) for p in arco) == pytest.approx(40, abs=0.5)
    muro["punti"][2:2] = arco
    curva = tmp_path / "piantina_curva.html"
    curva.write_text(re.sub(r'(<script type="application/json" id="sala">).*?(</script>)',
                            lambda m: m.group(1) + "\n" + json.dumps(dati, ensure_ascii=False) + "\n" + m.group(2), testo, count=1, flags=re.S),
                     encoding="utf-8")
    letti = leggi_blocco_sala(curva)
    punti = letti["muri"][0]["punti"]
    assert letti == dati and len(punti) == punti_prima + 30 and punti[1] == a and punti[2 + 30] == b   # i 30 vertici stanno tra a e b
    assert letti["tavoli"] == leggi_blocco_sala(PIANTINA)["tavoli"]
    sala = carica_sala(curva)
    assert sala["piantina"] == letti and Piantina(letti).posti_per_turno() == 151
    pren = in_arrivo(("A", 6, "20:00"), ("B", 2, "21:30"))
    sol = ordine(sala, pren)
    assert sol["accettazione"]["accettate"] == 2
    verifica_ok(verificatore, sala, pren, sol)
    mappa = genera_html(sala, pren, sol)
    inizio = f"M{punti[0][0]:g} {punti[0][1]:g} L{punti[1][0]:g} {punti[1][1]:g} L"    # il percorso parte dai primi punti dei dati
    percorsi = re.findall(r'<path d="(' + re.escape(inizio) + r'[^"]*)" fill="none" stroke="#2c2c2a"', mappa)
    assert len(percorsi) == 2 and all(p.count(" L") == len(punti) - 1 for p in percorsi)    # una vista per turno; N punti = N-1 tratti


def test_partizioni_di_un_blocco_da_tre(verificatore):
    p = Piantina({"tavoli": [BLOCCO3], "posti_quadrato_separato": 4})
    assert {u.quadrati: u.posti for u in p.unita()} == {(0, 2): 8, (0, 1): 6, (1, 2): 6, (0, 0): 4, (1, 1): 4, (2, 2): 4}
    sala = sala_vera(BLOCCO3)
    for righe, attese in (([("A", 8, "20:00")], [[0, 2]]),
                          ([("A", 5, "20:00"), ("B", 3, "20:00")], None),          # 2 + 1 (in un verso o nell'altro)
                          ([("A", 2, "20:00"), ("B", 2, "20:00"), ("C", 2, "20:00")], [[0, 0], [1, 1], [2, 2]])):
        pren = in_arrivo(*righe)
        sol = ordine(sala, pren)
        assert sol["accettazione"]["accettate"] == len(righe)
        part = sol["tavoli"][0]["partizioni"]["primo"]
        if attese is None:
            assert sorted(b - a + 1 for a, b in part) == [1, 2]
        else:
            assert part == attese
        assert sol["tavoli"][0]["partizioni"]["secondo"] == [[0, 2]]
        verifica_ok(verificatore, sala, pren, sol)
    # quattro coppie non entrano in un blocco da 3 (al più 3 pezzi)
    sol = ordine(sala, in_arrivo(("A", 2, "20:00"), ("B", 2, "20:00"), ("C", 2, "20:00"), ("D", 2, "20:00")))
    assert [r["id"] for r in sol["non_sistemate"]] == ["D"]


def test_lungo_due_gruppi_da_otto_e_niente_terzo(verificatore):
    sala = sala_vera(LUNGO)
    pren = in_arrivo(("A", 8, "20:00"), ("B", 8, "20:00"), ("C", 8, "20:00"), ("D", 10, "21:30"), ("E", 4, "21:30"))
    sol = ordine(sala, pren)
    seduti = {r["id"]: (r["turno"], r["gruppo"]) for r in sol["assegnazioni"]}
    assert seduti == {"A": ("primo", 1), "B": ("primo", 2), "D": ("secondo", 1)} or \
           seduti == {"A": ("primo", 2), "B": ("primo", 1), "D": ("secondo", 1)}
    assert {r["id"]: r["motivo"] for r in sol["non_sistemate"]} == {"C": MOTIVO_TURNO_PIENO, "E": MOTIVO_TURNO_PIENO}
    verifica_ok(verificatore, sala, pren, sol)


def test_gruppo_da_diciotto_solo_sul_lungo_e_proposta_dell_altro_turno(verificatore):
    sala = carica_sala(PIANTINA)
    sala["cliente_accetta_proposta"] = "sempre"
    pren = in_arrivo(("G18", 18, "20:00"), ("G14", 14, "20:15"), ("C2", 2, "20:00"))
    sol = ordine(sala, pren)
    per_id = {r["id"]: r for r in sol["assegnazioni"]}
    assert (per_id["G18"]["tavolo"], per_id["G18"]["turno"]) == ("11", "primo")
    assert (per_id["G14"]["tavolo"], per_id["G14"]["turno"]) == ("11", "secondo")     # il lungo era preso: altro turno
    reg = {r["id"]: r for r in sol["registro"]}
    assert reg["G14"]["esito"] == "accettata su proposta" and reg["G14"]["turno_proposto"] == "secondo"
    assert per_id["C2"]["posti_tavolo"] == 2                       # la coppia al tavolo da 2, non al tondo da 10
    verifica_ok(verificatore, sala, pren, sol)
    # con "mai" il secondo gruppo grande resta fuori
    sala["cliente_accetta_proposta"] = "mai"
    sol = ordine(sala, pren)
    assert [(r["id"], r["motivo"]) for r in sol["non_sistemate"]] == [("G14", MOTIVO_TURNO_PIENO)]


def test_coppia_non_al_tondo_da_dieci_se_ce_un_tavolo_da_due(verificatore):
    sala = sala_vera(TONDO10, DA2, LUNGO)
    pren = in_arrivo(("C", 2, "20:00"))
    sol = ordine(sala, pren)
    assert sol["assegnazioni"][0]["tavolo"] == "25" and sol["obiettivo_componenti"]["posti_vuoti"]["posti"] == 0
    verifica_ok(verificatore, sala, pren, sol)
    pren = in_arrivo(("C", 2, "20:00"), ("D", 2, "20:00"))        # il tavolo da 2 è preso: meglio il tondo che il lungo
    sol = ordine(sala, pren)
    assert sorted(r["tavolo"] for r in sol["assegnazioni"]) == ["10", "25"]


def test_chat_sulla_sala_vera_tavolo_solo_nel_riepilogo(tmp_path):
    sala = carica_sala(PIANTINA)

    def invia(t, minuti=0):
        return gestisci_messaggio(t, MARTEDI + timedelta(minutes=minuti), "p", tmp_path, sala=sala, lettore=SenzaLLM())

    assert invia("Ferri 18 sab 1t") == "✓ Ferri · 18 persone · sab 31/10 · primo turno (20:00)"
    assert invia("Bianchi 14 sab 20:15", 1) == ("Bianchi · 14 persone · sab 31/10: il primo turno è pieno. "
                                               "Posso nel secondo, alle 21:30. Va bene?")
    assert invia("ok", 2) == "✓ Bianchi · 14 persone · sab 31/10 · secondo turno (21:30)"
    assert invia("Rossi 2 sab 2t", 3) == "✓ Rossi · 2 persone · sab 31/10 · secondo turno (21:30)"
    r = invia("riepilogo sab", 4)
    assert "Ferri 18 · tavolo 11" in r and "Bianchi 14 · tavolo 11" in r
    assert r.splitlines()[-1].startswith("Tavoli indicativi")
    rossi = next(x for x in r.splitlines() if x.strip().startswith("Rossi 2"))
    assert "· tavolo " in rossi and rossi.split("tavolo ")[1].split(",")[0] in {"3", "4", "25", "26", "27", "28", "29"}


def _sol_valida():
    sala = sala_vera(BLOCCO3, LUNGO, DA2)
    pren = in_arrivo(("A", 2, "20:00"), ("B", 4, "20:00"), ("L1", 8, "20:00"), ("L2", 6, "20:00"), ("S", 2, "21:30"))
    sol = ordine(sala, pren)
    assert sol["accettazione"]["accettate"] == 5
    return sala, pren, sol


def test_verificatore_negativi(verificatore):
    sala, pren, sol = _sol_valida()
    verifica_ok(verificatore, sala, pren, sol)

    def falliti(mod):
        s, p = copy.deepcopy(sol), copy.deepcopy(pren)
        mod(s, p) if mod.__code__.co_argcount == 2 else mod(s)
        return {e.nome for e in verificatore.verifica(sala["piantina"], p, s) if not e.ok}

    posti = "posti: ogni prenotazione su un tavolo o pezzo del suo turno, coperti <= posti"

    def stesso_quadrato(s):           # due prenotazioni sullo stesso quadrato nello stesso turno
        a = next(r for r in s["assegnazioni"] if r["id"] == "A")
        b = next(r for r in s["assegnazioni"] if r["id"] == "B")
        a.update(tavolo="5", quadrati=[0, 0], gruppo=None, posti_tavolo=4)
        b.update(tavolo="5", quadrati=[0, 0], gruppo=None, posti_tavolo=4)
        next(t for t in s["tavoli"] if t["id"] == "5")["partizioni"]["primo"] = [[0, 0], [1, 1], [2, 2]]
    assert posti in falliti(stesso_quadrato)

    def non_contigua(s):
        next(t for t in s["tavoli"] if t["id"] == "5")["partizioni"]["secondo"] = [[0, 0], [2, 2]]
    assert "partizioni dei blocchi contigue, per turno" in falliti(non_contigua)

    def troppi_coperti(s):            # 4 coperti su un quadrato da 2
        next(r for r in s["assegnazioni"] if r["id"] == "B").update(tavolo="25", quadrati=None, gruppo=None, posti_tavolo=2)
    assert posti in falliti(troppi_coperti)

    lungo = "tavolo lungo: un gruppo fino ai suoi posti, oppure due gruppi fino a 8"

    def tre_gruppi(s):
        a = next(r for r in s["assegnazioni"] if r["id"] == "A")
        a.update(tavolo="11", quadrati=None, gruppo=2, posti_tavolo=8)
    assert lungo in falliti(tre_gruppi)

    def gruppo_grande_in_due(s, p):   # due gruppi sul lungo, ma uno da 10
        for r in s["assegnazioni"]:
            if r["tavolo"] == "11":
                r.update(tavolo="5", quadrati=[0, 2], gruppo=None, posti_tavolo=8, turno="secondo",
                         orario_assegnato="21:30", fine="24:00")
        for pid, g in (("L1", 1), ("L2", 2)):
            next(r for r in s["assegnazioni"] if r["id"] == pid).update(
                tavolo="11", quadrati=None, gruppo=g, posti_tavolo=20 if g == 1 else 8, turno="primo")
        next(r for r in s["assegnazioni"] if r["id"] == "L1")["coperti"] = 10
        next(x for x in p["prenotazioni"] if x["id"] == "L1")["coperti"] = 10
    assert lungo in falliti(gruppo_grande_in_due)

    def turno_cambiato(s):           # promessa nel primo turno, seduta nel secondo
        r = next(r for r in s["assegnazioni"] if r["id"] == "B")
        r.update(turno="secondo", orario_assegnato="21:30", fine="24:00")
    f = falliti(turno_cambiato)
    assert "turno finale = turno promesso (e orari uguali a quelli promessi)" in f

    def duplicata(s):
        s["assegnazioni"].append(copy.deepcopy(s["assegnazioni"][0]))
    assert "ogni prenotazione presente esattamente una volta" in falliti(duplicata)

    def registro_disordinato(s):
        s["registro"][0], s["registro"][1] = s["registro"][1], s["registro"][0]
    assert "registro in ordine di prenotazione" in falliti(registro_disordinato)


def test_tabella_sulla_sala_vera_uguale_al_calcolo_diretto(tmp_path):
    rnd = random.Random(7)
    sala = carica_sala(PIANTINA)
    cartella = tmp_path / "s"
    arch = Archivio(cartella)
    stato = serata_vuota(SAB)
    conv = _Conversazione(arch, sala, SenzaLLM(), MARTEDI, "x")
    for i in range(40):
        c, o = rnd.choice([2, 2, 2, 4, 4, 3, 5, 6, 8, 10]), rnd.choice(["20:00", "21:30"])
        if conv._valuta_diretta(stato, c, o).esito == "entra":
            stato["accettate"].append({"id": f"A{i}", "nome": f"N{i}", "coperti": c, "orario": o})
    stato["versione"] = 1
    arch.salva(stato)
    disp = Disponibilita(cartella, sala, CalcolatoreLocale(cartella))
    assert [k.nome for k in disp.classi] == ["1-2", "3", "4", "5-6", "7-8", "9-10", "11-20"]
    disp.aggiorna(stato)
    assert disp.tabella_pronta(SAB)
    for c, o in ((2, "20:00"), (4, "21:30"), (6, "20:00"), (8, "21:30"), (10, "20:00"), (14, "21:30"), (20, "20:00")):
        a, b = disp.valuta(stato, c, o), conv._valuta_diretta(stato, c, o)
        assert (a.esito, a.opzioni) == (b.esito, b.opzioni), (c, o)
