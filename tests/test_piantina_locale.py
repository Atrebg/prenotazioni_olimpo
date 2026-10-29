"""Il server locale della piantina (piantina_locale.py): serve solo la pagina, salva solo da lì e scrive in modo atomico.

Si lavora sempre su una COPIA della piantina in una cartella temporanea: il file vero non si tocca.
"""
import hashlib
import http.client
import json
import os
import socket
import threading

import pytest
from conftest import RADICE

import piantina_locale
from piantina_locale import ErroreSalvataggio, controlla_pagina, crea_server

PIANTINA = RADICE / "olimpo" / "piantina.html"
APERTURA = '<script type="application/json" id="sala">'


def sha(percorso) -> str:
    return hashlib.sha256(percorso.read_bytes()).hexdigest()


def con_blocco(testo: str, modifica) -> str:
    """La pagina con il blocco dei dati cambiato da `modifica(dati)` (il blocco vero è il primo: il secondo è testo del programma)."""
    i = testo.index(APERTURA) + len(APERTURA)
    j = testo.index("</script>", i)
    dati = json.loads(testo[i:j])
    modifica(dati)
    return testo[:i] + "\n" + json.dumps(dati, ensure_ascii=False, indent=1) + "\n" + testo[j:]


class Prova:
    """Il server in un thread su una porta libera, con la sua copia della piantina."""

    def __init__(self, cartella):
        self.cartella = cartella
        self.file = cartella / "piantina.html"
        self.file.write_bytes(PIANTINA.read_bytes())
        self.testo = self.file.read_text(encoding="utf-8")
        self.server = crea_server(self.file, 0)
        self.porta = self.server.porta
        self.filo = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.filo.start()

    def chiudi(self):
        self.server.shutdown()
        self.server.server_close()
        self.filo.join(5)

    def intestazioni(self, **altre):
        h = {"X-Piantina": "salva", "Origin": f"http://127.0.0.1:{self.porta}", "Content-Type": "text/html;charset=utf-8"}
        h.update(altre)
        return {k: v for k, v in h.items() if v is not None}

    def chiedi(self, metodo, percorso, corpo=None, intestazioni=None):
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=20)
        try:
            c.request(metodo, percorso, body=corpo, headers=intestazioni or {})
            r = c.getresponse()
            return r.status, dict(r.getheaders()), r.read()
        finally:
            c.close()

    def salva(self, corpo, **altre):
        """POST /__salva con le intestazioni giuste (`altre` le cambia; il valore None le toglie)."""
        if isinstance(corpo, str):
            corpo = corpo.encode("utf-8")
        return self.chiedi("POST", "/__salva", corpo, self.intestazioni(**altre))


@pytest.fixture
def prova(tmp_path):
    cartella = tmp_path / "olimpo"
    cartella.mkdir()
    p = Prova(cartella)
    yield p
    p.chiudi()


def test_pagina_locale_e_indirizzo_solo_127(prova):
    assert prova.server.server_address[0] == "127.0.0.1"
    for percorso in ("/", "/piantina.html"):
        stato, h, corpo = prova.chiedi("GET", percorso)
        assert stato == 200 and corpo == prova.file.read_bytes()
        assert h["Content-Type"].startswith("text/html") and h["Cache-Control"] == "no-store"
    stato, h, corpo = prova.chiedi("GET", "/__locale")
    assert stato == 200 and json.loads(corpo) == {"locale": True}
    assert "Access-Control-Allow-Origin" not in h
    # anche con "localhost" come indirizzo (è l'altro nome ammesso)
    stato, _, _ = prova.chiedi("GET", "/__locale", intestazioni={"Host": f"localhost:{prova.porta}"})
    assert stato == 200


@pytest.mark.parametrize("percorso", [
    "/../segreto.txt", "/%2e%2e/segreto.txt", "/..%2fsegreto.txt", "/piantina.html/../../segreto.txt", "/segreto.txt",
    "/olimpo/piantina.html", "/favicon.ico/", "//segreto.txt", "/piantina.html%00", "/__salva", "/__LOCALE", "/piantina.html/",
    "/../README.md", "/..\\segreto.txt",
])
def test_fuori_dalla_piantina_non_esiste(prova, percorso):
    (prova.cartella.parent / "segreto.txt").write_text("fuori dalla cartella", encoding="utf-8")
    (prova.cartella / "segreto.txt").write_text("nella cartella, ma non è la piantina", encoding="utf-8")
    stato, _, corpo = prova.chiedi("GET", percorso)
    assert stato == 404 and b"cartella" not in corpo


def test_favicon_risposta_vuota_senza_errore(prova):
    stato, _, corpo = prova.chiedi("GET", "/favicon.ico")
    assert stato == 204 and corpo == b""


def test_host_estraneo_rifiutato_anche_in_lettura(prova):
    for host in ("evil.example", f"evil.example:{prova.porta}", f"127.0.0.1:{prova.porta + 1}", ""):
        stato, _, corpo = prova.chiedi("GET", "/", intestazioni={"Host": host})
        assert stato == 403 and b"<html" not in corpo


def test_salvataggio_riuscito_scrive_il_file_e_la_pagina_lo_serve(prova):
    nuova = con_blocco(prova.testo, lambda d: d["tavoli"][3].update(x=d["tavoli"][3]["x"] + 5))
    assert nuova != prova.testo
    stato, h, corpo = prova.salva(nuova)
    assert stato == 200 and json.loads(corpo) == {"ok": True, "byte": len(nuova.encode("utf-8"))}
    assert prova.file.read_bytes() == nuova.encode("utf-8")
    assert prova.chiedi("GET", "/")[2] == nuova.encode("utf-8")
    assert os.listdir(prova.cartella) == ["piantina.html"]          # nessun file temporaneo rimasto
    assert "Access-Control-Allow-Origin" not in h


def test_salvataggio_accetta_anche_localhost_e_testi_accentati(prova):
    nuova = con_blocco(prova.testo, lambda d: d["tavoli"][0].update(note="panca fissa, è già così"))
    stato, _, _ = prova.salva(nuova, Origin=f"http://localhost:{prova.porta}", Host=f"localhost:{prova.porta}")
    assert stato == 200
    assert controlla_pagina(prova.file.read_text(encoding="utf-8"))["tavoli"][0]["note"] == "panca fissa, è già così"


@pytest.mark.parametrize("altre", [
    {"X-Piantina": None},                                   # senza intestazione
    {"X-Piantina": "altro"},
    {"X-Piantina": ""},
    {"Origin": "http://evil.example"},
    {"Origin": f"http://evil.example:{8770}"},
    {"Origin": None},                                       # il browser lo manda sempre su una POST: senza, non è la pagina
    {"Origin": "null"},                                     # pagina da file: o iframe senza origine
    {"Origin": "https://127.0.0.1:8770"},
    {"Host": "evil.example"},                               # DNS rebinding
])
def test_richieste_non_ammesse_403_e_file_invariato(prova, altre):
    altre = {k: (v.replace("8770", str(prova.porta)) if isinstance(v, str) else v) for k, v in altre.items()}
    prima = sha(prova.file)
    nuova = con_blocco(prova.testo, lambda d: d["tavoli"][3].update(x=1))
    stato, _, corpo = prova.salva(nuova, **altre)
    assert stato == 403 and json.loads(corpo)["ok"] is False
    assert sha(prova.file) == prima and os.listdir(prova.cartella) == ["piantina.html"]


def test_preflight_di_un_altro_sito_non_ha_permessi(prova):
    stato, h, _ = prova.chiedi("OPTIONS", "/__salva", intestazioni={
        "Origin": "http://evil.example", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-piantina"})
    assert stato == 403
    assert not any(k.lower().startswith("access-control-") for k in h)


def test_senza_lunghezza_del_corpo_411(prova):
    prima = sha(prova.file)
    with socket.create_connection(("127.0.0.1", prova.porta), timeout=10) as s:
        s.sendall((f"POST /__salva HTTP/1.0\r\nHost: 127.0.0.1:{prova.porta}\r\nOrigin: http://127.0.0.1:{prova.porta}\r\n"
                   "X-Piantina: salva\r\n\r\n").encode())
        risposta = b""
        while True:
            pezzo = s.recv(4096)
            if not pezzo:
                break
            risposta += pezzo
    assert risposta.startswith(b"HTTP/1.0 411") and sha(prova.file) == prima


def _senza_blocco(t):
    return "<!doctype html><html><body><p>niente</p></body></html>"


def _json_rotto(t):
    return t.replace(APERTURA + "\n{", APERTURA + "\n{ \"nome\": ", 1)


def _due_blocchi(t):
    return _in_coda(t, APERTURA + '{"tavoli": []}</' + "script>")


def _in_coda(t, testo):
    """`testo` prima dell'ultimo </body> (il primo è una stringa del programma, dentro il suo <script>)."""
    i = t.rindex("</body>")
    return t[:i] + testo + t[i:]


def _tipo_sbagliato(t):
    return t.replace(APERTURA, '<script type="text/plain" id="sala">', 1)


def _senza_tavoli(t):
    return con_blocco(t, lambda d: d.pop("tavoli"))


def _tavoli_non_lista(t):
    return con_blocco(t, lambda d: d.update(tavoli={"1": {}}))


def _json_non_oggetto(t):
    i = t.index(APERTURA) + len(APERTURA)
    return t[:i] + "[1, 2, 3]" + t[t.index("</script>", i):]


@pytest.mark.parametrize("fabbrica", [_senza_blocco, _json_rotto, _due_blocchi, _tipo_sbagliato, _senza_tavoli,
                                       _tavoli_non_lista, _json_non_oggetto, lambda t: ""])
def test_corpo_senza_blocco_valido_400_e_file_invariato(prova, fabbrica):
    prima = sha(prova.file)
    stato, _, corpo = prova.salva(fabbrica(prova.testo))
    assert stato == 400 and json.loads(corpo)["ok"] is False and json.loads(corpo)["errore"]
    assert sha(prova.file) == prima and os.listdir(prova.cartella) == ["piantina.html"]


def test_corpo_non_utf8_400(prova):
    prima = sha(prova.file)
    stato, _, _ = prova.salva(b"\xff\xfe\x00 non e' utf-8 " + prova.testo.encode("utf-8")[:100])
    assert stato == 400 and sha(prova.file) == prima


def test_corpo_da_3_mb_413_e_file_invariato(prova):
    prima = sha(prova.file)
    grande = prova.testo + " " * (3 * 1024 * 1024)               # un blocco valido, ma enorme
    stato, _, corpo = prova.salva(grande)
    assert stato == 413 and json.loads(corpo)["ok"] is False
    assert sha(prova.file) == prima and os.listdir(prova.cartella) == ["piantina.html"]
    # appena sotto il limite (2 MB) passa
    stato, _, _ = prova.salva(prova.testo + " " * (2 * 1024 * 1024 - len(prova.testo.encode("utf-8"))))
    assert stato == 200


def test_il_blocco_nel_testo_del_programma_non_e_un_secondo_blocco():
    testo = PIANTINA.read_text(encoding="utf-8")
    assert testo.count(APERTURA) >= 2                          # il tag vero e la stringa del programma che genera il file
    assert isinstance(controlla_pagina(testo)["tavoli"], list)
    with pytest.raises(ErroreSalvataggio):
        controlla_pagina(_in_coda(testo, APERTURA + "{}</" + "script>"))


def test_scrittura_atomica_il_file_vecchio_resta_fino_allo_scambio(prova, monkeypatch):
    vecchio = prova.file.read_bytes()
    nuova = con_blocco(prova.testo, lambda d: d["tavoli"][3].update(x=1)).encode("utf-8")
    visto = {}
    vera = os.replace

    def spia(sorgente, destinazione):
        visto["tmp_nella_stessa_cartella"] = os.path.dirname(os.path.abspath(sorgente)) == str(prova.cartella)
        visto["tmp_completo"] = open(sorgente, "rb").read() == nuova
        visto["vecchio_ancora_intero"] = open(destinazione, "rb").read() == vecchio
        return vera(sorgente, destinazione)

    monkeypatch.setattr(piantina_locale.os, "replace", spia)
    assert prova.salva(nuova)[0] == 200
    assert visto == {"tmp_nella_stessa_cartella": True, "tmp_completo": True, "vecchio_ancora_intero": True}
    assert prova.file.read_bytes() == nuova


def test_scrittura_fallita_500_file_invariato_e_nessun_temporaneo(prova, monkeypatch):
    prima = sha(prova.file)

    def rotta(sorgente, destinazione):
        raise PermissionError(13, "negato")

    monkeypatch.setattr(piantina_locale.os, "replace", rotta)
    monkeypatch.setattr(piantina_locale.time, "sleep", lambda s: None)
    stato, _, corpo = prova.salva(con_blocco(prova.testo, lambda d: d["tavoli"][3].update(x=1)))
    assert stato == 500 and json.loads(corpo)["ok"] is False
    assert sha(prova.file) == prima and os.listdir(prova.cartella) == ["piantina.html"]


def test_porta_occupata_si_passa_alla_successiva(tmp_path):
    file = tmp_path / "piantina.html"
    file.write_bytes(PIANTINA.read_bytes())
    with socket.socket() as occupata:
        occupata.bind(("127.0.0.1", 0))
        occupata.listen(1)
        porta = occupata.getsockname()[1]
        srv = crea_server(file, porta, 5)
        try:
            assert porta < srv.porta < porta + 5
        finally:
            srv.server_close()


def test_all_avvio_un_file_che_non_e_una_piantina_si_rifiuta(tmp_path):
    assert not (tmp_path / "manca.html").exists()
    with pytest.raises(SystemExit):
        crea_server(tmp_path / "manca.html", 0)
    altro = tmp_path / "altro.html"
    altro.write_text("<html><body>niente</body></html>", encoding="utf-8")
    with pytest.raises(SystemExit):
        crea_server(altro, 0)
