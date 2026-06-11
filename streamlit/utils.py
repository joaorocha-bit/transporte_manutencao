"""
Funções auxiliares: leitura do Google Sheets, cálculo de status e persistência de histórico.
"""

import pandas as pd
import streamlit as st
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta

# ── CONFIGURAÇÕES DE PRAZO ────────────────────────────────────────────────────
PRAZO_HIGIENIZACAO_DIAS  = 180   # semestral (~6 meses)
PRAZO_MANUTENCAO_DIAS    = 365   # anual
VIDA_UTIL_ANOS           = 10    # anos de vida útil estimada

ALERTA_HIGIENIZACAO_DIAS = 30
ALERTA_MANUTENCAO_DIAS   = 60
ALERTA_VIDA_UTIL_ANOS    = 1

# ── MAPEAMENTO DE COLUNAS ─────────────────────────────────────────────────────
# Chave = nome interno usado no app  |  Valor = cabeçalho EXATO na sua planilha
MAPA_COLUNAS = {
    "nome":              "EQUIPAMENTO",
    "tipo":              "Tipo",
    "local":             "LOCALIZAÇÃO DO EQUIPAMENTO",
    "numero_serie":      "Nº DE SÉRIE",
    "patrimonio_antigo": "Nº DE PATRIMÔNIO ANTIGO",
    "patrimonio_novo":   "Nº DE PATRIMÔNIO NOVO",
    "data_higienizacao": "DATA ETIQUETA HIGIENIZAÇÃO",
    "data_manutencao":   "DATA ETIQUETA MANUTENÇÃO",
    "data_verificacao":  "DATA DE VERIFICAÇÃO",
    "suporte_torpedo":   "TEM SUPORTE DE TORPEDO?",
    "data_aquisicao":    "Data de Aquisição",
    "necessidades":      "Necessidades",
}

ABA_PRINCIPAL = "Consolidado"
ABA_HISTORICO = "historico"

CABECALHO_HISTORICO = [
    "timestamp", "item_nome", "item_patrimonio", "tipo_ocorrencia",
    "data_ocorrencia", "responsavel", "observacoes", "novo_local",
    "necessidade", "status_ocorrencia", "data_finalizacao",
]


# ── CARREGA DADOS ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def carregar_dados(_gc, spreadsheet_id: str):
    sh = _gc.open_by_key(spreadsheet_id)

    # Aba principal
    try:
        ws_main = sh.worksheet(ABA_PRINCIPAL)
    except Exception:
        ws_main = sh.get_worksheet(0)

    registros = ws_main.get_all_records(numericise_ignore=["all"])
    df = pd.DataFrame(registros)

    col_map_inv = {v.strip(): k for k, v in MAPA_COLUNAS.items()}
    df.columns  = [col_map_inv.get(c.strip(), c.strip()) for c in df.columns]

    for col in MAPA_COLUNAS:
        if col not in df.columns:
            df[col] = ""

    for col in ["data_higienizacao", "data_manutencao", "data_verificacao", "data_aquisicao"]:
        df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

    df["_row"] = range(2, len(df) + 2)

    # Aba histórico
    try:
        ws_hist      = sh.worksheet(ABA_HISTORICO)
        hist_records = ws_hist.get_all_records()
        df_hist      = pd.DataFrame(hist_records)
        for col in ["status_ocorrencia", "data_finalizacao"]:
            if col not in df_hist.columns:
                df_hist[col] = ""
        df_hist["_row"] = range(2, len(df_hist) + 2)
    except Exception:
        df_hist = pd.DataFrame(columns=CABECALHO_HISTORICO + ["_row"])

    return df, df_hist


# ── SALVA HISTÓRICO ────────────────────────────────────────────────────────────
def salvar_historico(_gc, spreadsheet_id: str, registro: dict):
    sh = _gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(ABA_HISTORICO)
    except Exception:
        ws = sh.add_worksheet(title=ABA_HISTORICO, rows=1000, cols=len(CABECALHO_HISTORICO))
        ws.append_row(CABECALHO_HISTORICO)

    if "status_ocorrencia" not in registro:
        registro["status_ocorrencia"] = "Aberta"

    linha = [registro.get(c, "") for c in CABECALHO_HISTORICO]
    ws.append_row(linha)


# ── ATUALIZA LINHA NO HISTÓRICO ────────────────────────────────────────────────
def atualizar_historico(_gc, spreadsheet_id: str, row_index: int, updates: dict):
    sh = _gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(ABA_HISTORICO)
    except Exception:
        return

    cabecalho = [c.strip() for c in ws.row_values(1)]
    for campo, valor in updates.items():
        try:
            col_idx = cabecalho.index(campo) + 1
            if isinstance(valor, (datetime, date)):
                valor = valor.strftime("%d/%m/%Y")
            ws.update_cell(row_index, col_idx, valor)
        except ValueError:
            continue


# ── ATUALIZA ITEM NA ABA PRINCIPAL ─────────────────────────────────────────────
def atualizar_item(_gc, spreadsheet_id: str, row_index: int, updates: dict):
    """
    Atualiza células de uma linha na aba principal.
    `updates` = {nome_interno: novo_valor}
    Aceita tanto campos de texto quanto objetos date/datetime.
    """
    sh = _gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(ABA_PRINCIPAL)
    except Exception:
        ws = sh.get_worksheet(0)

    cabecalho    = ws.row_values(1)
    cab_stripped = [c.strip() for c in cabecalho]

    for campo_interno, valor in updates.items():
        nome_planilha = MAPA_COLUNAS.get(campo_interno, campo_interno)
        try:
            col_idx = cab_stripped.index(nome_planilha) + 1
        except ValueError:
            continue  # coluna não encontrada na planilha, ignora

        # Formata datas
        if isinstance(valor, (datetime, date)):
            valor = valor.strftime("%d/%m/%Y")
        elif valor is None:
            valor = ""

        ws.update_cell(row_index, col_idx, valor)


# ── FUNÇÕES DE STATUS ──────────────────────────────────────────────────────────
def calcular_status_higienizacao(data) -> str:
    if pd.isna(data):
        return "sem_data"
    hoje = pd.Timestamp.today()
    dias = (hoje - data).days
    if dias >= PRAZO_HIGIENIZACAO_DIAS:
        return "critico"
    if dias >= PRAZO_HIGIENIZACAO_DIAS - ALERTA_HIGIENIZACAO_DIAS:
        return "alerta"
    return "ok"


def calcular_status_manutencao(data) -> str:
    if pd.isna(data):
        return "sem_data"
    hoje = pd.Timestamp.today()
    dias = (hoje - data).days
    if dias >= PRAZO_MANUTENCAO_DIAS:
        return "critico"
    if dias >= PRAZO_MANUTENCAO_DIAS - ALERTA_MANUTENCAO_DIAS:
        return "alerta"
    return "ok"


def calcular_status_vida_util(data) -> str:
    if pd.isna(data):
        return "sem_data"
    hoje  = pd.Timestamp.today()
    anos  = (hoje - data).days / 365.25
    if anos >= VIDA_UTIL_ANOS:
        return "critico"
    if anos >= VIDA_UTIL_ANOS - ALERTA_VIDA_UTIL_ANOS:
        return "alerta"
    return "ok"


def carregar_historico(_gc, spreadsheet_id: str) -> pd.DataFrame:
    sh = _gc.open_by_key(spreadsheet_id)
    try:
        ws      = sh.worksheet(ABA_HISTORICO)
        df_hist = pd.DataFrame(ws.get_all_records())
        if not df_hist.empty:
            df_hist["_row"] = range(2, len(df_hist) + 2)
        return df_hist
    except Exception:
        return pd.DataFrame()
