"""Gera o relatorio de uma execucao em PDF estilizado (reportlab, Python puro).

Uso: gerar_pdf(execucao, alocacoes, aceitos=None, recusados=None, resumo_analistas=None) -> bytes
- execucao: linha da tabela execucoes (acesso por chave)
- alocacoes: lista de dicts de db.list_alocacoes_execucao
- aceitos/recusados: so' existem para a execucao gerada na sessao atual (opcionais)
- resumo_analistas: mantido por compatibilidade (nao usado no layout atual)
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

LARANJA = colors.HexColor("#F26A1B")
LARANJA_SUAVE = colors.HexColor("#FDEBDD")
LARANJA_NOTA = colors.HexColor("#FFF0E6")
GRAFITE = colors.HexColor("#1F2328")
CINZA = colors.HexColor("#6B7280")
BORDA = colors.HexColor("#E5E7EB")
ZEBRA = colors.HexColor("#FBF8F6")
VERDE_BG, VERDE_TX = colors.HexColor("#E3F4E8"), colors.HexColor("#1E7B3A")
VERM_BG, VERM_TX = colors.HexColor("#FDE8E8"), colors.HexColor("#B91C1C")

LARGURA, ALTURA = A4
MARGEM = 18 * mm
W = LARGURA - 2 * MARGEM

CORPO = ParagraphStyle("corpo", fontName="Helvetica", fontSize=9.5, leading=14, textColor=GRAFITE)
CEL = ParagraphStyle("cel", fontName="Helvetica", fontSize=8.8, leading=11, textColor=GRAFITE)
CEL_B = ParagraphStyle("celb", parent=CEL, fontName="Helvetica-Bold")
CEL_D = ParagraphStyle("celd", parent=CEL, alignment=TA_RIGHT)
TH = ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=CINZA)
TH_D = ParagraphStyle("thd", parent=TH, alignment=TA_RIGHT)
NOTA = ParagraphStyle("nota", fontName="Helvetica", fontSize=8, leading=11, textColor=CINZA)


def _num(v: float, casas: int = 2) -> str:
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _brl(v: float) -> str:
    return "R$ " + _num(v)


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _data_br(txt) -> str:
    s = str(txt)
    try:
        return datetime.fromisoformat(s.replace("Z", "")).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return s


# ---------------------------------------------------------------- flowables

class _Cabecalho(Flowable):
    def __init__(self, selo: str):
        super().__init__()
        self.selo = selo

    def wrap(self, aw, ah):
        self.width = aw
        return aw, 30 * mm

    def draw(self):
        c, h = self.canv, 30 * mm
        c.setFont("Helvetica-Bold", 22)
        y1 = h - 8 * mm
        c.setFillColor(GRAFITE)
        c.drawString(0, y1, "Relatório de ")
        x = c.stringWidth("Relatório de ", "Helvetica-Bold", 22)
        c.setFillColor(LARANJA)
        c.drawString(x, y1, "Alocação Ótima")
        c.setFillColor(GRAFITE)
        c.drawString(0, y1 - 9 * mm, "de Analistas")
        c.setFont("Helvetica", 9)
        c.setFillColor(CINZA)
        c.drawString(0, y1 - 15.5 * mm, "Sistema de Apoio à Decisão · Programação Linear Inteira Mista (PuLP/CBC)")
        c.setFont("Helvetica-Bold", 9)
        tw = c.stringWidth(self.selo, "Helvetica-Bold", 9)
        pw, ph = tw + 12 * mm, 9 * mm
        px, py = self.width - pw, h - 15 * mm
        c.setFillColor(LARANJA_SUAVE)
        c.roundRect(px, py, pw, ph, ph / 2, stroke=0, fill=1)
        c.setFillColor(LARANJA)
        c.drawCentredString(px + pw / 2, py + 3.1 * mm, self.selo)


class _CaixaMeta(Flowable):
    def __init__(self, itens):
        super().__init__()
        self.itens = itens

    def wrap(self, aw, ah):
        self.width = aw
        return aw, 20 * mm

    def draw(self):
        c, h = self.canv, 20 * mm
        c.setStrokeColor(BORDA)
        c.setLineWidth(0.8)
        c.setFillColor(colors.white)
        c.roundRect(0, 0, self.width, h, 3 * mm, stroke=1, fill=1)
        larguras = [0.27, 0.22, 0.30, 0.21]
        x = 5 * mm
        for (rot, val), frac in zip(self.itens, larguras):
            c.setFont("Helvetica", 8.5)
            c.setFillColor(CINZA)
            if "_" in rot:  # notacao com subscrito: "Parâmetro h_min" -> h com "min" abaixo
                base, sub = rot.split("_", 1)
                c.drawString(x, h - 7.5 * mm, base)
                bx = x + c.stringWidth(base, "Helvetica", 8.5)
                c.setFont("Helvetica", 6)
                c.drawString(bx, h - 8.9 * mm, sub)
                c.setFont("Helvetica", 8.5)
            else:
                c.drawString(x, h - 7.5 * mm, rot)
            c.setFont("Helvetica-Bold", 10.5)
            c.setFillColor(GRAFITE)
            c.drawString(x, h - 13.5 * mm, val)
            x += (self.width - 5 * mm) * frac


class _Secao(Flowable):
    def __init__(self, numero: int, titulo: str):
        super().__init__()
        self.numero, self.titulo = numero, titulo

    def wrap(self, aw, ah):
        self.width = aw
        return aw, 12 * mm

    def draw(self):
        c = self.canv
        c.setFillColor(LARANJA)
        c.circle(3.2 * mm, 5 * mm, 3.2 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawCentredString(3.2 * mm, 3.9 * mm, str(self.numero))
        c.setFillColor(GRAFITE)
        c.setFont("Helvetica-Bold", 12.5)
        c.drawString(10 * mm, 3.6 * mm, self.titulo)


class _Cartoes(Flowable):
    """Quatro cartoes de KPI; o primeiro e' preenchido em laranja, o ultimo tem barra de progresso."""

    def __init__(self, lucro, receita, custo, taxa):
        super().__init__()
        self.d = (lucro, receita, custo, taxa)

    def wrap(self, aw, ah):
        self.width = aw
        return aw, 27 * mm

    def draw(self):
        c, h = self.canv, 27 * mm
        gap = 3.5 * mm
        w = (self.width - 3 * gap) / 4
        lucro, receita, custo, taxa = self.d
        rotulos = ["Lucro líquido total", "Receita total", "Custo total alocado", "Taxa de ocupação"]
        valores = [_brl(lucro), _brl(receita), _brl(custo), f"{_num(taxa, 1)}%" if taxa is not None else "—"]
        for i in range(4):
            x = i * (w + gap)
            if i == 0:
                c.setFillColor(LARANJA)
                c.roundRect(x, 0, w, h, 3 * mm, stroke=0, fill=1)
                cor_r, cor_v = colors.white, colors.white
            else:
                c.setStrokeColor(BORDA)
                c.setLineWidth(0.8)
                c.setFillColor(colors.white)
                c.roundRect(x, 0, w, h, 3 * mm, stroke=1, fill=1)
                cor_r, cor_v = CINZA, GRAFITE
            c.setFillColor(cor_r)
            c.setFont("Helvetica", 8)
            c.drawString(x + 4.5 * mm, h - 7 * mm, rotulos[i])
            c.setFillColor(cor_v)
            c.setFont("Helvetica-Bold", 13 if i < 3 else 14)
            c.drawString(x + 4.5 * mm, h - 14.5 * mm, valores[i])
            if i == 3 and taxa is not None:
                bw = w - 9 * mm
                c.setFillColor(BORDA)
                c.roundRect(x + 4.5 * mm, 4.5 * mm, bw, 1.6 * mm, 0.8 * mm, stroke=0, fill=1)
                c.setFillColor(LARANJA)
                c.roundRect(x + 4.5 * mm, 4.5 * mm, max(1.6 * mm, bw * min(max(taxa, 0), 100) / 100),
                            1.6 * mm, 0.8 * mm, stroke=0, fill=1)


class _CartaoProjeto(Flowable):
    """Cartao arredondado com selo (Aceito/Recusado), nome do projeto e motivo opcional."""
    FONT, TAM = "Helvetica", 9.3

    def __init__(self, nome, aceito=True, motivo=""):
        super().__init__()
        self.nome, self.aceito, self.motivo = nome, aceito, motivo

    def wrap(self, aw, ah):
        self.width = aw
        self.sw = 17 * mm if self.aceito else 20 * mm
        self.l_nome = simpleSplit(self.nome, self.FONT, self.TAM, aw - self.sw - 12 * mm)
        self.l_mot = simpleSplit(self.motivo, self.FONT, 8, aw - self.sw - 12 * mm) if self.motivo else []
        self.height = max(11 * mm, (len(self.l_nome) * 4.2 + len(self.l_mot) * 3.6) * mm + 6 * mm)
        return aw, self.height

    def draw(self):
        c, h = self.canv, self.height
        c.setStrokeColor(BORDA)
        c.setLineWidth(0.8)
        c.setFillColor(colors.white)
        c.roundRect(0, 0, self.width, h, 3 * mm, stroke=1, fill=1)
        bg, tx = (VERDE_BG, VERDE_TX) if self.aceito else (VERM_BG, VERM_TX)
        cy = h / 2
        c.setFillColor(bg)
        c.roundRect(4 * mm, cy - 2.7 * mm, self.sw, 5.4 * mm, 2.7 * mm, stroke=0, fill=1)
        c.setFillColor(tx)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(4 * mm + self.sw / 2, cy - 1 * mm, "Aceito" if self.aceito else "Recusado")
        x = 4 * mm + self.sw + 4 * mm
        n_l, n_m = len(self.l_nome), len(self.l_mot)
        topo = cy + ((n_l * 4.2 + n_m * 3.6) / 2) * mm
        y = topo - 3.3 * mm
        c.setFillColor(GRAFITE)
        c.setFont(self.FONT, self.TAM)
        for ln in self.l_nome:
            c.drawString(x, y, ln)
            y -= 4.2 * mm
        c.setFillColor(CINZA)
        c.setFont(self.FONT, 8)
        for ln in self.l_mot:
            c.drawString(x, y + 0.4 * mm, ln)
            y -= 3.6 * mm


class _NotaMetodologica(Flowable):
    TEXTO = ("Resultado obtido pela resolução exata do modelo de Programação Linear Inteira Mista via solver CBC "
             "(branch-and-cut), por meio da biblioteca PuLP. A disponibilidade de cada analista desconta as horas "
             "já comprometidas em execuções confirmadas (soma cumulativa, liberada somente ao encerrar uma "
             "execução).")

    def wrap(self, aw, ah):
        self.width = aw
        self.linhas = simpleSplit(self.TEXTO, "Helvetica", 9.5, aw - 14 * mm)
        self.height = len(self.linhas) * 5 * mm + 9 * mm
        return aw, self.height

    def draw(self):
        c, h = self.canv, self.height
        c.setFillColor(LARANJA_NOTA)
        c.roundRect(0, 0, self.width, h, 2.5 * mm, stroke=0, fill=1)
        c.setFillColor(LARANJA)
        c.roundRect(0, 0, 1.6 * mm, h, 0.8 * mm, stroke=0, fill=1)
        c.setFillColor(GRAFITE)
        c.setFont("Helvetica", 9.5)
        y = h - 6.5 * mm
        for ln in self.linhas:
            c.drawString(7 * mm, y, ln)
            y -= 5 * mm


# ---------------------------------------------------------------- pagina

class _CanvasNumerado(_canvas.Canvas):
    """Canvas de duas passadas para escrever 'Pagina X de Y' no rodape."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._paginas = []

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            self._rodape(total)
            super().showPage()
        super().save()

    def _rodape(self, total):
        self.setFillColor(LARANJA)
        self.rect(0, ALTURA - 7 * mm, LARGURA, 7 * mm, stroke=0, fill=1)
        self.setStrokeColor(BORDA)
        self.setLineWidth(0.8)
        self.line(MARGEM, 17 * mm, LARGURA - MARGEM, 17 * mm)
        self.setFillColor(CINZA)
        self.setFont("Helvetica", 8.5)
        self.drawString(MARGEM, 11.5 * mm, "Relatório gerado pelo sistema de alocação de analistas")
        self.drawRightString(LARGURA - MARGEM, 11.5 * mm, f"Página {self._pageNumber} de {total}")


def _tabela_alocacoes(alocacoes):
    cab = [Paragraph("ANALISTA", TH), Paragraph("PROJETO", TH), Paragraph("HORAS", TH_D),
           Paragraph("CUSTO", TH_D), Paragraph("RECEITA GERADA", TH_D)]
    dados = [cab]
    for a in alocacoes:
        dados.append([Paragraph(_esc(a["analista_nome"]), CEL_B), Paragraph(_esc(a["projeto_nome"]), CEL),
                      Paragraph(f"{_num(a['horas'], 1)} h", CEL_D), Paragraph(_brl(a["custo"]), CEL_D),
                      Paragraph(_brl(a["receita"]), CEL_D)])
    t = Table(dados, colWidths=[W * .20, W * .36, W * .11, W * .15, W * .18], repeatRows=1)
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 1.4, LARANJA),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, BORDA),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _grade_projetos(cartoes):
    gap = 4 * mm
    cw = (W - gap) / 2
    linhas = []
    for i in range(0, len(cartoes), 2):
        par = cartoes[i:i + 2]
        linhas.append(par + [""] * (2 - len(par)))
    t = Table([[c[0], "", c[1]] for c in linhas], colWidths=[cw, gap, cw])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
    ]))
    return t


def gerar_pdf(execucao, alocacoes: Iterable[dict], aceitos=None, recusados=None, resumo_analistas=None) -> bytes:
    alocacoes = list(alocacoes)
    id_exec = execucao["id_execucao"]
    situacao = str(execucao["situacao"])
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=MARGEM, rightMargin=MARGEM,
                          topMargin=18 * mm, bottomMargin=22 * mm,
                          title=f"Relatório da execução #{id_exec}", author="SAD Alocação Ótima")
    doc.addPageTemplates([PageTemplate(id="p", frames=[
        Frame(MARGEM, 22 * mm, W, ALTURA - 22 * mm - 18 * mm, leftPadding=0, rightPadding=0,
              topPadding=0, bottomPadding=0)])])

    tempo = execucao["tempo_processamento_s"]
    h = [
        _Cabecalho(f"EXECUÇÃO #{id_exec} · {situacao.upper()}"), Spacer(1, 3 * mm),
        _CaixaMeta([
            ("Data da execução", _data_br(execucao["executado_em"])),
            ("Parâmetro h_min", f"{_num(float(execucao['h_min']), 1)} h"),
            ("Tempo de processamento CBC", f"{_num(tempo, 3)} s" if tempo is not None else "—"),
            ("Situação", situacao.capitalize()),
        ]),
        Spacer(1, 6 * mm),
    ]

    if not execucao["viavel"]:
        h += [_Secao(1, "Resultado geral"),
              Paragraph(f"O modelo foi considerado <b>inviável</b> (status do solver: {_esc(execucao['status'])}). "
                        "Nenhuma alocação foi gerada para esta execução.", CORPO)]
    else:
        h += [_Secao(1, "Resultado geral"), Spacer(1, 1 * mm),
              _Cartoes(execucao["lucro_liquido"], execucao["receita_total"], execucao["custo_total"],
                       execucao["taxa_ocupacao_equipe"]),
              Spacer(1, 6 * mm), _Secao(2, "Alocação detalhada"), Spacer(1, 1 * mm)]
        if alocacoes:
            h.append(_tabela_alocacoes(alocacoes))
        else:
            h.append(Paragraph("Nenhuma alocação realizada.", CORPO))

        h += [Spacer(1, 6 * mm)]
        cartoes = []
        if aceitos is not None:
            cartoes += [_CartaoProjeto(n, True) for n in aceitos]
            cartoes += [_CartaoProjeto(n, False, m) for n, m in (recusados or [])]
        else:
            cartoes += [_CartaoProjeto(n, True) for n in sorted({a["projeto_nome"] for a in alocacoes})]
        bloco = [_Secao(3, "Projetos aceitos e recusados"), Spacer(1, 1 * mm)]
        if cartoes:
            bloco.append(_grade_projetos(cartoes))
        if aceitos is None:
            bloco.append(Paragraph(
                f"Os {len(cartoes)} projetos considerados nesta execução foram aceitos. Os motivos de recusa não "
                "estão disponíveis porque só ficam registrados na sessão em que a execução foi gerada.", NOTA))
        h += [KeepTogether(bloco[:3])] + bloco[3:]

    h += [Spacer(1, 6 * mm), KeepTogether([_Secao(4, "Nota metodológica"), Spacer(1, 1 * mm),
                                           _NotaMetodologica()])]
    doc.build(h, canvasmaker=_CanvasNumerado)
    return buf.getvalue()
