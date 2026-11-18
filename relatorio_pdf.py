"""Gera o relatorio de uma execucao em PDF estilizado (reportlab, Python puro).

Uso: gerar_pdf(execucao, alocacoes, aceitos=None, recusados=None, resumo_analistas=None) -> bytes
- execucao: linha da tabela execucoes (acesso por chave)
- alocacoes: lista de dicts de db.list_alocacoes_execucao
- aceitos/recusados/resumo_analistas: so' existem para a execucao gerada na sessao atual (opcionais)
"""
from __future__ import annotations

import io
from collections import OrderedDict
from typing import Iterable, Optional

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

LARANJA = colors.HexColor("#F97316")
GRAFITE = colors.HexColor("#1F2937")
CINZA = colors.HexColor("#6B7280")
CINZA_CLARO = colors.HexColor("#F3F4F6")
LINHA = colors.HexColor("#E5E7EB")
VERDE = colors.HexColor("#16A34A")
VERMELHO = colors.HexColor("#DC2626")
AZUL = colors.HexColor("#2563EB")

LARGURA, ALTURA = A4
MARGEM = 18 * mm
LARGURA_UTIL = LARGURA - 2 * MARGEM

H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=13, textColor=GRAFITE, spaceBefore=0, spaceAfter=0)
CORPO = ParagraphStyle("corpo", fontName="Helvetica", fontSize=9, leading=13, textColor=GRAFITE, alignment=TA_LEFT)
PEQ = ParagraphStyle("peq", fontName="Helvetica", fontSize=8, leading=10, textColor=CINZA)
CELULA = ParagraphStyle("cel", fontName="Helvetica", fontSize=8.5, leading=11, textColor=GRAFITE)
CELULA_B = ParagraphStyle("celb", parent=CELULA, fontName="Helvetica-Bold")


def _brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _secao(titulo: str):
    t = Table([[Paragraph(_esc(titulo), H1)]], colWidths=[LARGURA_UTIL])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 1.2, LARANJA),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
    ]))
    t.keepWithNext = True  # titulo nunca fica orfao no fim da pagina
    return t


def _cartoes(itens):
    """Linha de cartoes de KPI: itens = [(rotulo, valor, cor_do_valor), ...]."""
    n = len(itens)
    w = LARGURA_UTIL / n
    celulas = []
    for rotulo, valor, cor in itens:
        celulas.append([
            Paragraph(_esc(rotulo), ParagraphStyle("kl", fontName="Helvetica", fontSize=7.5, textColor=CINZA, leading=10)),
            Paragraph(_esc(valor), ParagraphStyle("kv", fontName="Helvetica-Bold", fontSize=13.5, textColor=cor, leading=17)),
        ])
    t = Table([celulas], colWidths=[w] * n)
    estilo = [("VALIGN", (0, 0), (-1, -1), "TOP")]
    for i in range(n):
        estilo += [
            ("BACKGROUND", (i, 0), (i, 0), CINZA_CLARO),
            ("LINEBEFORE", (i, 0), (i, 0), 3, LARANJA),
            ("LEFTPADDING", (i, 0), (i, 0), 8), ("TOPPADDING", (i, 0), (i, 0), 7),
            ("BOTTOMPADDING", (i, 0), (i, 0), 7),
        ]
    t.setStyle(TableStyle(estilo))
    # espacamento entre cartoes via bordas brancas
    t.setStyle(TableStyle([("LINEAFTER", (0, 0), (-2, -1), 4, colors.white)]))
    return t


def _grafico_horas(horas_por_analista: "OrderedDict[str, float]", disponiveis: Optional[dict]):
    """Barras horizontais: horas alocadas por analista (e % de uso quando ha' disponibilidade)."""
    itens = list(horas_por_analista.items())
    if not itens:
        return None
    alt_linha = 16
    altura = alt_linha * len(itens) + 18
    d = Drawing(LARGURA_UTIL, altura)
    rotulo_w, area_w = 120, LARGURA_UTIL - 120 - 70
    maximo = max([h for _, h in itens] + [(disponiveis or {}).get(n, 0) for n, _ in itens] + [1])
    for i, (nome, horas) in enumerate(itens):
        y = altura - 18 - i * alt_linha
        d.add(String(0, y + 2, (nome[:24] + "…") if len(nome) > 25 else nome,
                     fontName="Helvetica", fontSize=8, fillColor=GRAFITE))
        d.add(Rect(rotulo_w, y, area_w, 9, fillColor=CINZA_CLARO, strokeColor=None))
        d.add(Rect(rotulo_w, y, area_w * horas / maximo, 9, fillColor=LARANJA, strokeColor=None))
        txt = f"{horas:.1f}h"
        if disponiveis and disponiveis.get(nome):
            txt += f"  ({horas / disponiveis[nome] * 100:.0f}%)"
        d.add(String(rotulo_w + area_w + 6, y + 1.5, txt, fontName="Helvetica-Bold", fontSize=8, fillColor=GRAFITE))
    return d


def _tabela(cabecalho, linhas, larguras, alinhar_dir=()):
    dados = [[Paragraph(_esc(c), ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8,
                                                 textColor=colors.white, leading=10)) for c in cabecalho]]
    for l in linhas:
        dados.append([c if not isinstance(c, str) else Paragraph(_esc(c), CELULA) for c in l])
    t = Table(dados, colWidths=larguras, repeatRows=1)
    est = [
        ("BACKGROUND", (0, 0), (-1, 0), GRAFITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CINZA_CLARO]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINHA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for c in alinhar_dir:
        est.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    t.setStyle(TableStyle(est))
    return t


def _decorar_pagina(canvas, doc, titulo_curto: str):
    canvas.saveState()
    if doc.page == 1:
        canvas.setFillColor(GRAFITE)
        canvas.rect(0, ALTURA - 42 * mm, LARGURA, 42 * mm, stroke=0, fill=1)
        canvas.setFillColor(LARANJA)
        canvas.rect(0, ALTURA - 42 * mm, LARGURA, 2.2 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 20)
        canvas.drawString(MARGEM, ALTURA - 20 * mm, "Relatório de Alocação Ótima")
        canvas.setFont("Helvetica", 10)
        canvas.setFillColor(colors.HexColor("#D1D5DB"))
        canvas.drawString(MARGEM, ALTURA - 27 * mm, "Sistema de Apoio à Decisão  ·  Programação Linear Inteira Mista (PuLP/CBC)")
        canvas.setFillColor(LARANJA)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawString(MARGEM, ALTURA - 35 * mm, titulo_curto)
    else:
        canvas.setFillColor(LARANJA)
        canvas.rect(0, ALTURA - 6 * mm, LARGURA, 6 * mm, stroke=0, fill=1)
        canvas.setFillColor(CINZA)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(MARGEM, ALTURA - 13 * mm, f"Relatório de Alocação Ótima  ·  {titulo_curto}")
    canvas.setStrokeColor(LINHA)
    canvas.line(MARGEM, 12 * mm, LARGURA - MARGEM, 12 * mm)
    canvas.setFillColor(CINZA)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(MARGEM, 8 * mm, "Gerado pelo SAD de Alocação Ótima de Analistas")
    canvas.drawRightString(LARGURA - MARGEM, 8 * mm, f"Página {doc.page}")
    canvas.restoreState()


def gerar_pdf(execucao, alocacoes: Iterable[dict], aceitos=None, recusados=None, resumo_analistas=None) -> bytes:
    alocacoes = list(alocacoes)
    id_exec = execucao["id_execucao"]
    titulo_curto = f"Execução #{id_exec}  ·  {execucao['executado_em']}"
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=MARGEM, rightMargin=MARGEM,
                          topMargin=18 * mm, bottomMargin=17 * mm,
                          title=f"Relatório da execução #{id_exec}", author="SAD Alocação Ótima")
    topo_p1 = 48 * mm
    f1 = Frame(MARGEM, 17 * mm, LARGURA_UTIL, ALTURA - topo_p1 - 17 * mm, id="f1", leftPadding=0, rightPadding=0,
               topPadding=0, bottomPadding=0)
    fn = Frame(MARGEM, 17 * mm, LARGURA_UTIL, ALTURA - 20 * mm - 17 * mm, id="fn", leftPadding=0, rightPadding=0,
               topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="primeira", frames=[f1], onPage=lambda c, d: _decorar_pagina(c, d, titulo_curto),
                     autoNextPageTemplate="demais"),
        PageTemplate(id="demais", frames=[fn], onPage=lambda c, d: _decorar_pagina(c, d, titulo_curto)),
    ])

    h = []
    tempo = execucao["tempo_processamento_s"]
    situacao = str(execucao["situacao"]).capitalize()
    meta = (f"<b>Situação:</b> {_esc(situacao)} &nbsp;&nbsp; <b>Status do solver:</b> {_esc(execucao['status'])}"
            f" &nbsp;&nbsp; <b>h_min:</b> {execucao['h_min']}h"
            f" &nbsp;&nbsp; <b>Tempo CBC:</b> {f'{tempo:.3f}s' if tempo is not None else '—'}")
    h += [Paragraph(meta, CORPO), Spacer(1, 8)]

    if not execucao["viavel"]:
        h += [_secao("Resultado geral"),
              Paragraph(f"O modelo foi considerado <b>inviável</b> (status do solver: {_esc(execucao['status'])}). "
                        "Nenhuma alocação foi gerada para esta execução.", CORPO)]
    else:
        receita, custo, lucro = execucao["receita_total"], execucao["custo_total"], execucao["lucro_liquido"]
        margem = lucro / receita * 100 if receita else 0.0
        taxa = execucao["taxa_ocupacao_equipe"]
        n_proj = len({a["projeto_nome"] for a in alocacoes})
        h += [_secao("Resultado geral"), Spacer(1, 4),
              _cartoes([("LUCRO LÍQUIDO", _brl(lucro), VERDE if lucro >= 0 else VERMELHO),
                        ("RECEITA TOTAL", _brl(receita), GRAFITE),
                        ("CUSTO TOTAL", _brl(custo), GRAFITE)]),
              Spacer(1, 5),
              _cartoes([("MARGEM", f"{margem:.1f}%", GRAFITE),
                        ("PROJETOS ACEITOS", str(n_proj), GRAFITE),
                        ("OCUPAÇÃO DA EQUIPE", f"{taxa:.1f}%" if taxa is not None else "—", AZUL)])]

        # horas por analista
        horas = OrderedDict()
        for a in alocacoes:
            horas[a["analista_nome"]] = horas.get(a["analista_nome"], 0.0) + a["horas"]
        disp = {r.nome: r.disponibilidade for r in resumo_analistas} if resumo_analistas else None
        g = _grafico_horas(horas, disp)
        if g is not None:
            h.append(KeepTogether([_secao("Horas por analista"), Spacer(1, 6), g]))

        # alocacao detalhada
        h.append(_secao("Alocação detalhada"))
        if alocacoes:
            linhas = [[a["analista_nome"], a["projeto_nome"], f"{a['horas']:.1f}",
                       _brl(a["custo"]), _brl(a["receita"])] for a in alocacoes]
            tot_h = sum(a["horas"] for a in alocacoes)
            linhas.append([Paragraph("Total", CELULA_B), "", Paragraph(f"{tot_h:.1f}", CELULA_B),
                           Paragraph(_brl(custo), CELULA_B), Paragraph(_brl(sum(a['receita'] for a in alocacoes)), CELULA_B)])
            w = LARGURA_UTIL
            h.append(_tabela(["Analista", "Projeto", "Horas", "Custo", "Receita gerada"], linhas,
                             [w * .24, w * .30, w * .10, w * .17, w * .19], alinhar_dir=(2, 3, 4)))
        else:
            h.append(Paragraph("Nenhuma alocação realizada.", CORPO))

        # aceitos / recusados
        h.append(_secao("Projetos aceitos e recusados"))
        linhas = []
        if aceitos is not None:
            linhas += [[Paragraph('<font color="#16A34A"><b>ACEITO</b></font>', CELULA), nome, ""] for nome in aceitos]
            linhas += [[Paragraph('<font color="#DC2626"><b>RECUSADO</b></font>', CELULA), nome, motivo]
                       for nome, motivo in (recusados or [])]
        else:
            linhas += [[Paragraph('<font color="#16A34A"><b>ACEITO</b></font>', CELULA), nome, ""]
                       for nome in sorted({a["projeto_nome"] for a in alocacoes})]
        if linhas:
            w = LARGURA_UTIL
            h.append(_tabela(["Situação", "Projeto", "Motivo"], linhas, [w * .15, w * .35, w * .50]))
        if aceitos is None:
            h += [Spacer(1, 4), Paragraph("Motivos de recusa só ficam disponíveis para a execução gerada na "
                                          "sessão atual.", PEQ)]

    h.append(KeepTogether([
        _secao("Nota metodológica"),
        Paragraph("Resultado obtido pela resolução exata do modelo de Programação Linear Inteira Mista via solver "
                  "CBC (branch-and-cut), por meio da biblioteca PuLP. A disponibilidade de cada analista desconta as "
                  "horas já comprometidas em execuções confirmadas (soma cumulativa, liberada ao encerrar a "
                  "execução ou ao fim do prazo do projeto).", CORPO),
    ]))
    doc.build(h)
    return buf.getvalue()
