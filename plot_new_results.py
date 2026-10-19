import pandas as pd
import matplotlib.pyplot as plt

COLORS = {
    'Tabu+SA': '#d62728', # Rojo (El mejor)
    'Tabu': '#2ca02c',  # Verde
    'SA': '#ff7f0e', # Naranja
    'GA (p_mut=1/n)': '#1f77b4' # Azul (El peor)
}

# Gráfica de Barras
df = pd.read_csv('results_los_v3_v2res.csv')
df = df[(df['mode']=='nominal') & (df['tracking']=='trunc') & (df['noise']=='floor')]

pivot = df.groupby('method')['planned_cost'].agg(['mean', 'std']).reset_index()
pivot = pivot.sort_values('mean')

# Asignar color basado en el nombre
bar_colors = []
for m in pivot['method']:
    if m in COLORS:
        bar_colors.append(COLORS[m])
    else:
        print(f"⚠️ ALERTA: El método '{m}' no está en COLORS. Revisa los nombres exactos.")
        bar_colors.append('gray')

plt.figure(figsize=(8, 5))
plt.bar(pivot['method'], pivot['mean'], yerr=pivot['std'], capsize=5, color=bar_colors)
plt.title('Planned Cost (2 x 240 min vacations)\nLower is better')
plt.ylabel('Cost (mean ± sd)')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('figures/fig_v3_hybrid_wins.png', dpi=150)
plt.close()

# Gráfica de Líneas
df_load = pd.read_csv('results_los_v3_load.csv')
df_load = df_load[(df_load['mode']=='nominal') & (df_load.tracking=='trunc') & (df_load.noise=='floor')]

pivot_load = df_load.pivot_table(index='bloc_load', columns='method', values='planned_cost', aggfunc='mean')

plt.figure(figsize=(8, 5))
for method in pivot_load.columns:
    c = COLORS.get(method, 'gray') 
    plt.plot(pivot_load.index, pivot_load[method], marker='o', label=method, color=c)

plt.title('Cost vs Block Load (2 x 240 min vacations)')
plt.xlabel('Block Load (Capacity Utilization)')
plt.ylabel('Planned Cost')
plt.axvline(x=0.93, color='gray', linestyle='--', label='High Load Threshold')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('figures/fig_v3_load_effect.png', dpi=150)
plt.close()