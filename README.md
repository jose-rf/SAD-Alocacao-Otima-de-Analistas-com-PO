# Alocação Ótima de Analistas

Modelo de otimização para alocação de analistas em projetos de assessoria em regime de horas, desenvolvido como Trabalho de Conclusão de Curso (TCC) na UEMG.

O objetivo é **maximizar a rentabilidade** da operação distribuindo horas de analistas entre projetos, respeitando capacidade, qualificação mínima e demanda de cada projeto.

---

## Sobre o modelo

O problema é formulado como um modelo de **Programação Linear Contínua** (Assignment Problem), resolvido com o solver CBC via biblioteca PuLP.

**Variável de decisão:**

```
x[i][j] = horas do analista i alocadas ao projeto j
```

**Função objetivo — maximizar o lucro líquido:**

```
max  Σ_ij [ (receita_j / horas_req_j) · prod_i  −  custo_hora_i ] · x[i][j]
```

**Restrições:**

| # | Descrição | Expressão |
|---|-----------|-----------|
| 1 | Capacidade do analista | `Σ_j x[i][j] ≤ horas_disp_i` &nbsp; ∀i |
| 2 | Demanda do projeto | `Σ_i x[i][j] ≥ horas_req_j` &nbsp; ∀j |
| 3 | Qualificação mínima | `x[i][j] = 0` se `nível_i < nível_min_j` |
| 4 | Não-negatividade | `x[i][j] ≥ 0` |

Os níveis de qualificação seguem a hierarquia: **Junior → Pleno → Sênior**.

---

## Funcionalidades

- Cadastro dinâmico de analistas e projetos via interface gráfica
- Parâmetro opcional de **produtividade** por analista (0 < prod ≤ 1)
- Restrição de **nível mínimo** por projeto
- Exibição dos KPIs: Lucro Líquido, Receita Total, Custo Total e Margem
- Tabela de alocação detalhada com horas, custo e receita gerada por linha
- Formulação matemática exibida junto ao resultado

---

## Tecnologias

- **Python 3.10+**
- [PuLP](https://coin-or.github.io/pulp/) — modelagem e resolução do problema de PL
- [CBC](https://github.com/coin-or/Cbc) — solver open-source (incluído no PuLP)
- [Streamlit](https://streamlit.io/) — interface web interativa

---

## Instalação

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/alocacao-analistas.git
cd alocacao-analistas

# Instale as dependências
pip install pulp streamlit
```

---

## Como usar

```bash
streamlit run alocacao_analistas.py
```

1. Preencha os dados dos **analistas** (nome, nível, custo/hora, horas disponíveis e produtividade opcional)
2. Preencha os dados dos **projetos** (nome, horas requeridas, receita total, nível mínimo e prazo)
3. Clique em **⚙ Calcular Alocação Ótima**
4. O resultado exibe os KPIs e a tabela de alocação detalhada

Dados de exemplo já são carregados automaticamente ao abrir o sistema.

---

## Estrutura do código

```
alocacao_analistas.py
├── Analista          # dataclass com atributos do analista
├── Projeto           # dataclass com atributos do projeto
├── resolver()        # monta e resolve o modelo de PL com PuLP
└── App               # interface gráfica em Tkinter
    ├── _header()
    ├── _corpo()      # seções de Analistas, Projetos e Resultado (com scroll)
    ├── _rodape()     # botão de execução
    ├── _calcular()   # coleta os dados e chama resolver()
    └── _mostrar_resultado()  # exibe KPIs, tabela e formulação
```

---

## Contexto acadêmico

Este projeto é o protótipo computacional do TCC:

> **Modelo de Otimização para Alocação de Analistas em Projetos de Assessoria em Regime de Horas: Uma Abordagem por Programação Linear Visando Maximização da Rentabilidade**
>
> Curso de Sistemas de Informação — UEMG

---

## Licença

MIT
