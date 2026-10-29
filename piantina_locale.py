"""Piantina in locale: si modifica olimpo/piantina.html da questo PC e "Salva" riscrive direttamente il file del repo.

    piantina_locale.cmd            (oppure: python piantina_locale.py)

Apre il browser su http://127.0.0.1:8770/piantina.html (se la porta è occupata, sulla prima libera dopo). La pagina si
accorge da sola di essere servita da qui: sala sbloccata, pulsante Salva (anche Ctrl+S), niente "Manda a Giacomo".
Per fermare il server: Ctrl+C. Il backup è git: non si fanno copie del file.

Solo libreria standard. Il server ascolta solo su 127.0.0.1 e serve solo la piantina; /__salva accetta solo richieste
che arrivano dalla pagina stessa (intestazione X-Piantina, Host e Origin del server, corpo fino a 2 MB, un solo blocco
<script type="application/json" id="sala"> con JSON valido e una lista "tavoli") e scrive in modo atomico.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
import webbrowser
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

INDIRIZZO = "127.0.0.1"
PORTA = 8770
PORTE_PROVATE = 20                      # da PORTA in su: la prima libera
LIMITE_CORPO = 2 * 1024 * 1024          # un salvataggio più grande non è una piantina
LIMITE_SCARTO = 16 * 1024 * 1024        # quanto si legge e si butta di un corpo troppo grande, prima di rispondere
INTESTAZIONE = "X-Piantina"             # senza, una pagina di un altro sito non può nemmeno provare: serve un preflight CORS
VALORE = "salva"
FILE_PREDEFINITO = Path(__file__).resolve().parent / "olimpo" / "piantina.html"


class ErroreSalvataggio(Exception):
    def __init__(self, codice: int, messaggio: str):
        super().__init__(messaggio)
        self.codice, self.messaggio = codice, messaggio


class _CercaBlocchi(HTMLParser):
    """I blocchi <script id="sala">. Il programma della pagina contiene il testo del tag come stringa JS: per il parser è
    dentro un <script>, quindi non lo vede come un tag (un semplice conteggio del testo ne troverebbe due)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.dentro, self.testo, self.blocchi = False, [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and a.get("id") == "sala":
            self.dentro = True
            self.testo = []
            self.blocchi.append((a.get("type"), self.testo))

    def handle_endtag(self, tag):
        if tag == "script":
            self.dentro = False

    def handle_data(self, data):
        if self.dentro:
            self.testo.append(data)


def controlla_pagina(testo: str) -> dict:
    """Il JSON della sala, se la pagina ha esattamente un blocco valido; altrimenti ErroreSalvataggio(400)."""
    p = _CercaBlocchi()
    try:
        p.feed(testo)
        p.close()
    except Exception:                          # il parser di HTML non dovrebbe mai fallire, ma un corpo storto non deve fermare il server
        raise ErroreSalvataggio(400, "il file non si legge come una pagina HTML") from None
    if len(p.blocchi) != 1:
        raise ErroreSalvataggio(400, f'atteso un solo blocco <script id="sala">, trovati {len(p.blocchi)}')
    tipo, parti = p.blocchi[0]
    if tipo != "application/json":
        raise ErroreSalvataggio(400, 'il blocco "sala" non è di tipo application/json')
    try:
        dati = json.loads("".join(parti))
    except ValueError as e:
        raise ErroreSalvataggio(400, f"il blocco dei dati non è JSON valido ({e})") from None
    if not isinstance(dati, dict) or not isinstance(dati.get("tavoli"), list):
        raise ErroreSalvataggio(400, 'nel blocco dei dati manca la lista "tavoli"')
    return dati


def scrivi_atomico(percorso: Path, dati: bytes) -> None:
    """File temporaneo nella stessa cartella e poi os.replace: o c'è il file vecchio o c'è il nuovo, mai uno a metà."""
    fd, tmp = tempfile.mkstemp(dir=percorso.parent, prefix=percorso.name + ".", suffix=".tmp")      # *.tmp è in .gitignore
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(dati)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp, percorso.stat().st_mode & 0o777)
        except OSError:
            pass
        for tentativo in range(5):               # su Windows, se qualcuno sta leggendo il file proprio ora, replace può negarsi
            try:
                os.replace(tmp, percorso)
                return
            except PermissionError:
                if tentativo == 4:
                    raise
                time.sleep(0.1)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Gestore(BaseHTTPRequestHandler):
    server_version = "PiantinaLocale"
    protocol_version = "HTTP/1.0"              # una richiesta per connessione: un corpo non letto non sporca la richiesta dopo
    timeout = 30                               # una connessione ferma (il browser ne apre in anticipo) non tiene un thread per sempre

    def log_message(self, *args):              # niente riga per ogni richiesta (favicon compresa): si scrive solo il salvataggio
        pass

    def _rispondi(self, codice: int, corpo: bytes, tipo: str) -> None:
        self.send_response(codice)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _json(self, codice: int, dati: dict) -> None:
        self._rispondi(codice, json.dumps(dati, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _testo(self, codice: int, testo: str) -> None:
        self._rispondi(codice, testo.encode("utf-8"), "text/plain; charset=utf-8")

    def _host_giusto(self) -> bool:             # contro il DNS rebinding: l'indirizzo che il browser ha usato deve essere il nostro
        return (self.headers.get("Host") or "").lower() in self.server.host_ammessi

    def _percorso(self) -> str:
        return unquote(urlsplit(self.path).path)

    def do_GET(self):
        if not self._host_giusto():
            return self._testo(403, "Indirizzo non ammesso.")
        p = self._percorso()
        if p == "/__locale":
            return self._json(200, {"locale": True})
        if p == "/favicon.ico":                            # il browser lo chiede sempre: risposta vuota, così la console non segna un errore
            return self._rispondi(204, b"", "image/x-icon")
        if p in ("/", "/" + self.server.file.name):       # solo la piantina: il resto, anche con "..", non esiste
            try:
                pagina = self.server.file.read_bytes()
            except OSError:
                return self._testo(500, "Non riesco a leggere il file della piantina.")
            return self._rispondi(200, pagina, "text/html; charset=utf-8")
        self._testo(404, "Non trovato.")

    do_HEAD = do_GET

    def do_OPTIONS(self):                       # nessun permesso CORS: il preflight di un altro sito fallisce
        self._testo(403, "Non consentito.")

    def do_POST(self):
        if self._percorso() != "/__salva":
            return self._testo(404, "Non trovato.")
        try:
            self._salva()
        except ErroreSalvataggio as e:
            self._json(e.codice, {"ok": False, "errore": e.messaggio})
        except OSError as e:
            self._json(500, {"ok": False, "errore": f"non riesco a scrivere il file ({e.strerror or e})"})

    def _leggi_corpo(self, n: int) -> bytes | None:
        """Il corpo di n byte; None se è oltre il limite. Si legge (e si butta) comunque fino a un tetto: su Windows un corpo
        rimasto nel socket fa partire un RST alla chiusura e il client non vede più la risposta."""
        if n > LIMITE_CORPO:
            resto = min(n, LIMITE_SCARTO)
            while resto > 0:
                pezzo = self.rfile.read(min(65536, resto))
                if not pezzo:
                    break
                resto -= len(pezzo)
            return None
        return self.rfile.read(n)

    def _salva(self) -> None:
        s = self.server
        lunghezza = self.headers.get("Content-Length", "")
        n = int(lunghezza) if lunghezza.isascii() and lunghezza.isdigit() and not self.headers.get("Transfer-Encoding") else -1
        corpo = self._leggi_corpo(n) if n >= 0 else b""
        if (not self._host_giusto() or self.headers.get("Origin") not in s.origini_ammesse
                or self.headers.get(INTESTAZIONE) != VALORE):
            raise ErroreSalvataggio(403, "richiesta non ammessa: il salvataggio funziona solo dalla pagina servita da qui")
        if n < 0:
            raise ErroreSalvataggio(411, "serve la lunghezza del corpo")
        if corpo is None:
            raise ErroreSalvataggio(413, f"il file è troppo grande (oltre {LIMITE_CORPO // (1024 * 1024)} MB)")
        if len(corpo) != n:
            raise ErroreSalvataggio(400, "il corpo è arrivato incompleto")
        try:
            testo = corpo.decode("utf-8")
        except UnicodeDecodeError:
            raise ErroreSalvataggio(400, "il file non è UTF-8") from None
        controlla_pagina(testo)
        with s.blocco_scrittura:
            scrivi_atomico(s.file, corpo)
        print(f"{time.strftime('%H:%M:%S')}  salvata ({n} byte) in {s.file}", flush=True)
        self._json(200, {"ok": True, "byte": n})


class Server(ThreadingHTTPServer):
    allow_reuse_address = False                # su Windows SO_REUSEADDR permette di agganciarsi a una porta già occupata
    daemon_threads = True

    def __init__(self, file: Path, porta: int):
        self.file = file
        self.blocco_scrittura = threading.Lock()
        super().__init__((INDIRIZZO, porta), Gestore)
        self.porta = self.server_address[1]
        self.host_ammessi = {f"{INDIRIZZO}:{self.porta}", f"localhost:{self.porta}"}
        self.origini_ammesse = {"http://" + h for h in self.host_ammessi}

    def server_bind(self):                     # HTTPServer.server_bind chiede il nome del computer (getfqdn): su Windows può durare secondi
        import socketserver
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = INDIRIZZO, self.server_address[1]


def crea_server(file: Path, porta: int = PORTA, porte_provate: int = 1) -> Server:
    """Il server sulla prima porta libera tra `porta` e `porta + porte_provate - 1` (porta 0: la sceglie il sistema)."""
    file = Path(file).resolve()
    if not file.is_file():
        raise SystemExit(f"Non trovo il file della piantina: {file}")
    try:
        controlla_pagina(file.read_text(encoding="utf-8"))
    except ErroreSalvataggio as e:
        raise SystemExit(f"Il file {file} non è una piantina valida: {e.messaggio}") from None
    ultimo = None
    for p in range(porta, porta + (porte_provate if porta else 1)):
        try:
            return Server(file, p)
        except OSError as e:
            ultimo = e
    raise SystemExit(f"Nessuna porta libera da {porta} a {porta + porte_provate - 1}: {ultimo}")


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    a = argparse.ArgumentParser(description="Modifica la piantina da questo PC e salva direttamente nel file del repo.")
    a.add_argument("--file", default=str(FILE_PREDEFINITO), help="la piantina (predefinito: olimpo/piantina.html)")
    a.add_argument("--porta", type=int, default=PORTA, help=f"porta di partenza (predefinita {PORTA}; se è occupata, la prima libera dopo)")
    a.add_argument("--no-browser", action="store_true", help="non aprire il browser")
    args = a.parse_args(argv)
    server = crea_server(Path(args.file), args.porta, PORTE_PROVATE)
    url = f"http://{INDIRIZZO}:{server.porta}/{server.file.name}"
    print(f"Piantina locale: {url}", flush=True)
    print(f"Salva nel file: {server.file}", flush=True)
    print("Per fermare: Ctrl+C", flush=True)
    if not args.no_browser:
        webbrowser.open(url)                    # il server ha già la porta in ascolto: la richiesta aspetta serve_forever
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nFermato.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
