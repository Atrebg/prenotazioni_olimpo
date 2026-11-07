/** Esegue i lavori uno alla volta, nell'ordine di arrivo: due messaggi non toccano mai lo stato insieme. */
export class Coda {
  private fine: Promise<unknown> = Promise.resolve();
  esegui<T>(lavoro: () => Promise<T>): Promise<T> {
    const r = this.fine.then(lavoro, lavoro);
    this.fine = r.catch(() => undefined);
    return r;
  }
}
