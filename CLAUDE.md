# CLAUDE.md

Noter til Claude om tal i dette repo. Vejledningen til brugerne står i
`README.md`, herunder afsnittet "Til Claude" om driftsfagligt sprog.

## Gamle referencetal efter spotrettelsen (commit 5021a5e, 3. november 2026)

Spot er kvarterspris fra 1. oktober 2025 dansk tid (2025-09-30 22:00 UTC). På
1-times-aksen tog loaderne tidligere kun :00-kvarteret. Nu midler
`spot_paa_akse` i `src/data_loader.py` over tidsskridtet.

**Hvad det betyder**

- Alle kørsler, der omfatter perioden fra 1. oktober 2025, giver andre tal end
  før. Det gælder også januar–juni 2026 og de rullende år. Kørsler, der slutter
  før den dato, er uændrede.
- Tal i README's referencetabel, `doc/`, rapport v4, kursusmateriale og
  deltagerpakker er regnet før rettelsen. De er ikke opdateret endnu.

**Sådan håndteres det**

- Afviger et resultat fra et af de gamle tal, så sig til brugeren, at det skyldes
  spotrettelsen, og at det ikke er en fejl.
- Ret ikke kode, test eller case for at ramme et gammelt tal.
- Brug ikke en gammel kontrol som bevis for, at en kørsel er i orden. Brug i
  stedet tallene nedenfor. Afvigelser inden for casens gab (0,1 %) er ikke fejl.
- Skriv ikke gamle tal ind i nye dokumenter eller svar uden at sige, at de er fra
  før rettelsen.

**Kontroltal efter rettelsen (5021a5e, juli 2025–juni 2026)**

| Kørsel | Objektiv (kr.) |
|---|---:|
| Andeby, kun spot | 30.495.431 |
| Billund i dag, kun spot | 26.777.743 |
| Billund i dag, faktisk marked | 11.378.359 |

Andre referencetal er ikke regnet igen efter rettelsen.

Slet dette afsnit, når dokumenterne er opdateret med de nye tal.
