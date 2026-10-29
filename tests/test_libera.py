"""Disposizione libera dei tavoli mobili sulla sala vera: una sala piccola di prova con un muro curvo e un ostacolo
(accettazione, inventario, sedie contro i muri, verifica indipendente anche negativa), e un controllo veloce sulla
piantina vera dell'Olimpo."""
import copy
import math

import pytest
from conftest import RADICE, esiti_per_nome

from ristorante.dati import costruisci_istanza
from ristorante.modello_libero import (accetta_in_ordine_libera, impossibile_per_conteggio_libera, posti_pezzo,
                                       sala_libera)
from ristorante.piantina import IMPOSTAZIONI, carica_sala, leggi_blocco_sala
from ristorante.sala_libera import SalaLibera

PIANTINA = RADICE / "olimpo" / "piantina.html"
TEMPI = {"tempo_impianto_s": 20, "tempo_decisione_s": 5, "tempo_piantina_s": 5}
TEMPI_VERA = {"tempo_impianto_s": 30, "tempo_decisione_s": 5, "tempo_piantina_s": 5}


def _arco(cx, cy, r, a0, a1, n=8):
    return [[round(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), 2),
             round(cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)), 2)] for i in range(n + 1)]


def piantina_piccola() -> dict:
    """Sala 8,5 x 6,5 m (1 m = 40 unità), ingresso in alto a sinistra, angolo in alto a destra curvo, un bancone in basso
    a sinistra e un pilastro; 3 quadrati, un blocco da 2 e una panca fissa."""
    perimetro = [[110, 10], [250, 10]] + _arco(250, 90, 80, -90, 0)[1:] + [[330, 250], [10, 250], [10, 10], [40, 10]]
    return {
        "nome": "Sala di prova", "turni": ["20:00", "21:30"], "posti_quadrato_separato": 4,
        "scala": {"lato_quadrato_cm": 80}, "sala": {"x": 6, "y": 6, "w": 328, "h": 248},
        "ingresso": {"x": 40, "y": 6, "w": 70, "h": 8, "spazio_libero_cm": 90},
        "muri": [{"punti": perimetro, "spessore_cm": 20}],
        "ostacoli": [{"nome": "bancone", "tipo": "bancone", "x": 14, "y": 170, "w": 60, "h": 76},
                     {"nome": "pilastro", "tipo": "pilastro", "forma": "quadrato", "x": 200, "y": 150, "w": 12, "h": 12}],
        "porte": [], "finestre": [], "passaggi": [],
        "tavoli": [
            {"id": "1", "tipo": "quadrato", "x": 100, "y": 100, "posti": 2, "fisso": False},
            {"id": "2", "tipo": "quadrato", "x": 150, "y": 100, "posti": 2, "fisso": False},
            {"id": "3", "tipo": "quadrato", "x": 200, "y": 100, "posti": 2, "fisso": False},
            {"id": "4", "tipo": "blocco", "x": 150, "y": 200, "moduli": 2, "verso": "orizzontale", "posti": 6,
             "fisso": False, "separabile": True},
            {"id": "5", "tipo": "panca", "x": 300, "y": 220, "posti": 4, "fisso": True},
        ],
        "unioni": [],
    }


def sala_di(piantina: dict) -> dict:
    turni = [{"nome": "primo", "inizio": "20:00", "fine": "21:30"}, {"nome": "secondo", "inizio": "21:30", "fine": "24:00"}]
    return copy.deepcopy(IMPOSTAZIONI) | {"nome": piantina["nome"], "turni": turni, "piantina": piantina, "fonte": "prova"}


def serata(*righe) -> dict:
    """righe: (id, nome, coperti, orario); prenotate nell'ordine dato."""
    return {"serata": "prova", "prenotazioni": [{"id": i, "nome": n, "coperti": c, "orario": o,
                                                 "prenotata_il": f"2026-10-20T10:{m:02d}"}
                                                for m, (i, n, c, o) in enumerate(righe)]}


@pytest.fixture(scope="module")
def risolta():
    pia = piantina_piccola()
    pren = serata(("A", "Rossi", 4, "20:00"), ("B", "Bianchi", 2, "20:00"), ("C", "Verdi", 4, "20:00"),
                  ("D", "Neri", 3, "21:30"), ("E", "Gialli", 4, "21:30"), ("F", "Blu", 2, "21:30"))
    ist = costruisci_istanza(sala_di(pia), pren)
    sol = accetta_in_ordine_libera(ist, tempi=TEMPI)
    return pia, pren, sol, ist


def test_sala_piccola_tutte_sedute_e_inventario(risolta):
    pia, pren, sol, ist = risolta
    assert sol["accettazione"]["accettate"] == 6 and not sol["non_sistemate"]
    file = [t for t in sol["tavoli"] if t["tipo"] == "fila"]
    assert sum(t["moduli"] for t in file) <= 5                   # 3 quadrati + 2 del blocco: mai un tavolo in più
    assert {t["id"] for t in sol["tavoli"] if t.get("fisso")} == {"5"}
    assert all(t["orientamento"] in ("orizzontale", "verticale") for t in file)
    quattro = [r for r in sol["assegnazioni"] if r["coperti"] == 4]       # tre gruppi da 4 e una sola panca da 4
    assert any(r["tavolo"] in {t["id"] for t in file} and r["posti_tavolo"] >= 4 for r in quattro)
    assert not sol["geometria"]["irraggiungibili_secondo_il_motore"]
    assert any(m["cosa"].startswith("tavoli fissi senza misure") for m in sol["misure_usate"])    # la panca: default


def test_sala_piccola_verifica_indipendente(risolta, verificatore):
    pia, pren, sol, _ = risolta
    esiti = verificatore.verifica(pia, pren, sol)
    assert all(e.ok for e in esiti), [(e.nome, e.errori) for e in esiti if not e.ok]
    nomi = {e.nome for e in esiti}
    assert any(n.startswith("tavoli e sedie dentro i muri") for n in nomi)
    assert any(n.startswith("corridoi: ogni tavolo") for n in nomi)


def _fila(sol, n=0):
    return [t for t in sol["tavoli"] if t["tipo"] == "fila"][n]


def _esito(esiti, inizio):
    return next(e for e in esiti if e.nome.startswith(inizio))


def test_verificatore_libera_negativi(risolta, verificatore):
    pia, pren, sol, _ = risolta
    # fila spinta oltre la curva, in alto a destra
    s = copy.deepcopy(sol)
    _fila(s)["x_cm"], _fila(s)["y_cm"] = 760, 60
    esiti = verificatore.verifica(pia, pren, s)
    assert not _esito(esiti, "tavoli e sedie dentro i muri").ok
    # fila sopra il pilastro
    s = copy.deepcopy(sol)
    _fila(s)["x_cm"], _fila(s)["y_cm"] = 480, 360
    assert not _esito(verificatore.verifica(pia, pren, s), "niente sopra ostacoli").ok
    # due file una sopra l'altra
    s = copy.deepcopy(sol)
    if len([t for t in s["tavoli"] if t["tipo"] == "fila"]) > 1:
        _fila(s, 1)["x_cm"], _fila(s, 1)["y_cm"] = _fila(s)["x_cm"] + 40, _fila(s)["y_cm"]
        assert not _esito(verificatore.verifica(pia, pren, s), "zone delle sedie libere").ok
    # un quadrato in più dell'inventario
    s = copy.deepcopy(sol)
    _fila(s)["moduli"] = 9
    assert not _esito(verificatore.verifica(pia, pren, s), "inventario").ok
    # posti dichiarati diversi dalle sedie
    s = copy.deepcopy(sol)
    _fila(s)["posti"] += 1
    assert not _esito(verificatore.verifica(pia, pren, s), "inventario").ok
    # una prenotazione con più coperti delle sedie del suo pezzo
    s = copy.deepcopy(sol)
    r = next(r for r in s["assegnazioni"] if r.get("quadrati"))
    r["coperti"] = r["posti_tavolo"] + 1
    assert not _esito(verificatore.verifica(pia, pren, s), "posti:").ok


def test_sedia_contro_il_muro_e_corridoio_chiuso(risolta, verificatore):
    pia, pren, sol, _ = risolta
    # fila da 1 contro il muro di sinistra (faccia interna a 35 cm): una sedia a sinistra non ci sta
    s = copy.deepcopy(sol)
    f = _fila(s)
    k = f["moduli"]
    f.update(x_cm=40, y_cm=300, orientamento="orizzontale", larghezza_cm=80 * k, altezza_cm=80)
    f["sedie"] = {"lato_a": [0] * k, "lato_b": [0] * k, "testa": 1, "coda": 0}
    f["posti"] = 1
    assert not _esito(verificatore.verifica(pia, pren, s), "tavoli e sedie dentro i muri").ok
    # senza la sedia contro il muro va bene per i muri
    f["sedie"]["testa"], f["posti"] = 0, 0
    assert _esito(verificatore.verifica(pia, pren, s), "tavoli e sedie dentro i muri").ok
    # una fila da 2 appena dentro l'ingresso: nessun corridoio da 60 cm parte più dall'ingresso
    s = copy.deepcopy(sol)
    f = _fila(s)
    f.update(x_cm=110, y_cm=40, moduli=2, orientamento="orizzontale", larghezza_cm=160, altezza_cm=80, posti=0,
             sedie={"lato_a": [0, 0], "lato_b": [0, 0], "testa": 0, "coda": 0})
    corridoi = _esito(verificatore.verifica(pia, pren, s), "corridoi:")
    assert not corridoi.ok and any("non si raggiunge" in m for m in corridoi.errori)


def test_conteggio_e_troppo_grandi():
    ist = costruisci_istanza(sala_di(piantina_piccola()), serata(("A", "Rossi", 2, "20:00")))
    sala = sala_libera(ist)
    assert sala.n_quadrati == 5 and len(sala.fissi) == 1
    assert not impossibile_per_conteggio_libera(ist, [4, 2, 2])
    assert impossibile_per_conteggio_libera(ist, [2] * 7)                     # 6 tavoli al più: 5 quadrati + la panca
    assert impossibile_per_conteggio_libera(ist, [12])                        # oltre 2 * k_max + 2 e oltre la panca
    pren = serata(("A", "Rossi", 12, "20:00"))
    sol = accetta_in_ordine_libera(costruisci_istanza(sala_di(piantina_piccola()), pren), tempi=TEMPI)
    assert sol["non_sistemate"][0]["motivo"] == "nessun tavolo componibile abbastanza grande"


def test_posti_di_un_pezzo():
    fila = {"k": 3, "sedie": {"a": [1, 1, 0], "b": [1, 0, 1], "testa": 1, "coda": 1}}
    assert posti_pezzo(fila, 0, 2) == 6
    assert posti_pezzo(fila, 0, 0) == 3            # testa + i due lati del primo quadrato
    assert posti_pezzo(fila, 1, 1) == 1            # in mezzo: niente testate (i pezzi restano accostati)
    assert posti_pezzo(fila, 2, 2) == 2


def test_sala_vera_geometria_e_serata_corta(verificatore):
    """Piantina vera: inventario, misure di default dichiarate, e una serata corta risolta e verificata."""
    dati = leggi_blocco_sala(PIANTINA)
    s = SalaLibera(dati)
    quadrati = sum(int(t.get("moduli") or 1) if t["tipo"] == "blocco" else 1 for t in dati["tavoli"]
                   if t["tipo"] in ("quadrato", "blocco") and not t.get("fisso"))
    assert s.n_quadrati == quadrati
    assert {f.id for f in s.fissi} == {str(t["id"]) for t in dati["tavoli"] if t.get("fisso")}
    cose = " · ".join(m["cosa"] for m in s.misure)
    assert "zona delle sedie" in cose and "corridoio per il personale" in cose and "lato di un quadrato" in cose
    assert not s.irraggiungibili([])                 # sala senza file: niente di nuovo chiuso
    pren = serata(("A", "Rossi", 2, "20:00"), ("B", "Bianchi", 6, "20:00"), ("C", "Verdi", 10, "20:00"),
                  ("D", "Neri", 4, "21:30"), ("E", "Gialli", 2, "21:30"))
    sala = carica_sala(PIANTINA)
    sol = accetta_in_ordine_libera(costruisci_istanza(sala, pren), tempi=TEMPI_VERA)
    assert sol["accettazione"]["accettate"] == 5, sol["registro"]
    esiti = verificatore.verifica(sala["piantina"], pren, sol)
    assert all(e.ok for e in esiti), [(e.nome, e.errori) for e in esiti if not e.ok]
    assert esiti_per_nome(esiti)


def test_disegno_della_sala_vera_con_le_regole(verificatore):
    """Regola di Giacomo (28/10): i 29 quadrati restano tutti in sala e il disegno così com'è (posizioni, rotazioni,
    posti) è ammesso. Una serata corta sulla variante del disegno passa la verifica indipendente con 29 quadrati; una
    soluzione con un tavolo in meno, o con una fila che dichiara meno quadrati dei pezzi che unisce, no."""
    from ristorante.libera_varianti import accetta_in_ordine_varianti
    sala = carica_sala(PIANTINA)
    pren = serata(("A", "Rossi", 2, "20:00"), ("B", "Bianchi", 6, "20:00"), ("C", "Verdi", 10, "21:30"),
                  ("D", "Neri", 4, "21:30"))
    ist = costruisci_istanza(sala, pren)
    sol = accetta_in_ordine_varianti(ist, sala, pren)
    assert sol["accettazione"]["accettate"] == 4
    esiti = verificatore.verifica(sala["piantina"], pren, sol)
    assert all(e.ok for e in esiti), [(e.nome, e.errori) for e in esiti if not e.ok]
    tutti = _esito(esiti, "tutti i quadrati del disegno")
    assert tutti.dettaglio.startswith("29/29")
    s2 = copy.deepcopy(sol)                             # un quadrato sparito dalla sala
    s2["tavoli"] = [t for t in s2["tavoli"] if t["id"] != "25"]
    s2["assegnazioni"] = [r for r in s2["assegnazioni"] if r["tavolo"] != "25"]
    assert not _esito(verificatore.verifica(sala["piantina"], pren, s2), "tutti i quadrati del disegno").ok
    s3 = copy.deepcopy(sol)                             # i quadrati del 25 in nessun pezzo della disposizione
    s3["variante"]["pezzi"] = [p for p in s3["variante"]["pezzi"] if p["id"] != "25"]
    assert not _esito(verificatore.verifica(sala["piantina"], pren, s3), "tutti i quadrati del disegno").ok
    s4 = copy.deepcopy(sol)                             # un pezzo «come nel disegno» spostato di nascosto
    next(p for p in s4["variante"]["pezzi"] if p["id"] == "9")["x"] += 20
    assert not _esito(verificatore.verifica(sala["piantina"], pren, s4), "pezzi cambiati").ok


def test_pezzo_allungato_senza_lato_d_accesso():
    """Un pezzo allungato deve avere un lato d'accesso da 60 cm oltre le sedie, come i tavoli nuovi. L'8 del disegno
    ce l'ha; allungato di un quadrato in coda e spostato contro il 9 e il 12 non ce l'ha più e viene bocciato (anche se
    lo spazio fra i corpi lo si guardasse a parte)."""
    from ristorante.libera_varianti import _mobili, allunga, controlla_pezzo, ha_accesso
    from ristorante.modello_libero import sala_libera
    sala_cfg = carica_sala(PIANTINA)
    ist = costruisci_istanza(sala_cfg, serata(("A", "Rossi", 2, "20:00")))
    sala = sala_libera(ist)
    mob = _mobili(ist.piantina.dati)
    altri = [t for i, t in mob.items() if i != "8"]
    assert ha_accesso(sala, mob["8"], altri)
    chiuso = [t for t in altri] + [dict(mob["12"], id="x1", x=float(mob["8"]["x"]) + d, y=float(mob["8"]["y"]) + e)
                                   for d, e in ((0, -60), (0, 60), (-60, 0), (60, 0), (45, 45), (-45, -45), (45, -45), (-45, 45))]
    nuovo = allunga(mob["8"], 0, 1, 0.0, 0.0, 0.0, sala.cpu)
    assert not ha_accesso(sala, nuovo, chiuso)
    from ristorante import libera_varianti as lv
    vero = lv.ha_accesso
    try:                                          # solo la regola dell'accesso: le distanze fra i corpi non contano qui
        lv.DISTANZA_REGOLA_CM, vecchia = 0, lv.DISTANZA_REGOLA_CM
        viol, _ = controlla_pezzo(sala, nuovo, mob["8"], [t for t in chiuso if not str(t["id"]).startswith("x")])
        lv.ha_accesso = lambda s, t, a: vero(s, t, chiuso if t is nuovo else a)
        viol2, _ = controlla_pezzo(sala, nuovo, mob["8"], [t for t in chiuso if not str(t["id"]).startswith("x")])
    finally:
        lv.DISTANZA_REGOLA_CM = vecchia
        lv.ha_accesso = vero
    assert not any("lato d'accesso" in v[0] for v in viol), viol
    assert any("lato d'accesso" in v[0] for v in viol2), viol2


def test_blocchi_della_striscia_divisi_danno_due_posti_a_quadrato(verificatore):
    """Regola di Giacomo (29/10): i 20-24 hanno 4 posti, niente sedie in testa; divisi sul posto danno 2 + 2, mai più
    di 4. Vale nel modo a tavoli fermi (Piantina, verifica) e nella disposizione libera (pezzo accorciato)."""
    from ristorante.libera_varianti import _accorcia
    from ristorante.piantina import Piantina
    dati = leggi_blocco_sala(PIANTINA)
    p = Piantina(dati)
    for tid in ("20", "21", "22", "23", "24"):
        t = p.per_id[tid]
        assert int(t["posti"]) == 4 and int(t["moduli"]) == 2
        assert p.posti_pezzo(t, 0, 1) == 4 and p.posti_pezzo(t, 0, 0) == 2 and p.posti_pezzo(t, 1, 1) == 2
        assert verificatore._posti_pezzo(t, 0, 0, 4) == 2 and verificatore._posti_pezzo(t, 0, 1, 4) == 4
        r, _ = _accorcia(dati, t, float(t["x"]) + 50, float(t["y"]))
        assert r["posti"] == 2
    t5 = p.per_id["5"]                                    # gli altri blocchi come prima: 2j + 2, un quadrato da solo 4
    assert p.posti_pezzo(t5, 0, 1) == 6 and p.posti_pezzo(t5, 0, 0) == int(dati.get("posti_quadrato_separato", 4))


def _rec(sol, pid):
    return next(r for r in sol["registro"] if r["id"] == pid)


def test_sala_vera_un_tavolo_nuovo_proposto_dal_motore(verificatore):
    """Lungo e tondo pieni in tutti e due i turni: il terzo gruppo da 10 entra solo se il motore smonta e rimonta dei
    pezzi del disegno in un tavolo da 4 quadrati (10 posti). La disposizione passa la verifica con 29 quadrati, e la
    mossa è scritta per il personale."""
    from ristorante.libera_varianti import accetta_in_ordine_varianti
    sala = carica_sala(PIANTINA)
    pren = serata(("X", "Lunghi", 20, "20:00"), ("Y", "Tondi", 10, "20:00"), ("X2", "Lunghi2", 20, "21:30"),
                  ("Y2", "Tondi2", 10, "21:30"), ("Z", "Marini", 10, "20:00"))
    ist = costruisci_istanza(sala, pren)
    sol = accetta_in_ordine_varianti(ist, sala, pren)
    assert sol["accettazione"]["accettate"] == 5, [(r["nome"], r["esito"], r["stato_solver"]) for r in sol["registro"]]
    # il tavolo da 10 che manca: un pezzo allungato (un quadrato staccato da un altro pezzo e attaccato) o un tavolo nuovo
    nuovi = {p["id"]: p for p in sol["variante"]["pezzi"] if p["stato"] in ("nuovo", "allungato")}
    dieci = [r for r in sol["assegnazioni"] if r["id"] in ("Y", "Z")]   # uno dei due ci va (anche Tondi:
    sul_nuovo = [r for r in dieci if r["tavolo"] in nuovi]              # chi era confermato può cambiare tavolo)
    assert len(sul_nuovo) == 1 and nuovi[sul_nuovo[0]["tavolo"]]["moduli"] == 4 and nuovi[sul_nuovo[0]["tavolo"]]["posti"] >= 10
    assert len(nuovi[sul_nuovo[0]["tavolo"]]["da"]) >= 2        # quadrati di almeno due pezzi del disegno: un'unione
    assert _rec(sol, "Z")["mosse"] and any(("componi" in m["mossa"] or "attacca" in m["mossa"]) and
                                           "Marini" in (m["per"] or "") for m in sol["variante"]["mosse"])
    if any(p["stato"] == "accorciato" for p in sol["variante"]["pezzi"]):
        assert any("dividi" in m["mossa"] for m in sol["variante"]["mosse"])      # la divisione è scritta
        s2 = copy.deepcopy(sol)               # il quadrato che resta spostato di 1 u fuori dall'impronta del disegno
        p = next(p for p in s2["variante"]["pezzi"] if p["stato"] == "accorciato")
        a = math.radians(p["rot"])
        ax = (math.cos(a), math.sin(a)) if p.get("verso") == "orizzontale" else (-math.sin(a), math.cos(a))
        src = next(t for t in sala["piantina"]["tavoli"] if str(t["id"]) == p["id"])
        s = 1 if (p["x"] - src["x"]) * ax[0] + (p["y"] - src["y"]) * ax[1] >= 0 else -1
        p["x"], p["y"] = p["x"] + s * ax[0], p["y"] + s * ax[1]
        assert not _esito(verificatore.verifica(sala["piantina"], pren, s2), "pezzi cambiati").ok
    esiti = verificatore.verifica(sala["piantina"], pren, sol)
    assert all(e.ok for e in esiti), [(e.nome, e.errori) for e in esiti if not e.ok]
    assert _esito(esiti, "tutti i quadrati del disegno").dettaglio.startswith("29/29")
    from ristorante.mappa_libera import genera_html_variante
    html = genera_html_variante(sala, pren, sol, "PASS")
    assert "Da preparare in sala" in html and "sedie-nuove" in html


def test_sala_vera_una_accettata_cambia_tavolo_e_resta_accettata():
    """Due gruppi da 10 confermati nel primo turno occupano tondo e lungo; il secondo turno è pieno uguale. Un gruppo
    da 20 nel primo turno entra solo nel lungo: chi ci stava cambia tavolo (sul tondo o sul tavolo nuovo che propone il
    motore), resta accettato e nel suo turno, e il registro lo dice."""
    from ristorante.libera_varianti import accetta_in_ordine_varianti
    sala = carica_sala(PIANTINA)
    pren = serata(("A", "Primi", 10, "20:00"), ("B", "Secondi", 10, "20:00"), ("D", "Lunghi2", 20, "21:30"),
                  ("E", "Tondi2", 10, "21:30"), ("C", "Grandi", 20, "20:00"))
    ist = costruisci_istanza(sala, pren)
    sol = accetta_in_ordine_varianti(ist, sala, pren)
    assert sol["accettazione"]["accettate"] == 5, [(r["nome"], r["esito"], r["stato_solver"]) for r in sol["registro"]]
    turno = {r["id"]: r["turno"] for r in sol["assegnazioni"]}
    assert turno["A"] == turno["B"] == turno["C"] == "primo"
    cambiati = [r for r in (_rec(sol, "A"), _rec(sol, "B")) if r["tavolo_cambiato"]]
    assert cambiati, [(r["nome"], r["tavolo_alla_conferma"], r["tavolo_finale"]) for r in sol["registro"]]
    assert all(r["esito"] == "accettata" for r in cambiati)
    assert _rec(sol, "C")["cambiano_tavolo"]                     # chi ha ceduto il posto, scritto alla conferma di C
    assert sol["accettazione"]["tavoli_cambiati"] >= 1
