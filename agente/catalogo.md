# Catalogo della sala (ricavato dalla piantina)

Si ricava con le regole della skill `sala` e si rigenera solo quando la piantina cambia (punto 2 della skill), non
a mano.

## Versione e totali

- Piantina con `"aggiornata": "29/10/2026"`, 17 righe di `storico`, l'ultima che comincia con "29/10/2026 · 13A e
  13B si uniscono in un tavolo da 8".
- 30 tavoli; 141 posti con i blocchi interi e senza unioni; **151 posti al massimo** per turno; **29 quadrati
  mobili** (7 tavoli quadrati e 22 moduli di blocchi).

## Unità

L'ordine delle righe è l'**ordine del catalogo**, l'ultimo spareggio di `assegna-tavoli`.

| unità | posti | usa (pezzi) | tagli richiesti | cos'è |
|---|---|---|---|---|
| 1 | 4 | 1 | – | panca fissa |
| 2 | 4 | 2 | – | panca fissa |
| 3 | 2 | 3 | – | quadrato mobile |
| 4 | 2 | 4 | – | quadrato mobile |
| 5 | 8 | 5a 5b 5c | nessuno (blocco intero) | blocco separabile |
| 5ab | 6 | 5a 5b | b\|c | pezzo |
| 5bc | 6 | 5b 5c | a\|b | pezzo |
| 5a | 4 | 5a | a\|b | quadrato |
| 5b | 4 | 5b | a\|b, b\|c | quadrato |
| 5c | 4 | 5c | b\|c | quadrato |
| 6 | 3 | 6 | – | tondo alto, sgabelli |
| 7 | 6 | 7a 7b | nessuno (blocco intero) | blocco separabile |
| 7a | 4 | 7a | a\|b | quadrato |
| 7b | 4 | 7b | a\|b | quadrato |
| 8 | 8 | 8a 8b 8c | nessuno (blocco intero) | blocco separabile |
| 8ab | 6 | 8a 8b | b\|c | pezzo |
| 8bc | 6 | 8b 8c | a\|b | pezzo |
| 8a | 4 | 8a | a\|b | quadrato |
| 8b | 4 | 8b | a\|b, b\|c | quadrato |
| 8c | 4 | 8c | b\|c | quadrato |
| 9 | 6 | 9 | – | blocco, non si divide |
| 10 | 10 | 10 | – | tondo grande |
| 11 | 20 | 11-1 11-2 | – | lungo, un gruppo |
| 11-1 | 8 | 11-1 | – | lungo, prima metà |
| 11-2 | 8 | 11-2 | – | lungo, seconda metà |
| 12 | 6 | 12 | – | blocco, non si divide |
| 13A | 4 | 13A | – | rettangolare fisso |
| 13B | 4 | 13B | – | rettangolare fisso |
| 13A+13B | 8 | 13A 13B | – | unione |
| 14, 15, 16, 17, 18, 19 | 4 ciascuna | sé stessa | – | panche fisse |
| 20, 21, 22, 23, 24 | 4 ciascuno | sé stesso | – | blocchi, non si dividono |
| 25, 26, 27, 28, 29 | 2 ciascuno | sé stesso | – | quadrati mobili |
| 20+25 | 6 | 20 25 | – | unione |
| 21+26 | 6 | 21 26 | – | unione |
| 22+27 | 6 | 22 27 | – | unione |
| 23+28 | 6 | 23 28 | – | unione |
| 24+29 | 6 | 24 29 | – | unione |

## Soglie per turno

| famiglia di pezzi | ≤ 2 | 3 | 4 | 5-6 | 7-8 | 9-10 | 11-20 |
|---|---|---|---|---|---|---|---|
| panche 1, 2, 14-19 | 8 | 8 | 8 | 0 | 0 | 0 | 0 |
| 13A, 13B, 13A+13B | 2 | 2 | 2 | 1 | 1 | 0 | 0 |
| 6 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| 10 | 1 | 1 | 1 | 1 | 1 | 1 | 0 |
| 11 | 2 | 2 | 2 | 2 | 2 | 1 | 1 |
| 3, 4 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| 5 | 3 | 3 | 3 | 1 | 1 | 0 | 0 |
| 8 | 3 | 3 | 3 | 1 | 1 | 0 | 0 |
| 7 | 2 | 2 | 2 | 1 | 0 | 0 | 0 |
| 9 | 1 | 1 | 1 | 1 | 0 | 0 | 0 |
| 12 | 1 | 1 | 1 | 1 | 0 | 0 | 0 |
| 20+25 … 24+29 (5 coppie) | 10 | 5 | 5 | 5 | 0 | 0 | 0 |
| **totale per turno** | **36** | **29** | **28** | **14** | **6** | **2** | **1** |

- Una colonna vale per le prenotazioni da almeno il suo primo numero ("5-6": da 5 coperti in su). Da 21 in su: 0.
- **Lungo a un gruppo**: 35, 28, 27, 13, 5 (colonne da ≤ 2 a 7-8). Obbligato se c'è un gruppo da 11 in su, oppure
  almeno due gruppi da 9 in su.

## Liste ricavate

- **Limiti di taglia**: l'unità più grande ha 20 posti (da 21 in su: PIENO); da 11 a 20 solo "11"; 9 o 10 solo "10"
  o "11"; fino a 8 mai "11".
- **Scambio con il lungo**: U = "10" (unica unità di un pezzo, oltre al lungo, con più di 8 posti).
- **Tavoli mobili** (`"fisso": false`): quadrati 3, 4, 25-29; blocchi 5, 7, 8, 9, 12, 20-24.
- **Dividi chi siede largo** (passo 2a):

| unità occupata | se l'occupante ha | va su | si libera |
|---|---|---|---|
| 7 | fino a 4 | 7a | 7b (4) |
| 5 (o 8) | fino a 6 | 5ab | 5c (4) |
| 5 (o 8) | fino a 4 | 5a | 5bc (6), oppure 5b e 5c (4 + 4) |
| 5ab (o 8ab) | fino a 4 | 5a | 5b (4) |
| 5bc (o 8bc) | fino a 4 | 5c | 5b (4) |
| 13A+13B | fino a 4 | 13A | 13B (4) |
| 20+25 (… 24+29) | fino a 4 | 20 | 25 (2) |
| 20+25 (… 24+29) | fino a 2 | 25 | 20 (4) |
| 11 | fino a 8 | 11-1 | 11-2 (8) |
