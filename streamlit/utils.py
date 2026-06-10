"""
Funções auxiliares: leitura do Google Sheets, cálculo de status e persistência de histórico.
"""

import pandas as pd
import streamlit as st
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta

# ── CONFIGURAÇÕES DE PRAZO ────────────────────────────────────────────────────
PRAZO_HIGIENIZACAO_DIAS = 180   # semestral  (~6 meses)
PRAZO_MANUTENCAO_DIAS   = 365   # anual
VIDA_UTIL_ANOS          = 10    # anos de vida útil estimada

# Limiar de alerta: quanto antes do vencimento já marca como "alerta"
ALERTA_HIGIENIZACAO_DIAS = 30
ALERTA_MANUTENCAO_DIAS   = 60
ALERTA_VIDA_UTIL_ANOS    = 1

# ── MAPEAMENTO DE COLUNAS ─────────────────────────────────────────────────────
# Ajuste as chaves abaixo para os nomes EXATOS das colunas na sua planilha.
MAPA_COLUNAS = {
    "nome":              "F",                   # nome do item
    "tipo":              "Tipo",                   # Maca / Cadeira de Rodas
    "local":             "LOCALIZAÇÃO DO EQUIPAMENTO",
    "numero_serie":      "Nº DE SÉRIE",
    "patrimonio_antigo": "Nº DE PATRIMÔNIO ANTIGO",
    "patrimonio_novo":   "Nº DE PATRIMÔNIO NOVO",
    "data_higienizacao": "DATA ETIQUETA HIGIENIZAÇÃO",      # coluna de data de higienização feita
    "data_manutencao":   "DATA ETIQUETA MANUTENÇÃO",        # coluna de data de manutenção feita
    "data_verificacao":  "DATA DE VERIFICAÇÃO",
    "suporte_torpedo":   "TEM SUPORTE DE TORPEDO?",
    "data_aquisicao":    "Data de Aquisição",      # se existir na planilha
    "necessidades":      "Necessidades",           # pendências de manutenção
}

# Nome da aba principal e da aba de histórico
ABA_PRINCIPAL = "Consolidado"        # altere se necessário
ABA_HISTORICO = "historico"        # será criada automaticamente se não existir


# ── CARREGA DADOS ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def carregar_dados(_gc, spreadsheet_id: str):
    """Lê a aba principal e a aba de histórico do Google Sheets."""
    sh = _gc.open_by_key(spreadsheet_id)

    # ── Aba principal ──
    try:
        ws_main = sh.worksheet(ABA_PRINCIPAL)
    except Exception:
        ws_main = sh.get_worksheet(0)

    registros = ws_main.get_all_records(numericise_ignore=["all"])
    df = pd.DataFrame(registros)

    # Renomeia para nomes internos (tolerante a espaços)
    col_map_inv = {v.strip(): k for k, v in MAPA_COLUNAS.items()}
    df.columns = [col_map_inv.get(c.strip(), c.strip()) for c in df.columns]

    # Garante colunas obrigatórias
    for col in MAPA_COLUNAS:
        if col not in df.columns:
            df[col] = ""

    # Converte datas
    for col in ["data_higienizacao", "data_manutencao", "data_verificacao", "data_aquisicao"]:
        df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

    # Guarda número da linha na planilha (1-indexed; linha 1 = cabeçalho)
    df["_row"] = range(2, len(df) + 2)

    # ── Aba histórico ──
    try:
        ws_hist = sh.worksheet(ABA_HISTORICO)
        hist_records = ws_hist.get_all_records()
        df_hist = pd.DataFrame(hist_records)
    except Exception:
        df_hist = pd.DataFrame(columns=[
            "timestamp","item_nome","item_patrimonio","tipo_ocorrencia",
            "data_ocorrencia","responsavel","observacoes","novo_local","necessidade"
        ])

    return df, df_hist


# ── SALVA HISTÓRICO ────────────────────────────────────────────────────────────
def salvar_historico(_gc, spreadsheet_id: str, registro: dict):
    """Appenda uma linha na aba de histórico. Cria a aba se não existir."""
    sh = _gc.open_by_key(spreadsheet_id)
    cabecalho = ["timestamp","item_nome","item_patrimonio","tipo_ocorrencia",
                 "data_ocorrencia","responsavel","observacoes","novo_local","necessidade"]
    try:
        ws = sh.worksheet(ABA_HISTORICO)
    except Exception:
        ws = sh.add_worksheet(title=ABA_HISTORICO, rows=1000, cols=len(cabecalho))
        ws.append_row(cabecalho)

    linha = [registro.get(c, "") for c in cabecalho]
    ws.append_row(linha)


# ── ATUALIZA ITEM NA ABA PRINCIPAL ─────────────────────────────────────────────
def atualizar_item(_gc, spreadsheet_id: str, row_index: int, updates: dict):
    """
    Atualiza células de uma linha específica na aba principal.
    `updates` é um dict {nome_interno: novo_valor}.
    """
    sh = _gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(ABA_PRINCIPAL)
    except Exception:
        ws = sh.get_worksheet(0)

    cabecalho = ws.row_values(1)
    col_map_inv = {k: v for k, v in MAPA_COLUNAS.items()}  # interno → planilha

    for campo_interno, valor in updates.items():
        nome_planilha = col_map_inv.get(campo_interno, campo_interno)
        # Acha a coluna pelo cabeçalho
        try:
            col_idx = [c.strip() for c in cabecalho].index(nome_planilha) + 1
        except ValueError:
            continue  # coluna não encontrada, pula
        # Formata data como string se necessário
        if isinstance(valor, (datetime, date)):
            valor = valor.strftime("%d/%m/%Y")
        ws.update_cell(row_index, col_idx, valor)


# ── FUNÇÕES DE STATUS ──────────────────────────────────────────────────────────
def calcular_status_higienizacao(data) -> str:
    """Retorna 'ok', 'alerta', 'critico' ou 'sem_data'."""
    if pd.isna(data):
        return "sem_data"
    hoje = pd.Timestamp.today()
    dias_passados = (hoje - data).days
    if dias_passados >= PRAZO_HIGIENIZACAO_DIAS:
        return "critico"
    if dias_passados >= PRAZO_HIGIENIZACAO_DIAS - ALERTA_HIGIENIZACAO_DIAS:
        return "alerta"
    return "ok"


def calcular_status_manutencao(data) -> str:
    if pd.isna(data):
        return "sem_data"
    hoje = pd.Timestamp.today()
    dias_passados = (hoje - data).days
    if dias_passados >= PRAZO_MANUTENCAO_DIAS:
        return "critico"
    if dias_passados >= PRAZO_MANUTENCAO_DIAS - ALERTA_MANUTENCAO_DIAS:
        return "alerta"
    return "ok"


def calcular_status_vida_util(data) -> str:
    if pd.isna(data):
        return "sem_data"
    hoje = pd.Timestamp.today()
    anos = (hoje - data).days / 365.25
    if anos >= VIDA_UTIL_ANOS:
        return "critico"
    if anos >= VIDA_UTIL_ANOS - ALERTA_VIDA_UTIL_ANOS:
        return "alerta"
    return "ok"


def carregar_historico(_gc, spreadsheet_id: str) -> pd.DataFrame:
    """Lê apenas a aba de histórico (sem cache, para uso direto)."""
    sh = _gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(ABA_HISTORICO)
        return pd.DataFrame(ws.get_all_records())
    except Exception:
        return pd.DataFrame()
