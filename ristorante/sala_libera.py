"""Geometria della sala vera per la disposizione LIBERA dei tavoli mobili (in cm), letta dalla piantina disegnata.

Unità: la piantina è in unità del disegno, 1 unità = lato_quadrato_cm / 32 cm (come nell'editor, dove il lato di un
quadrato è LATO = 32 unità): con 80 cm, 1 m = 40 unità. Qui tutto è in cm, con la stessa origine del disegno, x verso
destra e y verso il basso.

Che cosa si muove: i quadrati (i singoli e quelli dentro ogni blocco) non fissi sono l'inventario; si dispongono in file
di k quadrati (k <= `k_max`), a 0° o a 90°. Tutto il resto (panche, tondi, lungo, rettangolari) resta dov'è, con i suoi
posti e con la zona delle sue sedie (`sedie_cm` su ogni lato: quali lati abbiano le sedie la piantina non lo dice).

Regole (le soglie dell'editor della piantina dove ci sono, così editor e motore dicono la stessa cosa):
- sedia: 1 per ogni lato da un quadrato (lato_quadrato_cm) che ha davanti una zona libera profonda `sedie_cm`
  (SEDIE_CM = 50 dell'editor, "con le sedie ne servono 50"); un lato contro un muro o un ostacolo non ha sedie;
- tavolo e zone delle sedie dentro la faccia interna dei muri (spessore dei muri della piantina), lontani almeno
  `tolleranza_cm` (2,5 cm = 1 unità, la soglia "si toccano" dell'editor) da muri, ostacoli, porte con lo spazio da
  lasciare davanti (spazio_libero_cm), passaggi e ingresso;
- tavolo e sedie fuori dalla zona delle sedie dei tavoli fissi (`sedie_cm` su tutti i lati) e fuori dai corridoi di
  servizio: il percorso più corto dall'ingresso a ogni porta (cucina, bagni), largo `corridoio_cm`, resta libero;
- corridoio: ogni tavolo mobile ha su almeno un lato una zona d'accesso profonda `corridoio_cm` (oltre le sedie) senza
  altri tavoli né sedie, muri, ostacoli o tavoli fissi; ogni tavolo e ogni porta si raggiungono dall'ingresso con un
  corridoio largo `corridoio_cm` (controllo a griglia in `irraggiungibili`, e nella verifica indipendente su griglia
  fine). Ripiego più stretto, solo se serve: `corridoio_cm` anche tra ogni coppia di tavoli e lungo muri e ostacoli.
Griglia del modello: celle di `griglia_cm` (10 cm), arrotondamento conservativo: una cella è "occupata" se tocca la
cosa che la occupa, quindi una disposizione valida sulla griglia è valida anche in cm.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

LATO_U = 32                      # lato di un quadrato nel disegno (editor: LATO)
SEDIE_CM = 50                    # editor: SEDIE_CM
SPAZIO_PORTE_CM = 90             # editor: spazio_libero_cm di default di porte e ingresso
SPESSORE_MURO_CM = 10            # editor: metaMuro, spessore se manca
TONDO_R_U = 16                   # editor: raggio di un tondo se manca
TOLLERANZA_U = 1                 # editor: "si toccano" sotto 1 unità
TIPI_MOBILI = ("quadrato", "blocco")


# ---------------------------------------------------------------------------- geometria di base (cm)

def ruota(px: float, py: float, cx: float, cy: float, gradi: float) -> tuple[float, float]:
    a = math.radians(gradi or 0)
    dx, dy = px - cx, py - cy
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)


def rett_ruotato(cx: float, cy: float, w: float, h: float, rot: float) -> list[tuple[float, float]]:
    """Vertici del rettangolo w x h centrato in (cx, cy), ruotato di `rot` gradi (come rettRuotato dell'editor)."""
    return [ruota(cx + sx * w / 2, cy + sy * h / 2, cx, cy, rot) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def dentro(p: tuple[float, float], poli: list) -> bool:
    c = False
    j = len(poli) - 1
    for i in range(len(poli)):
        (xi, yi), (xj, yj) = poli[i], poli[j]
        if (yi > p[1]) != (yj > p[1]) and p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def dist_punto_seg(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ll if ll else 0.0
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def dist_punto_box(p, b) -> float:
    dx = max(b[0] - p[0], 0.0, p[0] - b[2])
    dy = max(b[1] - p[1], 0.0, p[1] - b[3])
    return math.hypot(dx, dy)


def _taglia_seg_box(a, b, box) -> bool:
    """Il segmento ab tocca il box (x0, y0, x1, y1)? (Liang-Barsky)"""
    x0, y0, x1, y1 = box
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return False
        else:
            r = q / p
            if p < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
            if t0 > t1:
                return False
    return True


def dist_box_seg(box, a, b) -> float:
    if _taglia_seg_box(a, b, box):
        return 0.0
    x0, y0, x1, y1 = box
    return min(dist_punto_box(a, box), dist_punto_box(b, box),
               *(dist_punto_seg(c, a, b) for c in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))))


def dist_box_poli(box, poli) -> float:
    """Distanza tra un box allineato e un poligono convesso (0 se si toccano o si sovrappongono)."""
    x0, y0, x1, y1 = box
    if any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in poli) or dentro(((x0 + x1) / 2, (y0 + y1) / 2), poli):
        return 0.0
    n = len(poli)
    return min(dist_box_seg(box, poli[i], poli[(i + 1) % n]) for i in range(n))


@dataclass(frozen=True)
class Forma:
    """Una cosa ferma nella sala: poligono convesso, cerchio, o spezzata con mezzo spessore (muro)."""
    nome: str
    tipo: str                      # "poli" | "cerchio" | "linea"
    punti: tuple = ()              # poli/linea: vertici; cerchio: ((cx, cy),)
    r: float = 0.0                 # cerchio: raggio; linea: mezzo spessore

    def bbox(self) -> tuple[float, float, float, float]:
        if self.tipo == "cerchio":
            (cx, cy), = self.punti
            return cx - self.r, cy - self.r, cx + self.r, cy + self.r
        xs, ys = [p[0] for p in self.punti], [p[1] for p in self.punti]
        m = self.r if self.tipo == "linea" else 0.0
        return min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m

    def dist_box(self, box) -> float:
        """Distanza tra il box e la cosa (per un muro: dalla sua faccia)."""
        if self.tipo == "cerchio":
            return max(0.0, dist_punto_box(self.punti[0], box) - self.r)
        if self.tipo == "linea":
            pts = self.punti
            return max(0.0, min(dist_box_seg(box, pts[i], pts[i + 1]) for i in range(len(pts) - 1)) - self.r)
        return dist_box_poli(box, self.punti)


# ---------------------------------------------------------------------------- la sala

@dataclass
class TavoloFisso:
    id: str
    tipo: str
    posti: int
    corpo: Forma                   # piano del tavolo
    x_u: float                     # centro nel disegno
    y_u: float


@dataclass
class SalaLibera:
    dati: dict
    griglia_cm: int = 10
    sedie_cm: float = SEDIE_CM
    corridoio_cm: float = 60
    k_max: int = 4
    # derivati
    cpu: float = 2.5
    lato_cm: float = 80
    tolleranza_cm: float = 2.5
    W: int = 0
    H: int = 0
    stanza: list = field(default_factory=list)            # poligono del muro perimetrale (asse), chiuso dall'ingresso
    muri: list = field(default_factory=list)              # Forma "linea" (asse + mezzo spessore)
    varco: tuple | None = None                            # tratto senza muro del perimetro (l'ingresso)
    vietate: list = field(default_factory=list)           # Forma: ostacoli, porte + spazio davanti, passaggi, ingresso
    ostacoli: list = field(default_factory=list)          # Forma: solo gli ostacoli (per il cammino)
    fissi: list = field(default_factory=list)             # TavoloFisso
    n_quadrati: int = 0                                   # inventario: quadrati mobili
    origine_quadrati: list = field(default_factory=list)  # (id del tavolo della piantina, quadrati)
    sorgente: Forma | None = None                         # zona davanti all'ingresso, dentro la sala
    porte_zone: dict = field(default_factory=dict)        # nome porta -> zone davanti (dentro la sala)
    misure: list = field(default_factory=list)            # misure usate, con la fonte (piantina o default)

    def __post_init__(self):
        d = self.dati
        g = self.griglia_cm
        scala = d.get("scala") or {}
        self.lato_cm = float(scala.get("lato_quadrato_cm") or 80)
        self.cpu = self.lato_cm / LATO_U
        self.tolleranza_cm = TOLLERANZA_U * self.cpu
        cpu = self.cpu
        M = self.misure
        M.append({"cosa": "lato di un quadrato", "valore": f"{self.lato_cm:g} cm",
                  "fonte": "piantina (scala.lato_quadrato_cm)" if scala.get("lato_quadrato_cm") else "default dell'editor (80 cm)"})
        M.append({"cosa": "unità del disegno", "valore": f"{cpu:g} cm (1 m = {100 / cpu:g} unità)",
                  "fonte": "lato del quadrato / 32 unità, come nell'editor"})

        # ---- muri: il perimetrale è la spezzata che racchiude l'area più grande
        muri = [m for m in d.get("muri") or [] if isinstance(m, dict) and len(m.get("punti") or []) >= 2]
        if not muri:
            raise ValueError("la piantina non ha muri: serve il contorno della sala")

        def area(pts):
            return abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                           for i in range(len(pts)))) / 2
        cm_pts = [[(float(p[0]) * cpu, float(p[1]) * cpu) for p in m["punti"]] for m in muri]
        ip = max(range(len(muri)), key=lambda i: area(cm_pts[i]))
        for i, (m, pts) in enumerate(zip(muri, cm_pts)):
            sp = m.get("spessore_cm")
            if sp is None:
                M.append({"cosa": f"spessore del muro {i + 1}", "valore": f"{SPESSORE_MURO_CM} cm", "fonte": "default dell'editor"})
            self.muri.append(Forma("muro perimetrale" if i == ip else "muro interno", "linea", tuple(pts),
                                   float(sp if sp is not None else SPESSORE_MURO_CM) / 2))
        sp_txt = ", ".join(f"{2 * m.r:g} cm" for m in self.muri)
        M.append({"cosa": "spessore dei muri", "valore": sp_txt, "fonte": "piantina (spessore_cm)"})
        per = cm_pts[ip]
        self.stanza = list(per)
        if per[0] != per[-1]:
            self.varco = (per[-1], per[0])
        else:
            self.stanza = per[:-1]

        # ---- contorno della sala (rettangolo dell'editor)
        s = d.get("sala") or {}
        sx, sy = float(s.get("x", 0)) * cpu, float(s.get("y", 0)) * cpu
        sw, sh = float(s.get("w", 0)) * cpu, float(s.get("h", 0)) * cpu
        if not sw or not sh:
            xs, ys = [p[0] for p in per], [p[1] for p in per]
            sx, sy, sw, sh = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        self.contorno = (sx, sy, sx + sw, sy + sh)
        self.W = int(math.ceil((sx + sw) / g)) + 1
        self.H = int(math.ceil((sy + sh) / g)) + 1

        # ---- ostacoli, porte (con lo spazio davanti), ingresso, passaggi
        for o in d.get("ostacoli") or []:
            f = self._forma_zona(o, str(o.get("nome") or o.get("tipo") or "ostacolo"))
            if f:
                self.vietate.append(f)
                self.ostacoli.append(f)
        for p in d.get("porte") or []:
            nome = str(p.get("nome") or "porta")
            self.porte_zone[nome] = []
            for f in self._porta(p, nome, M):
                self.vietate.append(f)
                if f.nome.endswith("(davanti)") and dentro(_centro(f), self.stanza) and \
                        not any(o.dist_box(_box_punto(_centro(f))) == 0 for o in self.ostacoli):
                    self.porte_zone[nome].append(f)
        ing = d.get("ingresso")
        if isinstance(ing, dict):
            for f in self._porta(ing, "ingresso", M):
                self.vietate.append(f)
                if f.nome.endswith("(davanti)") and dentro(_centro(f), self.stanza):
                    self.sorgente = f
        for p in d.get("passaggi") or []:
            nome = str(p.get("nome") or "passaggio")
            if p.get("spazio_libero_cm") is not None:      # passaggio con lo spazio davanti da lasciare (come una porta)
                self.vietate += self._porta(p, nome, M)
                continue
            f = self._forma_zona(p, nome)
            if f:
                self.vietate.append(f)

        # ---- tavoli: fissi (fermi) e quadrati mobili (inventario)
        def_panche = []
        for t in d.get("tavoli") or []:
            tid, tipo = str(t["id"]), t.get("tipo")
            if tipo in TIPI_MOBILI and not t.get("fisso"):
                k = int(t.get("moduli") or 1) if tipo == "blocco" else 1
                self.n_quadrati += k
                self.origine_quadrati.append((tid, k))
                continue
            cx, cy = float(t["x"]) * cpu, float(t["y"]) * cpu
            if tipo == "tondo":
                r_u = t.get("r")
                if r_u is None:
                    M.append({"cosa": f"raggio del tondo {tid}", "valore": f"{TONDO_R_U * cpu:g} cm",
                              "fonte": "default dell'editor (16 unità)"})
                corpo = Forma(f"tavolo {tid}", "cerchio", ((cx, cy),), float(r_u if r_u is not None else TONDO_R_U) * cpu)
                M.append({"cosa": f"tondo {tid}", "valore": f"diametro {2 * corpo.r:g} cm",
                          "fonte": "piantina (r)" if r_u is not None else "default dell'editor"})
            else:
                if tipo == "blocco":
                    k = int(t.get("moduli") or 1)
                    L = k * LATO_U + (k - 1) * 2
                    wu, hu = (L, LATO_U) if t.get("verso") == "orizzontale" else (LATO_U, L)
                else:
                    wu, hu = t.get("w"), t.get("h")
                    if wu is None or hu is None:
                        def_panche.append(tid)
                    wu, hu = float(wu or LATO_U), float(hu or LATO_U)
                corpo = Forma(f"tavolo {tid}", "poli", tuple(rett_ruotato(cx, cy, wu * cpu, hu * cpu, float(t.get("rot") or 0))))
                if t.get("w") is not None and t.get("h") is not None:
                    M.append({"cosa": f"{tipo} {tid}", "valore": f"{wu * cpu:g} × {hu * cpu:g} cm", "fonte": "piantina (w, h)"})
            self.fissi.append(TavoloFisso(tid, str(tipo), int(t["posti"]), corpo, float(t["x"]), float(t["y"])))
        if def_panche:
            M.append({"cosa": f"tavoli fissi senza misure ({', '.join(def_panche)})", "valore": f"{LATO_U * cpu:g} × {LATO_U * cpu:g} cm",
                      "fonte": "default dell'editor (un quadrato, 32 × 32 unità)"})
        quad = [tid for tid, k in self.origine_quadrati]
        M.append({"cosa": f"quadrati mobili ({', '.join(quad)})", "valore": f"{self.lato_cm:g} × {self.lato_cm:g} cm ciascuno, "
                  f"{self.n_quadrati} in tutto", "fonte": "piantina (lato_quadrato_cm; nessuno ha w/h)"})
        M.append({"cosa": "file di quadrati uniti", "valore": f"k × {self.lato_cm:g} cm, senza spazio tra i quadrati",
                  "fonte": "scelta del motore (nel disegno dell'editor c'è uno spazio di 5 cm solo per vederli)"})
        M.append({"cosa": "zona delle sedie", "valore": f"{self.sedie_cm:g} cm da ogni lato con le sedie",
                  "fonte": "editor (SEDIE_CM = 50): non è nella piantina"})
        M.append({"cosa": "zona delle sedie dei tavoli fissi", "valore": f"{self.sedie_cm:g} cm su tutti i lati",
                  "fonte": "scelta del motore: la piantina non dice quali lati hanno le sedie"})
        M.append({"cosa": "corridoio per il personale", "valore": f"{self.corridoio_cm:g} cm (strade dall'ingresso alle porte, "
                  "raggiungibilità di ogni tavolo)", "fonte": "scelta del motore (default): non è nella piantina"})
        M.append({"cosa": "distanza minima da muri e ostacoli", "valore": f"{self.tolleranza_cm:g} cm",
                  "fonte": "editor (\"si toccano\" sotto 1 unità)"})
        M.append({"cosa": "griglia delle posizioni", "valore": f"{g} cm", "fonte": "scelta del motore"})
        M.append({"cosa": "rotazioni dei tavoli mobili", "valore": "0° e 90°", "fonte": "scelta del motore"})
        M.append({"cosa": "file più lunghe", "valore": f"{self.k_max} quadrati ({2 * self.k_max + 2} posti con tutti i lati liberi)",
                  "fonte": "scelta del motore"})
        self._griglie()

    # ---- pezzi della piantina come forme in cm
    def _forma_zona(self, o: dict, nome: str) -> Forma | None:
        if not all(k in o for k in ("x", "y", "w", "h")):
            return None
        cpu = self.cpu
        x, y, w, h = (float(o[k]) * cpu for k in ("x", "y", "w", "h"))
        rot = float(o.get("rot") or 0)
        if o.get("forma") == "tondo":            # ellisse: poligono circoscritto (prudente)
            k = 1 / math.cos(math.pi / 24)
            pts = [ruota(x + w / 2 + k * w / 2 * math.cos(i * math.pi / 12), y + h / 2 + k * h / 2 * math.sin(i * math.pi / 12),
                         x + w / 2, y + h / 2, rot) for i in range(24)]
            return Forma(nome, "poli", tuple(pts))
        return Forma(nome, "poli", tuple(rett_ruotato(x + w / 2, y + h / 2, w, h, rot)))

    def _porta(self, p: dict, nome: str, M: list) -> list[Forma]:
        """La porta e le due zone da lasciare libere davanti e dietro (come aperture() dell'editor)."""
        out = []
        f = self._forma_zona(p, nome)
        if f is None:
            return out
        out.append(f)
        cpu = self.cpu
        sl = p.get("spazio_libero_cm")
        if sl is None:
            M.append({"cosa": f"spazio davanti a {nome}", "valore": f"{SPAZIO_PORTE_CM} cm", "fonte": "default dell'editor"})
        else:
            M.append({"cosa": f"spazio davanti a {nome}", "valore": f"{float(sl):g} cm", "fonte": "piantina (spazio_libero_cm)"})
        s = float(SPAZIO_PORTE_CM if sl is None else sl)
        if s <= 0:
            return out
        x, y, w, h = (float(p[k]) * cpu for k in ("x", "y", "w", "h"))
        cx, cy, rot = x + w / 2, y + h / 2, float(p.get("rot") or 0)
        orizz = w >= h
        a = math.radians(rot)
        for v in (-1, 1):
            lx, ly = (0.0, v * (h / 2 + s / 2)) if orizz else (v * (w / 2 + s / 2), 0.0)
            zx, zy = cx + lx * math.cos(a) - ly * math.sin(a), cy + lx * math.sin(a) + ly * math.cos(a)
            out.append(Forma(f"{nome} (davanti)", "poli", tuple(rett_ruotato(zx, zy, w if orizz else s, s if orizz else h, rot))))
        return out

    # ---- griglie (celle da griglia_cm)
    def cella(self, i: int, j: int) -> tuple[float, float, float, float]:
        g = self.griglia_cm
        return i * g, j * g, (i + 1) * g, (j + 1) * g

    def _marca(self, occ, forma: Forma, soglia: float) -> None:
        """Segna le celle a distanza < soglia dalla forma (un muro: tratto per tratto, ognuno col suo riquadro)."""
        if forma.tipo == "linea" and len(forma.punti) > 2:
            for a, b in zip(forma.punti, forma.punti[1:]):
                self._marca(occ, Forma(forma.nome, "linea", (a, b), forma.r), soglia)
            return
        g = self.griglia_cm
        x0, y0, x1, y1 = forma.bbox()
        for j in range(max(0, int((y0 - soglia) // g)), min(self.H, int((y1 + soglia) // g) + 1)):
            riga = occ[j]
            for i in range(max(0, int((x0 - soglia) // g)), min(self.W, int((x1 + soglia) // g) + 1)):
                if not riga[i] and forma.dist_box(self.cella(i, j)) < soglia:
                    riga[i] = 1

    def marca_fisso(self, occ, corpo: Forma, soglia: float) -> None:
        """Segna le celle a distanza < soglia da un tavolo fisso raggiungibili dal tavolo senza passare da un muro: la
        zona delle sue sedie non passa dall'altra parte di un muro."""
        tmp = [[0] * self.W for _ in range(self.H)]
        self._marca(tmp, corpo, soglia)
        dentro_c = [[0] * self.W for _ in range(self.H)]
        self._marca(dentro_c, corpo, 1e-6)
        coda = deque((i, j) for j in range(self.H) for i in range(self.W) if dentro_c[j][i])
        visto = set(coda)
        while coda:
            i, j = coda.popleft()
            occ[j][i] = 1
            for a, b in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= a < self.W and 0 <= b < self.H and (a, b) not in visto and tmp[b][a] and not self._occ_muri[b][a]:
                    visto.add((a, b))
                    coda.append((a, b))

    def _fuori(self) -> list[list[int]]:
        """Celle non del tutto dentro il poligono della sala e il contorno (angoli fuori)."""
        g, W, H = self.griglia_cm, self.W, self.H
        dentro_ang = [[False] * (W + 1) for _ in range(H + 1)]
        n = len(self.stanza)
        for j in range(H + 1):
            y = j * g + 1e-6
            xs = []
            for a in range(n):
                (x1, y1), (x2, y2) = self.stanza[a], self.stanza[(a + 1) % n]
                if (y1 > y) != (y2 > y):
                    xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
            xs.sort()
            for a in range(0, len(xs) - 1, 2):
                for i in range(max(0, int(math.ceil(xs[a] / g))), min(W, int(xs[a + 1] // g)) + 1):
                    dentro_ang[j][i] = True
        cx0, cy0, cx1, cy1 = self.contorno
        occ = [[0] * W for _ in range(H)]
        for j in range(H):
            for i in range(W):
                x0, y0, x1, y1 = self.cella(i, j)
                if not (dentro_ang[j][i] and dentro_ang[j][i + 1] and dentro_ang[j + 1][i] and dentro_ang[j + 1][i + 1]) \
                        or x0 < cx0 or y0 < cy0 or x1 > cx1 or y1 > cy1:
                    occ[j][i] = 1
        return occ

    def _griglie(self) -> None:
        t = self.tolleranza_cm
        fuori = self._fuori()
        self._occ_muri = [r[:] for r in fuori]         # muri e fuori, senza tolleranza: le zone dei fissi si fermano qui
        for m in self.muri:
            self._marca(self._occ_muri, m, 1e-6)
        # per i tavoli mobili e le loro sedie: fuori, muri, cose vietate (con la tolleranza)
        self.occ_tavoli = [r[:] for r in fuori]
        for m in self.muri:
            self._marca(self.occ_tavoli, m, t)
        if self.varco:
            self._marca(self.occ_tavoli, Forma("ingresso", "linea", self.varco, 0.0), t)
        for f in self.vietate:
            self._marca(self.occ_tavoli, f, t)
        for f in self.fissi:                      # la zona delle sedie dei tavoli fissi
            self.marca_fisso(self.occ_tavoli, f.corpo, self.sedie_cm)
        # ripiego più stretto: zona sedie del fisso + mezzo corridoio (il mobile porta l'altra metà)
        self.occ_fissi = [[0] * self.W for _ in range(self.H)]
        for f in self.fissi:
            self.marca_fisso(self.occ_fissi, f.corpo, self.sedie_cm + self.corridoio_cm / 2)
        # per il cammino del personale: fuori, muri, ostacoli, tavoli fissi con la zona delle sedie
        self.occ_cammino = [r[:] for r in fuori]
        for m in self.muri:
            self._marca(self.occ_cammino, m, 1e-6)
        for f in self.ostacoli:
            self._marca(self.occ_cammino, f, 1e-6)
        for f in self.fissi:
            self.marca_fisso(self.occ_cammino, f.corpo, self.sedie_cm)
        self.base_raggiunti = None
        ok, _ = self._cammino([])
        self.base_raggiunti = ok          # tavoli fissi e porte raggiungibili nella sala senza tavoli mobili
        self.occ_servizio = [[0] * self.W for _ in range(self.H)]
        self.percorsi_servizio = {}
        self._tavoli_senza_strade = [r[:] for r in self.occ_tavoli]

    def riserva_strade(self, regioni: list[tuple[str, list]] | None = None) -> dict[str, list]:
        """Corridoi di servizio: il percorso più corto dall'ingresso a ogni porta (cucina, bagni) e al tavolo mobile del
        disegno più lontano dall'ingresso (all'Olimpo in fondo alla striscia), largo quanto il corridoio, resta libero
        da tavoli e sedie. `regioni` = i tavoli del disegno (corpi): i percorsi passano dove il disegno lascia i
        corridoi."""
        g = self.griglia_cm
        r = int(math.ceil(self.corridoio_cm / 2 / g))
        self.occ_tavoli = [riga[:] for riga in self._tavoli_senza_strade]
        self.occ_servizio = [[0] * self.W for _ in range(self.H)]
        self.percorsi_servizio = self._strade(regioni or [])
        for punti in self.percorsi_servizio.values():
            for i, j in punti:
                for jj in range(max(0, j - r), min(self.H, j + r)):
                    for ii in range(max(0, i - r), min(self.W, i + r)):
                        self.occ_servizio[jj][ii] = 1
        for j in range(self.H):
            for i in range(self.W):
                if self.occ_servizio[j][i]:
                    self.occ_tavoli[j][i] = 1
        return self.percorsi_servizio

    # ---- raggiungibilità (personale largo `corridoio_cm`), sulla griglia
    def _cammino(self, regioni: list[tuple[str, list]]) -> tuple[set, set]:
        """regioni: (id del tavolo mobile, box in celle (i0, j0, i1, j1) esclusi i1, j1: tavolo e sedie).
        Restituisce (raggiunti, da raggiungere ma non raggiunti) tra tavoli fissi, porte e tavoli mobili."""
        W, H, g = self.W, self.H, self.griglia_cm
        occ = [r[:] for r in self.occ_cammino]
        for _, boxes in regioni:
            for i0, j0, i1, j1 in boxes:
                for j in range(max(0, j0), min(H, j1)):
                    riga = occ[j]
                    for i in range(max(0, i0), min(W, i1)):
                        riga[i] = 1
        r = int(math.ceil(self.corridoio_cm / 2 / g))
        pref = [[0] * (W + 1) for _ in range(H + 1)]
        for j in range(H):
            acc, pj, pj1, oj = 0, pref[j], pref[j + 1], occ[j]
            for i in range(W):
                acc += oj[i]
                pj1[i + 1] = pj[i + 1] + acc

        def libero(i, j):        # il personale al punto (i*g, j*g): il quadrato di 2r x 2r celle intorno è tutto libero
            a0, b0, a1, b1 = i - r, j - r, i + r, j + r
            if a0 < 0 or b0 < 0 or a1 > W or b1 > H:
                return False
            return pref[b1][a1] - pref[b0][a1] - pref[b1][a0] + pref[b0][a0] == 0

        vis = [[False] * (W + 1) for _ in range(H + 1)]       # sui punti d'angolo delle celle
        coda = deque()
        if self.sorgente is not None:
            x0, y0, x1, y1 = self.sorgente.bbox()
            for j in range(max(0, int(y0 // g)), min(H + 1, int(y1 // g) + 2)):
                for i in range(max(0, int(x0 // g)), min(W + 1, int(x1 // g) + 2)):
                    if dentro((i * g, j * g), self.sorgente.punti) and libero(i, j):
                        vis[j][i] = True
                        coda.append((i, j))
        while coda:
            i, j = coda.popleft()
            for a, b in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= a <= W and 0 <= b <= H and not vis[b][a] and libero(a, b):
                    vis[b][a] = True
                    coda.append((a, b))
        portata = self.corridoio_cm / 2 + 15      # il personale arriva a 45 cm dalla zona del tavolo (verifica: 50)

        def tocca(dist_punto, bb):
            x0, y0, x1, y1 = bb
            for j in range(max(0, int((y0 - portata) // g)), min(H + 1, int((y1 + portata) // g) + 2)):
                for i in range(max(0, int((x0 - portata) // g)), min(W + 1, int((x1 + portata) // g) + 2)):
                    if vis[j][i] and dist_punto((i * g, j * g)) <= portata:
                        return True
            return False

        raggiunti, mancano = set(), set()
        for f in self.fissi:
            bb = f.corpo.bbox()
            bb = (bb[0] - self.sedie_cm, bb[1] - self.sedie_cm, bb[2] + self.sedie_cm, bb[3] + self.sedie_cm)
            ok = tocca(lambda c, f=f: max(0.0, f.corpo.dist_box((c[0], c[1], c[0], c[1])) - self.sedie_cm), bb)
            (raggiunti if ok else mancano).add(f.id)
        for nome, zone in self.porte_zone.items():
            ok = any(vis[j][i] for z in zone for i, j in _punti_dentro(z, g) if i <= W and j <= H)
            (raggiunti if ok else mancano).add(f"porta:{nome}")
        for tid, boxes in regioni:
            ok = False
            for i0, j0, i1, j1 in boxes:
                bb = (i0 * g, j0 * g, i1 * g, j1 * g)
                if tocca(lambda c, bb=bb: dist_punto_box(c, bb), bb):
                    ok = True
                    break
            (raggiunti if ok else mancano).add(tid)
        if self.base_raggiunti is not None:      # contano solo i fissi e le porte raggiungibili nella sala vuota
            mancano = {x for x in mancano if x in self.base_raggiunti or not _e_base(x, self)}
        return raggiunti, mancano

    def _strade(self, regioni: list[tuple[str, list]]) -> dict[str, list]:
        """Per ogni porta e per il punto più lontano dall'ingresso, i punti (angoli di cella) del percorso più corto
        (Dijkstra a 8 direzioni: percorsi quasi dritti) dove passa il personale largo `corridoio_cm`, con i tavoli mobili
        `regioni` al loro posto."""
        import heapq
        W, H, g = self.W, self.H, self.griglia_cm
        r = int(math.ceil(self.corridoio_cm / 2 / g))
        occ = [riga[:] for riga in self.occ_cammino]
        for _, boxes in regioni:
            for i0, j0, i1, j1 in boxes:
                for j in range(max(0, j0), min(H, j1)):
                    for i in range(max(0, i0), min(W, i1)):
                        occ[j][i] = 1
        pref = self.prefissi(occ)

        def libero(i, j):
            return libero_box(pref, W, H, i - r, j - r, i + r, j + r)

        dist, padre, heap = {}, {}, []
        if self.sorgente is not None:
            x0, y0, x1, y1 = self.sorgente.bbox()
            for j in range(max(0, int(y0 // g)), min(H + 1, int(y1 // g) + 2)):
                for i in range(max(0, int(x0 // g)), min(W + 1, int(x1 // g) + 2)):
                    if dentro((i * g, j * g), self.sorgente.punti) and libero(i, j):
                        dist[(i, j)] = 0
                        heapq.heappush(heap, (0, i, j))
        while heap:
            d, i, j = heapq.heappop(heap)
            if d > dist.get((i, j), 1 << 60):
                continue
            for di, dj, c in ((1, 0, 10), (-1, 0, 10), (0, 1, 10), (0, -1, 10), (1, 1, 14), (1, -1, 14), (-1, 1, 14), (-1, -1, 14)):
                a, b = i + di, j + dj
                if 0 <= a <= W and 0 <= b <= H and libero(a, b) and d + c < dist.get((a, b), 1 << 60):
                    dist[(a, b)], padre[(a, b)] = d + c, (i, j)
                    heapq.heappush(heap, (d + c, a, b))
        def percorso(p):
            out = [p]
            while p in padre:
                p = padre[p]
                out.append(p)
            return out

        strade = {}
        for nome, zone in self.porte_zone.items():
            mete = [(i, j) for z in zone for i, j in _punti_dentro(z, g) if (i, j) in dist]
            if mete:
                strade[f"porta:{nome}"] = percorso(min(mete, key=lambda q: dist[q]))
        portata = self.corridoio_cm / 2 + 15
        migliori = []                                  # per ogni tavolo del disegno, il punto raggiunto più vicino
        for nome, boxes in regioni:
            cand = [(dist[(i, j)], (i, j)) for i0, j0, i1, j1 in boxes
                    for j in range(max(0, j0 - 5), min(H, j1 + 5) + 1) for i in range(max(0, i0 - 5), min(W, i1 + 5) + 1)
                    if (i, j) in dist and dist_punto_box((i * g, j * g), (i0 * g, j0 * g, i1 * g, j1 * g)) <= portata]
            if cand:
                migliori.append((min(cand), nome))
        if migliori:
            (_, punto), nome = max(migliori)
            strade[f"tavolo più lontano ({nome})"] = percorso(punto)
        return strade

    def irraggiungibili(self, regioni: list[tuple[str, list]]) -> set:
        """Tavoli (fissi e mobili) e porte che il personale non raggiunge dall'ingresso con i tavoli mobili `regioni`;
        i fissi e le porte già irraggiungibili nella sala senza tavoli mobili non contano (sono della piantina)."""
        return self._cammino(regioni)[1]

    # ---- utilità per il modello
    def rettangoli(self, occ) -> list[tuple[int, int, int, int]]:
        """Celle occupate scomposte in rettangoli DISGIUNTI (i0, j0, i1, j1), tratti per riga fusi in verticale."""
        aperti: dict[tuple[int, int], int] = {}
        out = []
        for j in range(self.H + 1):
            tratti = set()
            if j < self.H:
                riga, i = occ[j], 0
                while i < self.W:
                    if riga[i]:
                        i0 = i
                        while i < self.W and riga[i]:
                            i += 1
                        tratti.add((i0, i))
                    else:
                        i += 1
            for ch in list(aperti):
                if ch not in tratti:
                    out.append((ch[0], aperti.pop(ch), ch[1], j))
            for t in tratti:
                aperti.setdefault(t, j)
        return sorted(out, key=lambda r: (r[1], r[0]))

    def prefissi(self, occ) -> list[list[int]]:
        W, H = self.W, self.H
        pref = [[0] * (W + 1) for _ in range(H + 1)]
        for j in range(H):
            acc = 0
            for i in range(W):
                acc += occ[j][i]
                pref[j + 1][i + 1] = pref[j][i + 1] + acc
        return pref


def libero_box(pref, W: int, H: int, i0: int, j0: int, i1: int, j1: int) -> bool:
    """Il box di celle [i0, i1) x [j0, j1) è dentro la griglia e senza celle occupate."""
    if i0 < 0 or j0 < 0 or i1 > W or j1 > H:
        return False
    return pref[j1][i1] - pref[j0][i1] - pref[j1][i0] + pref[j0][i0] == 0


def _centro(f: Forma) -> tuple[float, float]:
    x0, y0, x1, y1 = f.bbox()
    return (x0 + x1) / 2, (y0 + y1) / 2


def _box_punto(p) -> tuple[float, float, float, float]:
    return p[0], p[1], p[0], p[1]


def _punti_dentro(f: Forma, g: int):
    """Punti d'angolo delle celle (i, j) dentro la forma."""
    x0, y0, x1, y1 = f.bbox()
    for j in range(max(0, int(y0 // g)), int(y1 // g) + 2):
        for i in range(max(0, int(x0 // g)), int(x1 // g) + 2):
            if dentro((i * g, j * g), f.punti):
                yield i, j


def _e_base(x: str, sala: SalaLibera) -> bool:
    """Il nome è di un tavolo fisso o di una porta (non di un tavolo mobile)."""
    return x.startswith("porta:") or any(f.id == x for f in sala.fissi)
