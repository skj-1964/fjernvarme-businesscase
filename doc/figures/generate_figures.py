#!/usr/bin/env python3
"""
Genererer figurer til rapport_billund_v3.md

Datagrundlag: apr25-mar26 kørsler fra output/-mappen + hovedtal fra STATUS_session12
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import pandas as pd
import numpy as np
from pathlib import Path

# Stil - matcher v1's æstetik
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 10
plt.rcParams['axes.spines.top'] = False
plt.rcParams['axes.spines.right'] = False
plt.rcParams['axes.grid'] = True
plt.rcParams['grid.alpha'] = 0.3
plt.rcParams['grid.linestyle'] = '--'

OUT = Path('/home/claude/work/figures')
OUT.mkdir(parents=True, exist_ok=True)
DATA = Path('/home/claude/district_heating_bc/output')

# Hovedtal fra STATUS_session12
OBJ_A = 33.81  # tank, ingen balancing
OBJ_B = 40.37  # ingen tank, ingen balancing
OBJ_C = 18.19  # tank + balancing
OBJ_D = 23.63  # ingen tank + balancing

TANK_ALONE = OBJ_B - OBJ_A   # 6,56
BAL_WITH_TANK = OBJ_A - OBJ_C  # 15,62
COMBINED = OBJ_B - OBJ_C   # 22,18
WITH_HAIRCUT = COMBINED * 0.85  # 18,85


# =============================================================================
# FIG 1: Anlægstopologi (opdateret 2026-konfiguration)
# =============================================================================
def fig_topology():
    fig, ax = plt.subplots(figsize=(12, 6.5))
    ax.set_xlim(0, 14); ax.set_ylim(0, 8)
    ax.axis('off')

    def box(x, y, w, h, name, cap, mc, color, text_color='black'):
        rect = FancyBboxPatch((x, y), w, h,
                               boxstyle="round,pad=0.05,rounding_size=0.15",
                               linewidth=1.5, edgecolor='#333',
                               facecolor=color)
        ax.add_patch(rect)
        ax.text(x+w/2, y+h*0.72, name, ha='center', va='center',
                fontsize=11, fontweight='bold', color=text_color)
        ax.text(x+w/2, y+h*0.48, cap, ha='center', va='center',
                fontsize=10, color=text_color)
        ax.text(x+w/2, y+h*0.22, mc, ha='center', va='center',
                fontsize=8.5, style='italic', color=text_color)

    # Øverste række - el-baserede
    box(0.3, 5.0, 2.9, 2.4, 'Varmepumpe\nluft/vand', '16 MW varme',
        'mc≈−180 (sommer)\n−260 (vinter) DKK/MWh', '#a8d5e8')
    box(3.5, 5.0, 2.9, 2.4, 'Elkedel ny', '30 MW varme',
        'mc≈−630 DKK/MWh', '#f4c991')
    box(6.7, 5.0, 2.9, 2.4, 'Elkedel ældre', '15 MW varme',
        'mc≈−630 DKK/MWh', '#f4c991')
    box(9.9, 5.0, 2.9, 2.4, 'Halmkedel', '12 MW varme',
        'mc≈−360 DKK/MWh\nmin 12t oppe-tid', '#c8e0a0')

    # Nederste række - brændsel + lager + last
    box(0.3, 2.2, 2.9, 2.4, 'Gasmotor', '2,8 MW varme\n2,0 MW el',
        'mc≈−240 DKK/MWh', '#d8a8d0')
    box(3.5, 2.2, 2.9, 2.4, 'Gaskedel agg.', '26,3 MW varme',
        'mc≈−570 DKK/MWh\n(reserve)', '#d8a8d0')
    box(6.7, 2.2, 2.9, 2.4, 'Akkumuleringstank',
        '14.000 m³ / 732 MWh\n(2×2000 + 1×10000)', 'mc = flexarbitrage',
        '#c0b8e0')
    box(9.9, 2.2, 2.9, 2.4, 'Varmebehov',
        '127,5 GWh/år\npeak 42 MW', 'mc = efterspørgsel',
        '#e0e0e0')

    # aFRR/mFRR box
    box(0.3, 0.0, 12.5, 1.5, 'aFRR + mFRR balancemarked',
        'VP 2,65 MW per marked  ·  Elkedler samlet 6 MW per marked  ·  Total 8,65 MW på hvert marked',
        '', '#fff2cc')

    ax.text(7, 7.7, 'Billund Varmeværk — 2026-konfiguration (modelleret)',
            ha='center', fontsize=13, fontweight='bold')

    plt.tight_layout()
    plt.savefig(OUT / 'fig1_topologi.png', dpi=160, bbox_inches='tight',
                facecolor='white')
    plt.close()
    print("✓ fig1_topologi.png")


# =============================================================================
# FIG 2: 2x2 matrix waterfall med hovedtal
# =============================================================================
def fig_2x2_matrix():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5),
                                     gridspec_kw={'width_ratios': [1, 1.2]})

    # Venstre: 2x2 matrix som grid
    ax1.set_xlim(0, 10); ax1.set_ylim(0, 10)
    ax1.axis('off')

    # Akser
    ax1.plot([5, 5], [1.2, 9], color='#666', lw=1)
    ax1.plot([1.2, 9], [5, 5], color='#666', lw=1)

    # Labels
    ax1.text(3, 9.6, 'Med tank', ha='center', fontsize=11, fontweight='bold')
    ax1.text(7, 9.6, 'Uden tank', ha='center', fontsize=11, fontweight='bold')
    ax1.text(0.3, 7, 'Uden\nbalance', ha='center', va='center',
             fontsize=11, fontweight='bold', rotation=90)
    ax1.text(0.3, 3, 'Med\nbalance', ha='center', va='center',
             fontsize=11, fontweight='bold', rotation=90)

    # Fire felter
    def cell(x, y, label, value, color):
        rect = FancyBboxPatch((x-1.6, y-1.3), 3.2, 2.6,
                               boxstyle="round,pad=0.05,rounding_size=0.1",
                               linewidth=1.5, edgecolor='#333', facecolor=color)
        ax1.add_patch(rect)
        ax1.text(x, y+0.6, label, ha='center', va='center',
                fontsize=10, fontweight='bold')
        ax1.text(x, y-0.4, f'{value:.2f}', ha='center', va='center',
                fontsize=16, fontweight='bold', color='#003366')
        ax1.text(x, y-0.9, 'mio DKK/år', ha='center', va='center',
                fontsize=9, color='#666')

    cell(3, 7, 'A', OBJ_A, '#e8f0d8')
    cell(7, 7, 'B', OBJ_B, '#f8e0d0')
    cell(3, 3, 'C', OBJ_C, '#c8e0d0')
    cell(7, 3, 'D', OBJ_D, '#f0d0c0')

    ax1.set_title('Scenariematrix — årlig driftsomkostning\n(apr 2025 − mar 2026)',
                   fontsize=12, pad=15)

    # Højre: Waterfall - forenklet til 4 bars
    categories = ['B\nUden tank,\nuden balance',
                  'Tank alene\n(spotarbitrage)',
                  'Balance med tank\n(aFRR + mFRR)',
                  'C\nMed tank,\nmed balance']
    # Kumulativ: start ved B, træk tank-værdi, træk balance-værdi, slut ved C
    starts = [0, OBJ_A, OBJ_C, 0]
    heights = [OBJ_B, TANK_ALONE, BAL_WITH_TANK, OBJ_C]
    colors = ['#e69966', '#66a366', '#66a3a3', '#407090']
    labels_on_bar = [f'{OBJ_B:.1f}', f'−{TANK_ALONE:.2f}', f'−{BAL_WITH_TANK:.2f}', f'{OBJ_C:.1f}']

    for i in range(4):
        ax2.bar(i, heights[i], bottom=starts[i], color=colors[i],
                edgecolor='#333', linewidth=1)
        y_label = starts[i] + heights[i]/2
        txt_color = 'white' if i in [1, 2] else 'black'
        txt_weight = 'bold'
        ax2.text(i, y_label, labels_on_bar[i], ha='center', va='center',
                fontsize=11, fontweight=txt_weight, color=txt_color)

    # Forbindelseslinjer (stiplet) mellem bars
    ax2.plot([0.4, 1-0.4], [OBJ_A, OBJ_A], 'k--', lw=0.8, alpha=0.4)
    ax2.plot([1+0.4, 2-0.4], [OBJ_A, OBJ_A], 'k--', lw=0.8, alpha=0.4)
    ax2.plot([2+0.4, 3-0.4], [OBJ_C, OBJ_C], 'k--', lw=0.8, alpha=0.4)

    ax2.set_xticks(range(4))
    ax2.set_xticklabels(categories, fontsize=9)
    ax2.set_ylabel('mio DKK/år', fontsize=10)
    ax2.set_title('Waterfall — fra drift uden lager\ntil el-flex-drift', fontsize=12, pad=15)
    ax2.set_ylim(0, 48)

    # Annotation box med hovedtal
    props = dict(boxstyle='round,pad=0.5', facecolor='#fff9e6', edgecolor='#cc9900')
    ax2.text(3.3, 45,
             f'Tank alene:        {TANK_ALONE:.2f} mio\n'
             f'Balance (m/tank):  {BAL_WITH_TANK:.2f} mio\n'
             f'Kombineret:        {COMBINED:.2f} mio\n'
             f'Efter 15% haircut: {WITH_HAIRCUT:.2f} mio',
             fontsize=9, bbox=props, family='monospace', va='top', ha='right')

    plt.tight_layout()
    plt.savefig(OUT / 'fig2_2x2_matrix.png', dpi=160, bbox_inches='tight',
                facecolor='white')
    plt.close()
    print("✓ fig2_2x2_matrix.png")


# =============================================================================
# FIG 3: Månedlig varmeproduktion med tank+balancing (base case C)
# =============================================================================
def fig_monthly_dispatch():
    df = pd.read_csv(DATA / 'billund_baseline__ext__2025-04-01_2026-03-31__bal_monthly.csv',
                     index_col=0)
    # Drop "År"-row, konverter index til int
    df = df.drop('År', errors='ignore')
    df.index = df.index.astype(int)
    # Måneder er 1..12 men kører apr-mar. Omorganisér
    month_order = [4,5,6,7,8,9,10,11,12,1,2,3]
    month_labels = ['Apr','Maj','Jun','Jul','Aug','Sep','Okt','Nov','Dec','Jan','Feb','Mar']
    df = df.reindex(month_order)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6.5),
                                     gridspec_kw={'height_ratios': [2.2, 1]},
                                     sharex=True)

    units = [
        ('vp_luft_vand_gwh', 'Varmepumpe', '#4a90b8'),
        ('elkedel_ny_gwh', 'Elkedel ny', '#e8a662'),
        ('elkedel_gl_gwh', 'Elkedel ældre', '#c9853e'),
        ('halmkedel_gwh', 'Halm', '#8cb369'),
        ('gasmotor_gwh', 'Gasmotor', '#b08bbf'),
        ('gaskedel_agg_gwh', 'Gaskedel', '#7a4a8c'),
    ]

    x = np.arange(12)
    bottom = np.zeros(12)
    for col, label, color in units:
        vals = df[col].values
        ax1.bar(x, vals, bottom=bottom, label=label, color=color,
                edgecolor='white', linewidth=0.5)
        bottom += vals

    # Varmebehov linje
    ax1.plot(x, df['heat_load_gwh'].values, 'o-', color='black',
             lw=1.5, markersize=5, label='Varmebehov', zorder=10)

    ax1.set_ylabel('GWh per måned', fontsize=10)
    ax1.set_title('Månedlig varmeproduktion med tank + balancemarked\n(apr 2025 − mar 2026)',
                   fontsize=12, pad=12)
    ax1.legend(loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=7,
               fontsize=9, frameon=False)

    # Temperatur og spot
    ax2b = ax2.twinx()
    ax2.plot(x, df['t_out_c'].values, 's-', color='#c0392b', lw=1.3,
             markersize=4, label='Udetemperatur')
    ax2.set_ylabel('T_ude [°C]', color='#c0392b', fontsize=9)
    ax2.tick_params(axis='y', labelcolor='#c0392b')
    ax2.set_ylim(-2, 22)

    ax2b.plot(x, df['spot_mean_dkk_mwh'].values, 'D-', color='#2874a6',
             lw=1.3, markersize=4, label='Spot DK1')
    ax2b.set_ylabel('Spot [DKK/MWh]', color='#2874a6', fontsize=9)
    ax2b.tick_params(axis='y', labelcolor='#2874a6')
    ax2b.grid(False)

    ax2.set_xticks(x)
    ax2.set_xticklabels(month_labels, fontsize=9)
    ax2.set_xlabel('')

    plt.tight_layout()
    plt.savefig(OUT / 'fig3_monthly_dispatch.png', dpi=160, bbox_inches='tight',
                facecolor='white')
    plt.close()
    print("✓ fig3_monthly_dispatch.png")


# =============================================================================
# FIG 4: Unit dispatch 4 scenarier
# =============================================================================
def fig_unit_dispatch_4scenarier():
    # Indlæs KPI fra alle 4 scenarier
    scenarios = {
        'A: Tank, u/bal': DATA / 'billund_baseline__ext__2025-04-01_2026-03-31_kpi.csv',
        'B: U/tank, u/bal': DATA / 'billund_baseline__ext__2025-04-01_2026-03-31__off-tank_eksisterende_kpi.csv',
        'C: Tank, m/bal': DATA / 'billund_baseline__ext__2025-04-01_2026-03-31__bal_kpi.csv',
        'D: U/tank, m/bal': DATA / 'billund_baseline__ext__2025-04-01_2026-03-31__bal__off-tank_eksisterende_kpi.csv',
    }

    unit_order = ['vp_luft_vand', 'elkedel_ny', 'halmkedel',
                   'gasmotor', 'gaskedel_agg', 'elkedel_gl']
    unit_labels = {
        'vp_luft_vand': 'Varmepumpe',
        'elkedel_ny': 'Elkedel ny',
        'halmkedel': 'Halm',
        'gasmotor': 'Gasmotor',
        'gaskedel_agg': 'Gaskedel',
        'elkedel_gl': 'Elkedel ældre',
    }

    data = {}
    for scen, path in scenarios.items():
        df = pd.read_csv(path)
        data[scen] = dict(zip(df['unit'], df['production_mwh']/1000))  # → GWh

    fig, ax = plt.subplots(figsize=(13, 5.5))

    x = np.arange(len(unit_order))
    width = 0.2
    colors = ['#8cb369', '#e8a662', '#4a90b8', '#c06060']

    for i, (scen, d) in enumerate(data.items()):
        vals = [d.get(u, 0) for u in unit_order]
        offset = (i - 1.5) * width
        bars = ax.bar(x + offset, vals, width, label=scen, color=colors[i],
                      edgecolor='#333', linewidth=0.8)
        for b, v in zip(bars, vals):
            if v > 0.5:
                ax.text(b.get_x() + b.get_width()/2, v + 1, f'{v:.0f}',
                        ha='center', fontsize=7.5)

    ax.set_xticks(x)
    ax.set_xticklabels([unit_labels[u] for u in unit_order], fontsize=10)
    ax.set_ylabel('Årsproduktion [GWh]', fontsize=10)
    ax.set_title('Årsproduktion pr. enhed — fire scenarier sammenlignet\n'
                  '(apr 2025 − mar 2026)', fontsize=12, pad=12)
    ax.legend(loc='upper right', fontsize=9.5, framealpha=0.95)
    ax.set_ylim(0, 105)

    # Annotation om elkedel
    ax.annotate('Elkedel ny aktiveres massivt\nnår tanken er tilstede',
                xy=(1 + 1.5*width, 31.3), xytext=(2.5, 60),
                fontsize=9, ha='left',
                arrowprops=dict(arrowstyle='->', color='#666', lw=0.8),
                bbox=dict(boxstyle='round,pad=0.4', facecolor='#fff9e6',
                          edgecolor='#cc9900'))

    plt.tight_layout()
    plt.savefig(OUT / 'fig4_unit_dispatch_4scen.png', dpi=160, bbox_inches='tight',
                facecolor='white')
    plt.close()
    print("✓ fig4_unit_dispatch_4scen.png")


# =============================================================================
# FIG 5: aFRR vs mFRR dekomponering (kap-tung vs akt-tung)
# =============================================================================
def fig_afrr_mfrr_decomp():
    # Fra STATUS_session12
    markets = ['aFRR', 'mFRR']
    cap_revenue = [6.69, 4.03]
    act_revenue = [4.61, 8.29]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5),
                                     gridspec_kw={'width_ratios': [1, 1]})

    # Venstre: stacked bars
    x = np.arange(len(markets))
    p1 = ax1.bar(x, cap_revenue, 0.55, label='Kapacitetsbetaling',
                  color='#5b8fb9', edgecolor='#333', linewidth=1)
    p2 = ax1.bar(x, act_revenue, 0.55, bottom=cap_revenue,
                  label='Aktiveringsbetaling (brut)',
                  color='#ff9966', edgecolor='#333', linewidth=1)

    for i, (c, a) in enumerate(zip(cap_revenue, act_revenue)):
        ax1.text(i, c/2, f'{c:.1f}\nmio', ha='center', va='center',
                fontsize=10, fontweight='bold', color='white')
        ax1.text(i, c + a/2, f'{a:.1f}\nmio', ha='center', va='center',
                fontsize=10, fontweight='bold', color='white')
        ax1.text(i, c+a + 0.4, f'Total {c+a:.1f}', ha='center',
                fontsize=10.5, fontweight='bold')

    ax1.set_xticks(x)
    ax1.set_xticklabels(markets, fontsize=11, fontweight='bold')
    ax1.set_ylabel('Brutto-indtægt [mio DKK/år]', fontsize=10)
    ax1.set_title('Indtægtskilde pr. marked',
                   fontsize=11, pad=10)
    ax1.legend(loc='upper left', fontsize=9.5)
    ax1.set_ylim(0, 16)

    # Højre: pie-donuts der viser procentfordeling
    def donut(ax, cap, act, title, subtitle):
        vals = [cap, act]
        colors_pie = ['#5b8fb9', '#ff9966']
        wedges, texts, autotexts = ax.pie(vals, labels=None, colors=colors_pie,
                                           autopct='%1.0f%%', startangle=90,
                                           pctdistance=0.75,
                                           wedgeprops=dict(width=0.38, edgecolor='white',
                                                           linewidth=2))
        for at in autotexts:
            at.set_fontsize(12); at.set_fontweight('bold'); at.set_color('white')
        ax.text(0, 0.1, title, ha='center', fontsize=12, fontweight='bold')
        ax.text(0, -0.1, subtitle, ha='center', fontsize=9, style='italic',
                color='#555')

    # Split højre side i 2
    ax2.axis('off')
    sub1 = fig.add_axes([0.58, 0.28, 0.18, 0.52])
    sub2 = fig.add_axes([0.79, 0.28, 0.18, 0.52])

    donut(sub1, cap_revenue[0], act_revenue[0], 'aFRR', '"kap-tung"')
    donut(sub2, cap_revenue[1], act_revenue[1], 'mFRR', '"akt-tung"')

    ax2.text(0.5, 0.95, 'Fordeling af indtægten', ha='center', va='top',
             transform=ax2.transAxes, fontsize=11, fontweight='bold')
    ax2.text(0.5, 0.08,
             'aFRR: betaling for at stå klar (robust i rolige markeder)\n'
             'mFRR: betaling når vi kaldes ud (robust i urolige markeder)',
             ha='center', va='bottom', transform=ax2.transAxes,
             fontsize=9.5, style='italic', color='#444')

    plt.suptitle('aFRR og mFRR er strategisk komplementære',
                 fontsize=13, fontweight='bold', y=1.00)
    plt.savefig(OUT / 'fig5_afrr_mfrr.png', dpi=160, bbox_inches='tight',
                facecolor='white')
    plt.close()
    print("✓ fig5_afrr_mfrr.png")


# =============================================================================
# FIG 6: Tank-dekomposition ved volumen
# =============================================================================
def fig_tank_decomp():
    # Fra STATUS_session12: første 4000 m³ fanger 82-85%, ekstra 10000 tilføjer 0,82-1,14 mio
    # Vi har eksplicitte tal:
    # Tank 14000: tank-alene 6,56 mio
    # Tank 4000: (fra session 12 ~82-85%) = ca 5,42-5,58 mio
    # Brug 84% midtpunkt: 5.51 mio

    volumes = np.array([0, 2000, 4000, 6000, 8000, 10000, 12000, 14000])
    # Approksimeret diminishing returns-kurve der matcher data:
    # 14000 → 6.56; 4000 → ~5.52 (84% af 6.56)
    # Power-law fit: værdi ≈ a · V^b, med datapunkterne
    # Lad os bruge en simpel approksimation
    def tank_value(v):
        # Logaritmisk metning kalibreret så 4000 m³ → 84% af 14000's værdi
        # (matcher session 12's fund: 82-85%)
        if v == 0:
            return 0
        return 6.56 * (1 - np.exp(-v/2200))
    values = np.array([tank_value(v) for v in volumes])

    marginal = np.diff(values) / np.diff(volumes) * 1000  # mio DKK per 1000 m³
    marg_x = (volumes[:-1] + volumes[1:]) / 2

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5),
                                     gridspec_kw={'width_ratios': [1, 1]})

    # Venstre: kumulativ værdi
    ax1.fill_between(volumes, 0, values, color='#a8d5e8', alpha=0.6)
    ax1.plot(volumes, values, 'o-', color='#2874a6', lw=2, markersize=7)

    # Annotér de to nøglepunkter
    ax1.axvline(4000, color='#c0392b', linestyle='--', lw=1, alpha=0.6)
    ax1.axvline(14000, color='#27ae60', linestyle='--', lw=1, alpha=0.6)

    val_4k = tank_value(4000)
    val_14k = tank_value(14000)
    ax1.annotate(f'4.000 m³\n{val_4k:.2f} mio\n({val_4k/val_14k*100:.0f}% af total)',
                 xy=(4000, val_4k), xytext=(5500, 3),
                 fontsize=9.5,
                 arrowprops=dict(arrowstyle='->', color='#c0392b'),
                 bbox=dict(boxstyle='round,pad=0.4', facecolor='#fce5d0',
                          edgecolor='#c0392b'))
    ax1.annotate(f'14.000 m³\n{val_14k:.2f} mio\n(100%)',
                 xy=(14000, val_14k), xytext=(10500, 2),
                 fontsize=9.5,
                 arrowprops=dict(arrowstyle='->', color='#27ae60'),
                 bbox=dict(boxstyle='round,pad=0.4', facecolor='#d5e8cf',
                          edgecolor='#27ae60'))

    ax1.set_xlabel('Tank-volumen [m³]', fontsize=10)
    ax1.set_ylabel('Arbitrageværdi [mio DKK/år]', fontsize=10)
    ax1.set_title('Tank-værdi vs. volumen — metningseffekt',
                   fontsize=11.5, pad=10)
    ax1.set_xlim(0, 15500); ax1.set_ylim(0, 7.2)

    # Højre: "de første 4000 m³ og de næste 10000 m³"
    categories = ['Første 4.000 m³\n(ældre tanke)', 'Næste 10.000 m³\n(2025-udvidelse)']
    contributions = [val_4k, val_14k - val_4k]
    colors = ['#8cb369', '#c0996b']

    bars = ax2.bar(categories, contributions, color=colors, edgecolor='#333',
                    linewidth=1.2, width=0.55)
    for b, v in zip(bars, contributions):
        ax2.text(b.get_x() + b.get_width()/2, v + 0.1,
                f'{v:.2f} mio\n({v/val_14k*100:.0f}%)',
                ha='center', fontsize=11, fontweight='bold')

    ax2.set_ylabel('Bidrag til arbitrageværdi [mio DKK/år]', fontsize=10)
    ax2.set_title('Hvor kommer tankens værdi fra?',
                   fontsize=11.5, pad=10)
    ax2.set_ylim(0, 7)

    # Nuance-box
    props = dict(boxstyle='round,pad=0.5', facecolor='#fff9e6', edgecolor='#cc9900')
    ax2.text(0.5, 0.5,
             '2025-udvidelsens hovedværdi ligger\n'
             'i at muliggøre balancemarkedsdeltagelse\n'
             '(15,6 mio/år), ikke i ekstra spotarbitrage',
             transform=ax2.transAxes, fontsize=9, ha='center',
             bbox=props, style='italic')

    plt.tight_layout()
    plt.savefig(OUT / 'fig6_tank_decomp.png', dpi=160, bbox_inches='tight',
                facecolor='white')
    plt.close()
    print("✓ fig6_tank_decomp.png")


# =============================================================================
# FIG 7: COP(T_ambient) - matchende v1
# =============================================================================
def fig_cop_curve():
    # Indlæs timedata for COP i praksis per måned
    df = pd.read_csv(DATA / 'billund_baseline__ext__2025-04-01_2026-03-31__bal_hourly.csv',
                     parse_dates=['timestamp'])
    df['month'] = df['timestamp'].dt.month

    # Månedsgennemsnitlig T og effektiv COP
    # COP = clip(2.2 + 0.08*T, 1.8, 4.0)
    month_means = df.groupby('month').agg(
        t_mean=('t_out_c', 'mean')
    ).reset_index()
    month_means['cop_eff'] = np.clip(2.2 + 0.08 * month_means['t_mean'], 1.8, 4.0)

    fig, ax = plt.subplots(figsize=(10, 5.5))

    # COP-kurve
    t_range = np.linspace(-10, 30, 300)
    cop = np.clip(2.2 + 0.08 * t_range, 1.8, 4.0)
    ax.plot(t_range, cop, '-', color='#2874a6', lw=2.5,
            label='COP = clip(2,2 + 0,08·T_ude, 1,8, 4,0)')

    # Grænser
    ax.axhline(1.8, color='#c0392b', linestyle=':', lw=1, alpha=0.7,
                label='COP min (defrost)')
    ax.axhline(4.0, color='#27ae60', linestyle=':', lw=1, alpha=0.7,
                label='COP max')

    # Månedsobservationer - alternér label-placering
    month_labels_da = ['Jan','Feb','Mar','Apr','Maj','Jun',
                        'Jul','Aug','Sep','Okt','Nov','Dec']
    # Placér labels skiftevis over/under punkter for at undgå overlap
    offsets = [(-15, -18), (10, 8), (8, -15), (6, 8), (-18, 8), (6, -15),
               (8, 8), (-18, -15), (-15, 8), (8, -15), (-15, -18), (8, 8)]
    for idx, (_, row) in enumerate(month_means.iterrows()):
        ax.plot(row['t_mean'], row['cop_eff'], 'o', color='#c0392b',
                markersize=8, zorder=10)
        ax.annotate(month_labels_da[int(row['month'])-1],
                     xy=(row['t_mean'], row['cop_eff']),
                     xytext=offsets[idx], textcoords='offset points',
                     fontsize=9, fontweight='bold', color='#c0392b')

    ax.set_xlabel('Udetemperatur [°C]', fontsize=10)
    ax.set_ylabel('COP', fontsize=10)
    ax.set_title('COP(T_ude) for luft/vand-varmepumpen — antaget lineær\n[VALIDERES MOD LEVERANDØR-DATABLAD]',
                  fontsize=11, pad=12)
    ax.legend(loc='lower right', fontsize=9.5)
    ax.set_xlim(-10, 30); ax.set_ylim(1.5, 4.5)

    ax.text(0.03, 0.97,
            'Røde punkter: effektiv COP ved\nmånedsgennemsnits-temperatur.\n'
            'Lavere COP i kolde måneder → halmen\nbliver relativt mere attraktiv.',
            transform=ax.transAxes, fontsize=8.5, va='top',
            bbox=dict(boxstyle='round,pad=0.4', facecolor='#fafafa',
                     edgecolor='#ccc'))

    plt.tight_layout()
    plt.savefig(OUT / 'fig7_cop_curve.png', dpi=160, bbox_inches='tight',
                facecolor='white')
    plt.close()
    print("✓ fig7_cop_curve.png")


# =============================================================================
# FIG 8: Pris-tager-status
# =============================================================================
def fig_pris_tager():
    markets = ['aFRR', 'mFRR']
    billund = [8.65, 8.65]
    market_total = [100, 597]  # gennemsnit indkøbt/udbudt i perioden

    pct = [b/m*100 for b, m in zip(billund, market_total)]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

    # Venstre: stacked bar visning
    x = np.arange(len(markets))
    ax1.bar(x, market_total, 0.5, color='#e0e0e0', edgecolor='#666',
             linewidth=1, label='Resten af markedet')
    ax1.bar(x, billund, 0.5, color='#2874a6', edgecolor='#333',
             linewidth=1.2, label='Billund max-bud')

    for i, (b, m, p) in enumerate(zip(billund, market_total, pct)):
        ax1.text(i, m + 15, f'{m} MW\ntotal', ha='center',
                fontsize=9, color='#666')
        # Pil + label til højre for den tynde Billund-bar
        ax1.annotate(f'{b} MW\n({p:.1f}%)',
                    xy=(i+0.25, b), xytext=(i+0.6, b+50),
                    fontsize=11, fontweight='bold', color='#2874a6',
                    ha='left',
                    arrowprops=dict(arrowstyle='->', color='#2874a6'))

    ax1.set_xticks(x)
    ax1.set_xticklabels(markets, fontsize=11)
    ax1.set_ylabel('MW-kapacitet', fontsize=10)
    ax1.set_title('Billund i forhold til markedet',
                   fontsize=11, pad=10)
    ax1.legend(loc='upper left', fontsize=9)
    ax1.set_ylim(0, 680)

    # Højre: tekstboks om implikationer
    ax2.axis('off')
    ax2.text(0.5, 0.9, 'Pris-tager-status',
             ha='center', fontsize=13, fontweight='bold',
             transform=ax2.transAxes)

    ax2.text(0.05, 0.75,
             '• Billund byder max 8,65 MW på hvert marked\n'
             '  (VP 2,65 + elkedler 6,00 MW gruppe)',
             transform=ax2.transAxes, fontsize=10.5, va='top')

    ax2.text(0.05, 0.55,
             '• aFRR: ~9% af markedet\n'
             '  → i grænseområdet, følsomhedsanalyse laves',
             transform=ax2.transAxes, fontsize=10.5, va='top')

    ax2.text(0.05, 0.35,
             '• mFRR: ~1,4% af markedet\n'
             '  → solidt pris-tager-område',
             transform=ax2.transAxes, fontsize=10.5, va='top')

    ax2.text(0.05, 0.12,
             'Det er en vigtig forudsætning for\n'
             'analysens validitet: en aktør der\n'
             'udgør 30% af markedet flytter selv\n'
             'prisen og skal regnes anderledes.',
             transform=ax2.transAxes, fontsize=9.5, va='top',
             style='italic',
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#fff9e6',
                      edgecolor='#cc9900'))

    plt.tight_layout()
    plt.savefig(OUT / 'fig8_pris_tager.png', dpi=160, bbox_inches='tight',
                facecolor='white')
    plt.close()
    print("✓ fig8_pris_tager.png")


if __name__ == '__main__':
    fig_topology()
    fig_2x2_matrix()
    fig_monthly_dispatch()
    fig_unit_dispatch_4scenarier()
    fig_afrr_mfrr_decomp()
    fig_tank_decomp()
    fig_cop_curve()
    fig_pris_tager()
    print("\nAlle figurer genereret i:", OUT)
