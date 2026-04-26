import tkinter as tk
from tkinter import ttk, messagebox
import pulp
from dataclasses import dataclass
from typing import List

NIVEL_ORDEM = {"Junior": 1, "Pleno": 2, "Senior": 3}

BG    = "#F5F5F5"
WHITE = "#FFFFFF"
BLUE  = "#1A3C5E"
BLUE2 = "#2E6DA4"
GREEN = "#1B6B45"
GREEN2= "#EAF3DE"
RED   = "#A32D2D"
RED2  = "#FCEBEB"
GRAY  = "#D3D1C7"
TEXT  = "#2C2C2A"
MUTED = "#888780"


# ── Modelos ──────────────────────────────────────────────────────────────────

@dataclass
class Analista:
    nome: str
    nivel: str
    custo_hora: float
    horas_disponiveis: float
    produtividade: float = 1.0   # opcional; padrão = 1.0

@dataclass
class Projeto:
    nome: str
    horas_requeridas: float
    receita_total: float
    nivel_minimo: str
    prazo_semanas: int


# ── Solver ───────────────────────────────────────────────────────────────────

def resolver(analistas: List[Analista], projetos: List[Projeto]):
    """
    Maximiza lucro líquido:
      max  Σ_ij [ (receita_j/horas_j) * prod_i  -  custo_i ] * x_ij
    Sujeito a:
      Σ_j x_ij  ≤  horas_disp_i        (capacidade)
      Σ_i x_ij  ≥  horas_req_j         (demanda)
      x_ij = 0 se nivel_i < nivel_min_j (qualificação)
      x_ij ≥ 0
    """
    prob = pulp.LpProblem("Alocacao", pulp.LpMaximize)
    na, np_ = len(analistas), len(projetos)
    x = [[pulp.LpVariable(f"x{i}{j}", lowBound=0) for j in range(np_)] for i in range(na)]

    prob += pulp.lpSum(
        ((projetos[j].receita_total / projetos[j].horas_requeridas) * analistas[i].produtividade
         - analistas[i].custo_hora) * x[i][j]
        for i in range(na) for j in range(np_)
    )

    for i, a in enumerate(analistas):
        prob += pulp.lpSum(x[i][j] for j in range(np_)) <= a.horas_disponiveis

    for j, p in enumerate(projetos):
        prob += pulp.lpSum(
            x[i][j] for i, a in enumerate(analistas)
            if NIVEL_ORDEM[a.nivel] >= NIVEL_ORDEM[p.nivel_minimo]
        ) >= p.horas_requeridas

    for i, a in enumerate(analistas):
        for j, p in enumerate(projetos):
            if NIVEL_ORDEM[a.nivel] < NIVEL_ORDEM[p.nivel_minimo]:
                prob += x[i][j] == 0

    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    lucro = pulp.value(prob.objective) or 0.0

    linhas = []
    if lucro:
        for i, a in enumerate(analistas):
            for j, p in enumerate(projetos):
                h = pulp.value(x[i][j]) or 0.0
                if h > 0.01:
                    linhas.append((
                        a.nome, a.nivel, p.nome,
                        round(h, 1),
                        round(h * a.custo_hora, 2),
                        round(p.receita_total / p.horas_requeridas * h * a.produtividade, 2)
                    ))

    return round(lucro, 2), linhas


# ── Interface ────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Alocação Ótima de Analistas")
        self.configure(bg=BG)
        self.resizable(True, True)

        self.linhas_analistas = []
        self.linhas_projetos  = []

        self._header()
        self._corpo()
        self._rodape()

        # Duas linhas de exemplo em cada seção
        self._add_analista("Ana Souza",    "Senior", "120", "160", "")
        self._add_analista("Bruno Lima",   "Pleno",   "85", "160", "")
        self._add_analista("Diego Ramos",  "Junior",  "55", "160", "")
        self._add_projeto("Consultoria Fiscal",  "200", "50000", "Pleno",  "10")
        self._add_projeto("Auditoria Interna",   "120", "30000", "Senior",  "6")
        self._add_projeto("Implantação ERP",     "300", "70000", "Junior", "14")

        self.update_idletasks()
        w = min(self.winfo_reqwidth() + 40, 1150)
        h = min(self.winfo_reqheight() + 40, 860)
        self.geometry(f"{w}x{h}")

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    def _header(self):
        f = tk.Frame(self, bg=BLUE, padx=24, pady=14)
        f.pack(fill="x")
        tk.Label(f, text="Alocação Ótima de Analistas",
                 font=("Georgia", 17, "bold"), bg=BLUE, fg="white").pack(side="left")
        tk.Label(f, text="Programação Linear · Pesquisa Operacional",
                 font=("Helvetica", 9), bg=BLUE, fg="#A8C4E0").pack(side="left", padx=12)

    # ── Corpo com scroll ──────────────────────────────────────────────────────
    def _corpo(self):
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.sf = tk.Frame(canvas, bg=BG)
        win_id = canvas.create_window((0, 0), window=self.sf, anchor="nw")

        def _resize(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def _width(e):
            canvas.itemconfig(win_id, width=e.width)

        self.sf.bind("<Configure>", _resize)
        canvas.bind("<Configure>", _width)
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        # ── Seção Analistas ───────────────────────────────────────────────────
        self._titulo(self.sf, "Analistas")

        cab_a = tk.Frame(self.sf, bg=BG)
        cab_a.pack(fill="x", padx=24, pady=(2, 0))
        for txt, w in [("Nome", 18), ("Nível", 10), ("Custo/hora (R$)", 14),
                       ("Horas disponíveis", 14), ("Produtividade (opcional)", 20)]:
            tk.Label(cab_a, text=txt, font=("Helvetica", 9, "bold"),
                     bg=BG, fg=MUTED, width=w, anchor="w").pack(side="left", padx=4)

        self.frame_a = tk.Frame(self.sf, bg=BG)
        self.frame_a.pack(fill="x", padx=24, pady=2)

        tk.Button(self.sf, text="+ Adicionar analista",
                  command=self._add_analista,
                  bg=WHITE, fg=BLUE2, font=("Helvetica", 9), relief="flat",
                  cursor="hand2", highlightbackground=GRAY, highlightthickness=1,
                  padx=10, pady=3).pack(anchor="w", padx=24, pady=(4, 12))

        # ── Seção Projetos ────────────────────────────────────────────────────
        self._titulo(self.sf, "Projetos")

        cab_p = tk.Frame(self.sf, bg=BG)
        cab_p.pack(fill="x", padx=24, pady=(2, 0))
        for txt, w in [("Nome do projeto", 18), ("Horas requeridas", 14),
                       ("Receita total (R$)", 16), ("Nível mínimo", 10), ("Prazo (semanas)", 14)]:
            tk.Label(cab_p, text=txt, font=("Helvetica", 9, "bold"),
                     bg=BG, fg=MUTED, width=w, anchor="w").pack(side="left", padx=4)

        self.frame_p = tk.Frame(self.sf, bg=BG)
        self.frame_p.pack(fill="x", padx=24, pady=2)

        tk.Button(self.sf, text="+ Adicionar projeto",
                  command=self._add_projeto,
                  bg=WHITE, fg=BLUE2, font=("Helvetica", 9), relief="flat",
                  cursor="hand2", highlightbackground=GRAY, highlightthickness=1,
                  padx=10, pady=3).pack(anchor="w", padx=24, pady=(4, 12))

        # ── Resultado ─────────────────────────────────────────────────────────
        self._titulo(self.sf, "Resultado")
        self.frame_r = tk.Frame(self.sf, bg=BG)
        self.frame_r.pack(fill="x", padx=24, pady=6)
        tk.Label(self.frame_r,
                 text="Preencha os dados acima e clique em  ⚙ Calcular Alocação Ótima.",
                 font=("Helvetica", 10), bg=BG, fg=MUTED).pack(anchor="w")

    # ── Rodapé ────────────────────────────────────────────────────────────────
    def _rodape(self):
        f = tk.Frame(self, bg=WHITE, padx=24, pady=10,
                     highlightbackground=GRAY, highlightthickness=1)
        f.pack(fill="x", side="bottom")
        tk.Button(f, text="⚙  Calcular Alocação Ótima", command=self._calcular,
                  bg=BLUE, fg="white", font=("Helvetica", 11, "bold"),
                  relief="flat", cursor="hand2", padx=20, pady=7).pack(side="right")
        tk.Label(f, text="Solver: PuLP / CBC  ·  Programação Linear Contínua",
                 font=("Helvetica", 9), bg=WHITE, fg=MUTED).pack(side="left")

    # ── Linha de analista ─────────────────────────────────────────────────────
    def _add_analista(self, nome="", nivel="Pleno", custo="80",
                      horas="160", prod=""):
        row = tk.Frame(self.frame_a, bg=BG)
        row.pack(fill="x", pady=2)

        w_nome  = self._entry(row, 18, nome)
        w_nivel = self._combo(row, ["Junior","Pleno","Senior"], nivel)
        w_custo = self._entry(row, 12, custo)
        w_horas = self._entry(row, 12, horas)
        w_prod  = self._entry(row, 18, prod)

        dados = (w_nome, w_nivel, w_custo, w_horas, w_prod)
        tk.Button(row, text="✕",
                  command=lambda r=row, d=dados: self._del(r, d, self.linhas_analistas),
                  bg=BG, fg=RED, font=("Helvetica", 10),
                  relief="flat", cursor="hand2").pack(side="left", padx=4)

        self.linhas_analistas.append(dados)

    # ── Linha de projeto ──────────────────────────────────────────────────────
    def _add_projeto(self, nome="", horas="200", receita="40000",
                     nivel="Pleno", prazo="8"):
        row = tk.Frame(self.frame_p, bg=BG)
        row.pack(fill="x", pady=2)

        w_nome    = self._entry(row, 18, nome)
        w_horas   = self._entry(row, 12, horas)
        w_receita = self._entry(row, 14, receita)
        w_nivel   = self._combo(row, ["Junior","Pleno","Senior"], nivel)
        w_prazo   = self._entry(row, 8,  prazo)

        dados = (w_nome, w_horas, w_receita, w_nivel, w_prazo)
        tk.Button(row, text="✕",
                  command=lambda r=row, d=dados: self._del(r, d, self.linhas_projetos),
                  bg=BG, fg=RED, font=("Helvetica", 10),
                  relief="flat", cursor="hand2").pack(side="left", padx=4)

        self.linhas_projetos.append(dados)

    def _del(self, row, dados, lista):
        row.destroy()
        lista.remove(dados)

    # ── Calcular ──────────────────────────────────────────────────────────────
    def _calcular(self):
        analistas, projetos = [], []

        for i, (wn, wnv, wc, wh, wp) in enumerate(self.linhas_analistas):
            try:
                nome  = wn.get().strip() or f"Analista {i+1}"
                nivel = wnv.get()
                custo = float(wc.get())
                horas = float(wh.get())
                prod  = float(wp.get()) if wp.get().strip() else 1.0
                if not (0 < prod <= 1):
                    raise ValueError("Produtividade fora do intervalo")
                analistas.append(Analista(nome, nivel, custo, horas, prod))
            except ValueError as e:
                messagebox.showerror("Erro nos dados",
                    f"Analista {i+1}: verifique os campos.\n"
                    "Produtividade deve ser entre 0 e 1 (ou deixe em branco).")
                return

        for i, (wn, wh, wr, wnv, wp) in enumerate(self.linhas_projetos):
            try:
                nome    = wn.get().strip() or f"Projeto {i+1}"
                horas   = float(wh.get())
                receita = float(wr.get())
                nivel   = wnv.get()
                prazo   = int(wp.get())
                projetos.append(Projeto(nome, horas, receita, nivel, prazo))
            except ValueError:
                messagebox.showerror("Erro nos dados",
                    f"Projeto {i+1}: verifique os campos numéricos.")
                return

        if not analistas or not projetos:
            messagebox.showwarning("Atenção",
                "Adicione ao menos um analista e um projeto.")
            return

        lucro, linhas = resolver(analistas, projetos)
        self._mostrar_resultado(lucro, linhas, analistas, projetos)

    # ── Resultado ─────────────────────────────────────────────────────────────
    def _mostrar_resultado(self, lucro, linhas, analistas, projetos):
        for w in self.frame_r.winfo_children():
            w.destroy()
        f = self.frame_r

        if not linhas:
            tk.Label(f,
                text="✘  Solução inviável. Verifique se as horas disponíveis cobrem a demanda dos projetos.",
                font=("Helvetica", 10), bg=RED2, fg=RED,
                padx=12, pady=10, justify="left").pack(fill="x")
            return

        # KPIs
        receita_tot = sum(p.receita_total for p in projetos)
        custo_tot   = sum(l[4] for l in linhas)
        margem_pct  = lucro / receita_tot * 100 if receita_tot else 0

        kpi_row = tk.Frame(f, bg=BG)
        kpi_row.pack(fill="x", pady=(0, 14))
        for label, valor, cor, bg_ in [
            ("Lucro Líquido",  f"R$ {lucro:,.2f}",        GREEN,      GREEN2),
            ("Receita Total",   f"R$ {receita_tot:,.2f}",  BLUE2,      "#E6F1FB"),
            ("Custo Total",     f"R$ {custo_tot:,.2f}",    "#854F0B",  "#FAEEDA"),
            ("Margem",          f"{margem_pct:.1f}%",       GREEN,      GREEN2),
        ]:
            card = tk.Frame(kpi_row, bg=bg_, padx=14, pady=10,
                            highlightbackground=GRAY, highlightthickness=1)
            card.pack(side="left", padx=(0,10), expand=True, fill="x")
            tk.Label(card, text=label, font=("Helvetica", 9),
                     bg=bg_, fg=MUTED).pack(anchor="w")
            tk.Label(card, text=valor,  font=("Helvetica", 13, "bold"),
                     bg=bg_, fg=cor).pack(anchor="w")

        # Tabela
        tk.Label(f, text="Alocação detalhada",
                 font=("Helvetica", 10, "bold"), bg=BG, fg=BLUE).pack(anchor="w", pady=(2,4))

        style = ttk.Style()
        style.configure("R.Treeview", background=WHITE, fieldbackground=WHITE,
                        foreground=TEXT, rowheight=26, font=("Helvetica", 10))
        style.configure("R.Treeview.Heading", background=BLUE, foreground="white",
                        font=("Helvetica", 9, "bold"), relief="flat")
        style.map("R.Treeview", background=[("selected", "#D3E4F5")])

        cols = ("Analista", "Nível", "Projeto", "Horas", "Custo (R$)", "Receita gerada (R$)")
        tv = ttk.Treeview(f, columns=cols, show="headings",
                          style="R.Treeview", height=min(len(linhas), 10))
        for c in cols:
            tv.heading(c, text=c)
            tv.column(c, width=130, anchor="center")
        tv.column("Analista", width=150, anchor="w")
        tv.column("Projeto",  width=170, anchor="w")
        for l in linhas:
            tv.insert("", "end", values=(
                l[0], l[1], l[2],
                f"{l[3]:.1f}h",
                f"R$ {l[4]:,.2f}",
                f"R$ {l[5]:,.2f}"))
        tv.pack(fill="x", pady=(0, 14))

        # Formulação matemática
        tk.Label(f, text="Formulação matemática utilizada",
                 font=("Helvetica", 10, "bold"), bg=BG, fg=BLUE).pack(anchor="w", pady=(2,4))
        formula = (
            "Variável de decisão:  x[i][j] = horas do analista i alocadas ao projeto j\n\n"
            "Maximizar:   Σ_ij [ (receita_j / horas_req_j) · prod_i  −  custo_hora_i ] · x[i][j]\n\n"
            "Sujeito a:\n"
            "  (1)  Σ_j x[i][j]  ≤  horas_disp_i          ∀i   [capacidade do analista]\n"
            "  (2)  Σ_i x[i][j]  ≥  horas_req_j            ∀j   [demanda do projeto]\n"
            "  (3)  x[i][j] = 0   se nível_i < nível_min_j       [qualificação mínima]\n"
            "  (4)  x[i][j] ≥ 0                                   [não-negatividade]"
        )
        card_f = tk.Frame(f, bg=WHITE, padx=14, pady=12,
                          highlightbackground=GRAY, highlightthickness=1)
        card_f.pack(fill="x", pady=(0, 20))
        tk.Label(card_f, text=formula, font=("Courier", 9),
                 bg=WHITE, fg=MUTED, justify="left").pack(anchor="w")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _entry(self, parent, width, default=""):
        e = tk.Entry(parent, width=width, font=("Helvetica", 10),
                     bg=WHITE, fg=TEXT, relief="solid",
                     highlightthickness=1, highlightcolor=BLUE2,
                     highlightbackground=GRAY)
        e.insert(0, default)
        e.pack(side="left", padx=4, ipady=4)
        return e

    def _combo(self, parent, values, default=""):
        var = tk.StringVar(value=default)
        cb = ttk.Combobox(parent, textvariable=var, values=values,
                          state="readonly", width=10, font=("Helvetica", 10))
        cb.pack(side="left", padx=4)
        cb.get = var.get
        return cb

    def _titulo(self, parent, texto):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="x", padx=24, pady=(18, 4))
        tk.Label(f, text=texto, font=("Georgia", 12, "bold"),
                 bg=BG, fg=BLUE).pack(side="left")
        tk.Frame(f, bg=GRAY, height=1).pack(
            side="left", fill="x", expand=True, padx=10, pady=6)


if __name__ == "__main__":
    App().mainloop()
