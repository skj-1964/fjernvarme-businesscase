# Arkiv

Historiske dokumenter. De er bevaret, så det kan ses, hvad der blev vist og
regnet tidligere, men **tal og kommandoer her gælder ikke længere**. Brug
repoets README og den gældende rapport i `doc/`.

| fil | hvad | hvorfor forældet |
|---|---|---|
| `rapport_billund_v3.docx` / `.pdf` | pilotrapporten til Billund, 24. april 2026 | Casen `billund_baseline.yaml` findes ikke længere; kommandoerne bruger `--external` uden `--data-source`; balancetallene (bl.a. de "19 mio." fra temadagen 7. maj 2026) er afløst af valideringen mod Billunds afregning; varmepumpen var lineær, nu en målt ydelsestabel. |
| `figures_v3/` | figur 1–8 til rapport v3 og `generate_figures.py` | Figurerne bygger på kørsler for april 2025–marts 2026 med et ældre filnavnsformat. Scriptet peger på stier uden for repoet og kan ikke køre på main. |

Hvad der ændrede sig, og hvorfor, står i rapport v4.
