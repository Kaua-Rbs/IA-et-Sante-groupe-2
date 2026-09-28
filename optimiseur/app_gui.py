"""
app_gui.py
----------
Interface graphique (Tkinter) du moteur d'optimisation du bloc
operatoire. Permet de :
  - generer un jeu de donnees de test, charger le Parquet EDA reel
    (donnees du bloc) ou ses propres CSV
  - lancer les metaheuristiques (recuit simule, tabou, genetique,
    hybride tabou x recuit, fourmis/ACO)
  - visualiser la vitesse de convergence, la comparaison qualite/temps,
    le planning obtenu et l'occupation des lits
  - consulter le planning detaille dans un tableau

Lancement (depuis la racine du depot) :
    python -m optimiseur.app_gui

Necessite tkinter (fourni avec la plupart des distributions Python ;
sous Linux : `sudo apt install python3-tk` si absent).
"""

from __future__ import annotations

import threading
import queue
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

import pandas as pd
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

from . import data_bridge as db
from . import optimizer as op
from . import plotting as pl

METHODES = [op.METHODE_RECUIT, op.METHODE_TABOU, op.METHODE_GENETIQUE, op.METHODE_HYBRIDE, op.METHODE_FOURMIS]


class BlocOperatoireApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Optimisation du bloc operatoire — metaheuristiques")
        self.geometry("1150x750")

        self.patients_df: pd.DataFrame | None = None
        self.vacations_df: pd.DataFrame | None = None
        self.problem: op.PlanningProblem | None = None
        self.resultats: dict[str, op.RunResult] | None = None

        self._queue: queue.Queue = queue.Queue()

        self._build_top_bar()
        self._build_notebook()
        self._build_status_bar()

        # generer un jeu de donnees par defaut au demarrage
        self._generer_donnees_test()

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------
    def _build_top_bar(self):
        bar = ttk.Frame(self, padding=8)
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(bar, text="Patients :").grid(row=0, column=0, padx=4)
        self.var_n_patients = tk.IntVar(value=30)
        ttk.Spinbox(bar, from_=5, to=200, textvariable=self.var_n_patients, width=6).grid(row=0, column=1)

        ttk.Label(bar, text="Jours :").grid(row=0, column=2, padx=4)
        self.var_n_days = tk.IntVar(value=5)
        ttk.Spinbox(bar, from_=1, to=20, textvariable=self.var_n_days, width=5).grid(row=0, column=3)

        ttk.Label(bar, text="Capacite lits :").grid(row=0, column=4, padx=4)
        self.var_lits = tk.IntVar(value=42)
        ttk.Spinbox(bar, from_=5, to=500, textvariable=self.var_lits, width=6).grid(row=0, column=5)

        ttk.Button(bar, text="Generer des donnees de test", command=self._generer_donnees_test).grid(
            row=0, column=6, padx=10
        )
        ttk.Button(bar, text="Charger donnees reelles (EDA)...", command=self._charger_donnees_reelles).grid(
            row=0, column=7, padx=4
        )
        ttk.Button(bar, text="Charger CSV patients...", command=self._charger_patients_csv).grid(
            row=0, column=8, padx=4
        )
        ttk.Button(bar, text="Charger CSV vacations...", command=self._charger_vacations_csv).grid(
            row=0, column=9, padx=4
        )

        self.btn_run = ttk.Button(bar, text="Lancer l'optimisation", command=self._lancer_optimisation)
        self.btn_run.grid(row=0, column=10, padx=14)

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.tab_donnees = ttk.Frame(self.notebook)
        self.tab_convergence = ttk.Frame(self.notebook)
        self.tab_comparaison = ttk.Frame(self.notebook)
        self.tab_planning = ttk.Frame(self.notebook)
        self.tab_lits = ttk.Frame(self.notebook)
        self.tab_table = ttk.Frame(self.notebook)

        for tab, titre in [
            (self.tab_donnees, "Donnees"),
            (self.tab_convergence, "Convergence"),
            (self.tab_comparaison, "Comparaison"),
            (self.tab_planning, "Planning"),
            (self.tab_lits, "Lits"),
            (self.tab_table, "Tableau du planning"),
        ]:
            self.notebook.add(tab, text=titre)

        # -- onglet donnees : deux tableaux (patients / vacations) --
        self.tree_patients = self._make_tree(self.tab_donnees, side=tk.LEFT, titre="Patients")
        self.tree_vacations = self._make_tree(self.tab_donnees, side=tk.RIGHT, titre="Vacations")

        # -- onglets graphiques : un canvas matplotlib chacun --
        self.canvas_convergence = self._make_canvas(self.tab_convergence)
        self.canvas_comparaison = self._make_canvas(self.tab_comparaison)
        self.canvas_planning = self._make_canvas(self.tab_planning)
        self.canvas_lits = self._make_canvas(self.tab_lits)

        # -- onglet tableau du planning final --
        top = ttk.Frame(self.tab_table)
        top.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(top, text="Methode a afficher :").pack(side=tk.LEFT)
        self.var_methode_table = tk.StringVar(value=op.METHODE_RECUIT)
        self.combo_methode = ttk.Combobox(
            top, textvariable=self.var_methode_table,
            values=METHODES, state="readonly", width=20,
        )
        self.combo_methode.pack(side=tk.LEFT, padx=6)
        self.combo_methode.bind("<<ComboboxSelected>>", lambda e: self._rafraichir_table_planning())
        self.tree_planning = self._make_tree(self.tab_table, side=tk.TOP, titre=None, fill_all=True)

    def _build_status_bar(self):
        self.status_var = tk.StringVar(value="Pret.")
        bar = ttk.Frame(self, padding=4)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=180)
        self.progress.pack(side=tk.RIGHT, padx=6)
        ttk.Label(bar, textvariable=self.status_var).pack(side=tk.LEFT, padx=6)

    def _make_tree(self, parent, side, titre, fill_all=False):
        frame = ttk.Frame(parent)
        if fill_all:
            frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        else:
            frame.pack(side=side, fill=tk.BOTH, expand=True, padx=6, pady=4)
        if titre:
            ttk.Label(frame, text=titre, font=("", 10, "bold")).pack(anchor="w")
        tree = ttk.Treeview(frame, show="headings")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        return tree

    def _make_canvas(self, parent):
        fig = plt.Figure(figsize=(9, 5.5))
        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        return canvas

    # ------------------------------------------------------------------
    # Remplissage des tables (Treeview) a partir d'un DataFrame
    # ------------------------------------------------------------------
    @staticmethod
    def _fill_tree(tree: ttk.Treeview, df: pd.DataFrame):
        tree.delete(*tree.get_children())
        tree["columns"] = list(df.columns)
        for col in df.columns:
            tree.heading(col, text=col)
            tree.column(col, width=100, anchor="center")
        for _, row in df.iterrows():
            tree.insert("", "end", values=list(row))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _generer_donnees_test(self):
        self.patients_df, self.vacations_df = op.generate_test_data(
            n_patients=self.var_n_patients.get(),
            n_days=self.var_n_days.get(),
        )
        self._fill_tree(self.tree_patients, self.patients_df)
        self._fill_tree(self.tree_vacations, self.vacations_df)
        self.resultats = None
        self.status_var.set(
            f"Donnees de test generees : {len(self.patients_df)} patients, {len(self.vacations_df)} vacations."
        )

    def _charger_donnees_reelles(self):
        """Charge le Parquet pretraite par EDA_donees_bloc.ipynb.

        Le classeur Excel source n'est jamais lu directement : le notebook EDA
        est la source de verite du pretraitement et produit ce Parquet, que
        ``data_bridge.prepare_inputs`` convertit au schema de l'optimiseur.
        """
        chemin = Path(db.DEFAULT_PARQUET)
        if not chemin.exists():
            chemin = filedialog.askopenfilename(
                title="Choisir le Parquet pretraite par EDA_donees_bloc.ipynb",
                filetypes=[("Parquet pretraite", "*.parquet")],
            )
        if not chemin:
            return
        try:
            patients, vacations, contexte = db.prepare_inputs(
                chemin, horizon_jours=self.var_n_days.get()
            )
        except Exception as exc:
            messagebox.showerror("Erreur de chargement", str(exc))
            return

        self.patients_df, self.vacations_df = patients, vacations
        self._fill_tree(self.tree_patients, patients)
        self._fill_tree(self.tree_vacations, vacations)
        self.resultats = None

        dates = contexte.get("dates") or []
        if len(dates):
            periode = f"du {pd.Timestamp(dates[0]):%d/%m/%Y} au {pd.Timestamp(dates[-1]):%d/%m/%Y}"
        else:
            periode = "dates inconnues"
        self.status_var.set(
            f"Donnees reelles chargees ({periode}) : {len(patients)} patients, "
            f"{len(vacations)} vacations."
        )

    def _charger_patients_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            df = pd.read_csv(path)
            required = {"specialite", "duree_operatoire", "duree_sejour"}
            if not required.issubset(df.columns):
                raise ValueError(f"Colonnes requises manquantes : {required - set(df.columns)}")
            if "patient_id" not in df.columns:
                df.insert(0, "patient_id", range(len(df)))
            self.patients_df = df
            self._fill_tree(self.tree_patients, df)
            self.status_var.set(f"Patients charges depuis {path}")
        except Exception as exc:
            messagebox.showerror("Erreur de chargement", str(exc))

    def _charger_vacations_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            df = pd.read_csv(path)
            required = {"jour", "specialite", "capacite_min"}
            if not required.issubset(df.columns):
                raise ValueError(f"Colonnes requises manquantes : {required - set(df.columns)}")
            if "vacation_id" not in df.columns:
                df.insert(0, "vacation_id", range(len(df)))
            self.vacations_df = df
            self._fill_tree(self.tree_vacations, df)
            self.status_var.set(f"Vacations chargees depuis {path}")
        except Exception as exc:
            messagebox.showerror("Erreur de chargement", str(exc))

    def _lancer_optimisation(self):
        if self.patients_df is None or self.vacations_df is None:
            messagebox.showwarning("Donnees manquantes", "Generez ou chargez d'abord des donnees.")
            return

        self.btn_run.config(state="disabled")
        self.progress.start(12)
        self.status_var.set("Optimisation en cours (metaheuristiques)...")

        # Les tk.Variable ne doivent etre lues que depuis le thread principal :
        # on capture la valeur ici, avant de la transmettre au thread de calcul.
        lits_capacity = self.var_lits.get()
        thread = threading.Thread(target=self._worker_optimisation, args=(lits_capacity,), daemon=True)
        thread.start()
        self.after(150, self._poll_queue)

    def _worker_optimisation(self, lits_capacity: int):
        try:
            problem = op.PlanningProblem(
                self.patients_df, self.vacations_df, lits_capacity=lits_capacity
            )
            resultats = op.optimize_planning(
                self.patients_df, self.vacations_df, lits_capacity=lits_capacity
            )
            self._queue.put(("ok", problem, resultats))
        except Exception as exc:  # remonte l'erreur au thread principal
            self._queue.put(("erreur", exc, None))

    def _poll_queue(self):
        try:
            statut, a, b = self._queue.get_nowait()
        except queue.Empty:
            self.after(150, self._poll_queue)
            return

        self.progress.stop()
        self.btn_run.config(state="normal")

        if statut == "erreur":
            messagebox.showerror("Erreur pendant l'optimisation", str(a))
            self.status_var.set("Erreur pendant l'optimisation.")
            return

        self.problem, self.resultats = a, b
        self._rafraichir_graphiques()
        self.status_var.set("Optimisation terminee. Voir les onglets Convergence / Comparaison / Planning.")

    # ------------------------------------------------------------------
    # Rafraichissement des visualisations
    # ------------------------------------------------------------------
    def _rafraichir_graphiques(self):
        if self.resultats is None or self.problem is None:
            return

        for nom, r in self.resultats.items():
            print(f"{nom:<15s} fitness={r.meilleure_fitness:10.3f}  temps={op.format_duree(r.duree_s):>9s}")

        fig = self.canvas_convergence.figure
        fig.clear()
        ax = fig.add_subplot(111)
        pl.plot_convergence(self.resultats, ax=ax)
        self.canvas_convergence.draw()

        fig2 = self.canvas_comparaison.figure
        fig2.clear()
        ax1 = fig2.add_subplot(121)
        ax2 = fig2.add_subplot(122)
        pl.plot_comparaison_barres(self.resultats, ax=[ax1, ax2])
        self.canvas_comparaison.draw()

        meilleure_methode = max(self.resultats, key=lambda n: self.resultats[n].meilleure_fitness)
        fig3 = self.canvas_planning.figure
        fig3.clear()
        ax3 = fig3.add_subplot(111)
        pl.plot_planning(
            self.problem,
            self.resultats[meilleure_methode].meilleure_solution,
            titre=f"Planning obtenu ({meilleure_methode} — meilleure methode)",
            ax=ax3,
        )
        self.canvas_planning.draw()

        fig4 = self.canvas_lits.figure
        fig4.clear()
        ax4 = fig4.add_subplot(111)
        pl.plot_occupation_lits(self.problem, self.resultats[meilleure_methode].meilleure_solution, ax=ax4)
        self.canvas_lits.draw()

        self.var_methode_table.set(meilleure_methode)
        self._rafraichir_table_planning()

    def _rafraichir_table_planning(self):
        if self.resultats is None or self.problem is None:
            return
        methode = self.var_methode_table.get()
        if methode not in self.resultats:
            return
        df = op.solution_to_dataframe(self.problem, self.resultats[methode].meilleure_solution)
        self._fill_tree(self.tree_planning, df)


if __name__ == "__main__":
    app = BlocOperatoireApp()
    app.mainloop()
