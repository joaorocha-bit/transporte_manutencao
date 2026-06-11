"""
App de Gestão de Equipamentos Hospitalares
Macas e Cadeiras de Rodas
"""

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date, timedelta
import json
import plotly.graph_objects as go
import plotly.express as px
from utils import (
    carregar_dados,
    salvar_historico,
    carregar_historico,
    calcular_status_higienizacao,
    calcular_status_manutencao,
    calcular_status_vida_util,
    atualizar_item,
    atualizar_historico,
    PRAZO_HIGIENIZACAO_DIAS,
    PRAZO_MANUTENCAO_DIAS,
    VIDA_UTIL_ANOS,
    ALERTA_HIGIENIZACAO_DIAS,
    ALERTA_MANUTENCAO_DIAS,
    ALERTA_VIDA_UTIL_ANOS,
    MAPA_COLUNAS,
)

st.set_page_config(
    page_title="Gestão de Equipamentos",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .main { background-color: #F0F4F8; }

    .metric-card {
        background: white;
        border-radius: 12px;
        padding: 20px 24px;
        border-left: 4px solid #2563EB;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
        margin-bottom: 8px;
    }
    .metric-card.verde   { border-left-color: #16A34A; }
    .metric-card.amarelo { border-left-color: #D97706; }
    .metric-card.vermelho{ border-left-color: #DC2626; }

    .metric-value { font-size: 2rem; font-weight: 700; color: #1E293B; line-height:1; }
    .metric-label { font-size: 0.8rem; color: #64748B; margin-top: 4px; text-transform: uppercase; letter-spacing: .05em; }

    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-ok       { background:#DCFCE7; color:#166534; }
    .badge-alerta   { background:#FEF9C3; color:#854D0E; }
    .badge-critico  { background:#FEE2E2; color:#991B1B; }
    .badge-sem-data { background:#F1F5F9; color:#475569; }

    .section-title {
        font-size: 1.1rem; font-weight: 600;
        color: #1E293B; margin: 24px 0 12px;
        padding-bottom: 6px;
        border-bottom: 2px solid #E2E8F0;
    }

    .legend-box {
        background: white;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.07);
        font-size: 0.82rem;
        color: #334155;
    }
    .legend-box strong { color: #1E293B; }
    .legend-row { display: flex; gap: 24px; flex-wrap: wrap; margin-top: 6px; }
    .legend-item { display: flex; align-items: center; gap: 6px; }
    .dot { width: 10px; height: 10px; border-radius: 50%; display:inline-block; }
    .dot-ok      { background: #16A34A; }
    .dot-alerta  { background: #D97706; }
    .dot-critico { background: #DC2626; }
    .dot-semdata { background: #94A3B8; }

    div[data-testid="stSidebar"] { background: #1E293B; }
    div[data-testid="stSidebar"] * { color: #CBD5E1 !important; }
    div[data-testid="stSidebar"] .stSelectbox label,
    div[data-testid="stSidebar"] h1,
    div[data-testid="stSidebar"] h2,
    div[data-testid="stSidebar"] h3 { color: #F8FAFC !important; }
</style>
""", unsafe_allow_html=True)


# ── AUTENTICAÇÃO GOOGLE SHEETS ───────────────────────────────────────────────
@st.cache_resource
def conectar_sheets():
    creds_dict = st.secrets["gcp_service_account"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


def get_client():
    return conectar_sheets()


# ── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏥 Equipamentos")
    st.markdown("---")
    pagina = st.radio(
        "Navegação",
        [
            "📊 Dashboard",
            "📋 Inventário",
            "✏️ Lançar Ocorrência",
            "📜 Histórico",
        ],
        label_visibility="collapsed",
    )
    st.markdown("---")
    tipo_filtro = st.selectbox("Tipo de equipamento", ["Todos", "Maca", "Cadeira de Rodas"])
    st.markdown("---")
    st.caption("Atualizado em: " + datetime.now().strftime("%d/%m/%Y %H:%M"))
    if st.button("🔄 Recarregar dados"):
        st.cache_data.clear()
        st.rerun()


# ── CARREGA DADOS ─────────────────────────────────────────────────────────────
try:
    gc = get_client()
    spreadsheet_id = st.secrets["spreadsheet"]["id"]
    df, df_historico = carregar_dados(gc, spreadsheet_id)
except Exception as e:
    st.error(f"Erro ao conectar ao Google Sheets: {e}")
    st.info("Verifique se configurou corretamente o `.streamlit/secrets.toml`.")
    st.stop()

# Aplica filtro de tipo
if tipo_filtro != "Todos":
    df_view = df[df["tipo"].str.upper() == tipo_filtro.upper()].copy()
else:
    df_view = df.copy()


# ═══════════════════════════════════════════════════════════════════════════════
# PÁGINA: DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
if pagina == "📊 Dashboard":
    st.markdown("# Dashboard de Equipamentos")
    st.markdown(f"**{len(df_view)} itens** carregados · filtro: *{tipo_filtro}*")

    total_macas    = len(df[df["tipo"].str.upper() == "MACA"])
    total_cadeiras = len(df[df["tipo"].str.upper() == "CADEIRA DE RODAS"])

    df_view["status_hig"]  = df_view["data_higienizacao"].apply(calcular_status_higienizacao)
    df_view["status_man"]  = df_view["data_manutencao"].apply(calcular_status_manutencao)
    df_view["status_vida"] = df_view["data_aquisicao"].apply(calcular_status_vida_util)

    hig_ok      = (df_view["status_hig"] == "ok").sum()
    hig_alerta  = (df_view["status_hig"] == "alerta").sum()
    hig_critico = (df_view["status_hig"] == "critico").sum()

    man_ok      = (df_view["status_man"] == "ok").sum()
    man_alerta  = (df_view["status_man"] == "alerta").sum()
    man_critico = (df_view["status_man"] == "critico").sum()

    if tipo_filtro != "Todos":
        df_hist_view = df_historico[df_historico["item_patrimonio"].isin(df_view["patrimonio_novo"])].copy()
    else:
        df_hist_view = df_historico.copy()

    if "status_ocorrencia" not in df_hist_view.columns:
        df_hist_view["status_ocorrencia"] = "Aberta"

    oc_abertas    = (df_hist_view["status_ocorrencia"].str.lower() != "finalizada").sum()
    oc_finalizadas = (df_hist_view["status_ocorrencia"].str.lower() == "finalizada").sum()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-value">{total_macas}</div>
            <div class="metric-label">Macas</div></div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-value">{total_cadeiras}</div>
            <div class="metric-label">Cadeiras de Rodas</div></div>""", unsafe_allow_html=True)
    with col3:
        cor_hig = "vermelho" if hig_critico > 0 else ("amarelo" if hig_alerta > 0 else "verde")
        st.markdown(f"""<div class="metric-card {cor_hig}">
            <div class="metric-value">{hig_critico + hig_alerta}</div>
            <div class="metric-label">Higienização pendente</div></div>""", unsafe_allow_html=True)
    with col4:
        cor_man = "vermelho" if man_critico > 0 else ("amarelo" if man_alerta > 0 else "verde")
        st.markdown(f"""<div class="metric-card {cor_man}">
            <div class="metric-value">{man_critico + man_alerta}</div>
            <div class="metric-label">Manutenção pendente</div></div>""", unsafe_allow_html=True)

    col_oc1, col_oc2 = st.columns(2)
    with col_oc1:
        cor_oc = "vermelho" if oc_abertas > 0 else "verde"
        st.markdown(f"""<div class="metric-card {cor_oc}">
            <div class="metric-value">{oc_abertas}</div>
            <div class="metric-label">📋 Ocorrências em Aberto</div></div>""", unsafe_allow_html=True)
    with col_oc2:
        st.markdown(f"""<div class="metric-card verde">
            <div class="metric-value">{oc_finalizadas}</div>
            <div class="metric-label">✅ Ocorrências Finalizadas</div></div>""", unsafe_allow_html=True)

    st.markdown("---")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown('<p class="section-title">Higienização (Semestral)</p>', unsafe_allow_html=True)
        fig_hig = go.Figure(go.Pie(
            labels=["Em dia", "Alerta", "Vencido"],
            values=[hig_ok, hig_alerta, hig_critico],
            hole=0.55,
            marker_colors=["#16A34A", "#D97706", "#DC2626"],
            textinfo="value+percent",
        ))
        fig_hig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=220,
                               showlegend=True, legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig_hig, use_container_width=True)

    with col_b:
        st.markdown('<p class="section-title">Manutenção Preventiva (Anual)</p>', unsafe_allow_html=True)
        fig_man = go.Figure(go.Pie(
            labels=["Em dia", "Alerta", "Vencido"],
            values=[man_ok, man_alerta, man_critico],
            hole=0.55,
            marker_colors=["#16A34A", "#D97706", "#DC2626"],
            textinfo="value+percent",
        ))
        fig_man.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=220,
                               showlegend=True, legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig_man, use_container_width=True)

    with col_c:
        st.markdown('<p class="section-title">Distribuição por Local</p>', unsafe_allow_html=True)
        locais = df_view["local"].value_counts().head(8)
        fig_loc = px.bar(
            x=locais.values, y=locais.index, orientation="h",
            color_discrete_sequence=["#2563EB"],
        )
        fig_loc.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=220,
                               xaxis_title="", yaxis_title="", showlegend=False)
        st.plotly_chart(fig_loc, use_container_width=True)

    st.markdown('<p class="section-title">⚠️ Itens que requerem atenção imediata</p>', unsafe_allow_html=True)
    criticos = df_view[
        (df_view["status_hig"] == "critico") | (df_view["status_man"] == "critico")
    ][["nome", "tipo", "local", "patrimonio_novo", "status_hig", "status_man"]].copy()

    if criticos.empty:
        st.success("Nenhum item crítico no momento. ✅")
    else:
        def badge(status):
            labels = {"ok": ("Em dia","badge-ok"), "alerta": ("Alerta","badge-alerta"),
                      "critico": ("Vencido","badge-critico"), "sem_data": ("Sem data","badge-sem-data")}
            txt, cls = labels.get(status, ("—","badge-sem-data"))
            return f'<span class="badge {cls}">{txt}</span>'
        criticos["Higienização"] = criticos["status_hig"].apply(badge)
        criticos["Manutenção"]   = criticos["status_man"].apply(badge)
        criticos = criticos.rename(columns={"nome":"Item","tipo":"Tipo","local":"Local","patrimonio_novo":"Patrimônio"})
        st.write(criticos[["Item","Tipo","Local","Patrimônio","Higienização","Manutenção"]].to_html(
            escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)

    st.markdown('<p class="section-title">🔧 Necessidades de Manutenção Registradas</p>', unsafe_allow_html=True)
    if "necessidades" in df_view.columns:
        pendencias = df_view[df_view["necessidades"].notna() & (df_view["necessidades"] != "")][
            ["nome", "tipo", "local", "patrimonio_novo", "necessidades"]
        ]
        if pendencias.empty:
            st.info("Nenhuma necessidade registrada.")
        else:
            st.dataframe(pendencias.rename(columns={
                "nome":"Item","tipo":"Tipo","local":"Local",
                "patrimonio_novo":"Patrimônio","necessidades":"Pendência"
            }), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PÁGINA: INVENTÁRIO
# ═══════════════════════════════════════════════════════════════════════════════
elif pagina == "📋 Inventário":
    st.markdown("# Inventário Completo")

    # ── LEGENDA DE STATUS ─────────────────────────────────────────────────────
    prazo_hig_alerta_inicio = PRAZO_HIGIENIZACAO_DIAS - ALERTA_HIGIENIZACAO_DIAS
    prazo_man_alerta_inicio = PRAZO_MANUTENCAO_DIAS   - ALERTA_MANUTENCAO_DIAS
    vida_alerta_inicio      = VIDA_UTIL_ANOS          - ALERTA_VIDA_UTIL_ANOS

    st.markdown(f"""
    <div class="legend-box">
        <strong>Legenda dos Status</strong>
        <div class="legend-row" style="margin-top:10px; gap:32px;">
            <div>
                <strong style="font-size:0.8rem; text-transform:uppercase; letter-spacing:.04em;">
                    💧 Higienização Terminal (semestral — {PRAZO_HIGIENIZACAO_DIAS} dias)
                </strong>
                <div class="legend-row" style="margin-top:4px;">
                    <div class="legend-item"><span class="dot dot-ok"></span> Em dia (≤ {prazo_hig_alerta_inicio} dias)</div>
                    <div class="legend-item"><span class="dot dot-alerta"></span> Alerta ({prazo_hig_alerta_inicio}–{PRAZO_HIGIENIZACAO_DIAS} dias)</div>
                    <div class="legend-item"><span class="dot dot-critico"></span> Vencido (> {PRAZO_HIGIENIZACAO_DIAS} dias)</div>
                    <div class="legend-item"><span class="dot dot-semdata"></span> Sem data registrada</div>
                </div>
            </div>
            <div>
                <strong style="font-size:0.8rem; text-transform:uppercase; letter-spacing:.04em;">
                    🔧 Manutenção Preventiva (anual — {PRAZO_MANUTENCAO_DIAS} dias)
                </strong>
                <div class="legend-row" style="margin-top:4px;">
                    <div class="legend-item"><span class="dot dot-ok"></span> Em dia (≤ {prazo_man_alerta_inicio} dias)</div>
                    <div class="legend-item"><span class="dot dot-alerta"></span> Alerta ({prazo_man_alerta_inicio}–{PRAZO_MANUTENCAO_DIAS} dias)</div>
                    <div class="legend-item"><span class="dot dot-critico"></span> Vencido (> {PRAZO_MANUTENCAO_DIAS} dias)</div>
                    <div class="legend-item"><span class="dot dot-semdata"></span> Sem data registrada</div>
                </div>
            </div>
            <div>
                <strong style="font-size:0.8rem; text-transform:uppercase; letter-spacing:.04em;">
                    📅 Vida Útil (estimada — {VIDA_UTIL_ANOS} anos)
                </strong>
                <div class="legend-row" style="margin-top:4px;">
                    <div class="legend-item"><span class="dot dot-ok"></span> Dentro do prazo (≤ {vida_alerta_inicio} anos)</div>
                    <div class="legend-item"><span class="dot dot-alerta"></span> Próximo ao fim ({vida_alerta_inicio}–{VIDA_UTIL_ANOS} anos)</div>
                    <div class="legend-item"><span class="dot dot-critico"></span> Vida útil excedida (> {VIDA_UTIL_ANOS} anos)</div>
                    <div class="legend-item"><span class="dot dot-semdata"></span> Sem data de aquisição</div>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── BUSCA ─────────────────────────────────────────────────────────────────
    busca = st.text_input("🔍 Buscar por nome, patrimônio ou local")
    if busca:
        mask = df_view.apply(lambda r: busca.lower() in str(r).lower(), axis=1)
        df_view = df_view[mask]

    df_view = df_view.copy()
    df_view["status_hig"]  = df_view["data_higienizacao"].apply(calcular_status_higienizacao)
    df_view["status_man"]  = df_view["data_manutencao"].apply(calcular_status_manutencao)
    df_view["status_vida"] = df_view["data_aquisicao"].apply(calcular_status_vida_util)

    def fmt_data(val):
        if pd.isna(val) or val == "":
            return "—"
        try:
            return pd.to_datetime(val).strftime("%d/%m/%Y")
        except:
            return str(val)

    st.caption(f"{len(df_view)} itens exibidos")
    st.dataframe(
        df_view[[
            "nome","tipo","local","patrimonio_novo","patrimonio_antigo",
            "numero_serie","data_aquisicao","data_higienizacao",
            "data_manutencao","data_verificacao","suporte_torpedo","necessidades",
            "status_hig","status_man","status_vida",
        ]].assign(
            data_aquisicao    = df_view["data_aquisicao"].apply(fmt_data),
            data_higienizacao = df_view["data_higienizacao"].apply(fmt_data),
            data_manutencao   = df_view["data_manutencao"].apply(fmt_data),
            data_verificacao  = df_view["data_verificacao"].apply(fmt_data),
        ).rename(columns={
            "nome":"Item","tipo":"Tipo","local":"Local",
            "patrimonio_novo":"Patrim. Novo","patrimonio_antigo":"Patrim. Antigo",
            "numero_serie":"N° Série","data_aquisicao":"Aquisição",
            "data_higienizacao":"Última Higienização","data_manutencao":"Última Manutenção",
            "data_verificacao":"Última Verificação","suporte_torpedo":"Torpedo",
            "necessidades":"Necessidades","status_hig":"Status Hig.",
            "status_man":"Status Man.","status_vida":"Vida Útil",
        }),
        use_container_width=True, hide_index=True,
    )

    # ── EDITAR ITEM ───────────────────────────────────────────────────────────
    st.markdown('<p class="section-title">✏️ Editar Item do Inventário</p>', unsafe_allow_html=True)
    st.info("Selecione um item abaixo para editar seus dados cadastrais. As alterações serão salvas diretamente na aba **Consolidado** do Google Sheets.")

    opcoes_edit = (
        df_view["nome"].astype(str) + " | " +
        df_view["tipo"].astype(str) + " | " +
        df_view["local"].astype(str) + " | Pat: " +
        df_view["patrimonio_novo"].fillna("—").astype(str)
    )

    if opcoes_edit.empty:
        st.warning("Nenhum item disponível para edição com o filtro atual.")
    else:
        item_edit_sel = st.selectbox("Selecione o item para editar", opcoes_edit, key="select_edit")
        idx_edit = opcoes_edit[opcoes_edit == item_edit_sel].index[0]
        item_edit = df_view.loc[idx_edit]

        with st.form("form_edicao"):
            st.markdown(f"**Editando:** {item_edit.get('nome','—')} · Patrimônio: `{item_edit.get('patrimonio_novo','—')}`")
            st.markdown("---")

            col1, col2, col3 = st.columns(3)
            with col1:
                novo_nome  = st.text_input("Nome do equipamento", value=str(item_edit.get("nome", "") or ""))
                novo_tipo  = st.selectbox("Tipo", ["Maca", "Cadeira de Rodas"],
                                          index=0 if str(item_edit.get("tipo","")).upper() == "MACA" else 1)
                novo_local = st.text_input("Local / Setor", value=str(item_edit.get("local", "") or ""))
            with col2:
                novo_pat_novo    = st.text_input("Patrimônio Novo",   value=str(item_edit.get("patrimonio_novo","") or ""))
                novo_pat_antigo  = st.text_input("Patrimônio Antigo", value=str(item_edit.get("patrimonio_antigo","") or ""))
                novo_serie       = st.text_input("N° de Série",       value=str(item_edit.get("numero_serie","") or ""))
            with col3:
                novo_torpedo = st.selectbox(
                    "Tem Suporte de Torpedo?",
                    ["Sim", "Não"],
                    index=0 if str(item_edit.get("suporte_torpedo","")).upper() in ["SIM","S","YES","TRUE","1"] else 1,
                )
                novo_necessidades = st.text_area("Necessidades / Pendências",
                                                 value=str(item_edit.get("necessidades","") or ""),
                                                 height=80)

            st.markdown("**Datas**")
            col_d1, col_d2, col_d3, col_d4 = st.columns(4)

            def parse_date_safe(val):
                try:
                    if pd.isna(val) or val == "":
                        return None
                    return pd.to_datetime(val, dayfirst=True).date()
                except:
                    return None

            with col_d1:
                d_aquisicao = st.date_input(
                    "Data de Aquisição",
                    value=parse_date_safe(item_edit.get("data_aquisicao")),
                    format="DD/MM/YYYY",
                )
            with col_d2:
                d_higienizacao = st.date_input(
                    "Última Higienização",
                    value=parse_date_safe(item_edit.get("data_higienizacao")),
                    format="DD/MM/YYYY",
                )
            with col_d3:
                d_manutencao = st.date_input(
                    "Última Manutenção",
                    value=parse_date_safe(item_edit.get("data_manutencao")),
                    format="DD/MM/YYYY",
                )
            with col_d4:
                d_verificacao = st.date_input(
                    "Última Verificação",
                    value=parse_date_safe(item_edit.get("data_verificacao")),
                    format="DD/MM/YYYY",
                )

            submitted = st.form_submit_button("💾 Salvar alterações no Consolidado", type="primary")

        if submitted:
            try:
                updates = {
                    "nome":              novo_nome,
                    "tipo":              novo_tipo,
                    "local":             novo_local,
                    "patrimonio_novo":   novo_pat_novo,
                    "patrimonio_antigo": novo_pat_antigo,
                    "numero_serie":      novo_serie,
                    "suporte_torpedo":   novo_torpedo,
                    "necessidades":      novo_necessidades,
                    "data_aquisicao":    d_aquisicao,
                    "data_higienizacao": d_higienizacao,
                    "data_manutencao":   d_manutencao,
                    "data_verificacao":  d_verificacao,
                }
                atualizar_item(gc, spreadsheet_id, int(item_edit["_row"]), updates)
                st.success(f"✅ Item **{novo_nome}** atualizado com sucesso no Google Sheets!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# PÁGINA: LANÇAR OCORRÊNCIA
# ═══════════════════════════════════════════════════════════════════════════════
elif pagina == "✏️ Lançar Ocorrência":
    st.markdown("# Lançar Ocorrência")
    st.info("Selecione o item e registre a ocorrência. O histórico será salvo e a planilha atualizada.")

    opcoes = df["nome"] + " | " + df["tipo"] + " | " + df["local"] + " | Pat:" + df["patrimonio_novo"].fillna("—")
    item_sel = st.selectbox("Item", opcoes)
    idx = opcoes[opcoes == item_sel].index[0]
    item = df.loc[idx]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Tipo:** {item.get('tipo','—')}")
        st.markdown(f"**Local atual:** {item.get('local','—')}")
    with col2:
        st.markdown(f"**Patrimônio novo:** {item.get('patrimonio_novo','—')}")
        st.markdown(f"**N° Série:** {item.get('numero_serie','—')}")
    with col3:
        st.markdown(f"**Suporte torpedo:** {item.get('suporte_torpedo','—')}")

    st.markdown("---")
    tipo_ocorrencia = st.selectbox("Tipo de ocorrência", [
        "Higienização Terminal",
        "Manutenção Preventiva",
        "Manutenção Corretiva",
        "Troca de Local",
        "Verificação",
        "Troca de Estofado",
        "Instalação Suporte de Soro",
        "Instalação Suporte de O₂",
        "Instalação Suporte de Torpedo",
        "Outra necessidade",
        "Observação geral",
    ])

    data_ocorrencia = st.date_input("Data da ocorrência", value=date.today())
    responsavel     = st.text_input("Responsável")
    observacoes     = st.text_area("Observações / Detalhamento")

    novo_local = None
    if tipo_ocorrencia == "Troca de Local":
        novo_local = st.text_input("Novo local")

    nova_necessidade = None
    if tipo_ocorrencia in ["Troca de Estofado","Instalação Suporte de Soro",
                            "Instalação Suporte de O₂","Instalação Suporte de Torpedo","Outra necessidade"]:
        nova_necessidade   = st.text_input("Descreva a necessidade")
        status_necessidade = st.selectbox("Status", ["Pendente","Em andamento","Concluído"])

    if st.button("💾 Registrar ocorrência", type="primary"):
        if not responsavel:
            st.warning("Informe o responsável.")
        else:
            try:
                registro = {
                    "timestamp":        datetime.now().isoformat(),
                    "item_nome":        item["nome"],
                    "item_patrimonio":  item.get("patrimonio_novo",""),
                    "tipo_ocorrencia":  tipo_ocorrencia,
                    "data_ocorrencia":  data_ocorrencia.isoformat(),
                    "responsavel":      responsavel,
                    "observacoes":      observacoes,
                    "novo_local":       novo_local or "",
                    "necessidade":      nova_necessidade or "",
                    "status_ocorrencia":"Aberta",
                    "data_finalizacao": "",
                }
                salvar_historico(gc, spreadsheet_id, registro)

                updates = {}
                if tipo_ocorrencia == "Higienização Terminal":
                    updates["data_higienizacao"] = data_ocorrencia
                elif tipo_ocorrencia == "Manutenção Preventiva":
                    updates["data_manutencao"] = data_ocorrencia
                elif tipo_ocorrencia == "Verificação":
                    updates["data_verificacao"] = data_ocorrencia
                elif tipo_ocorrencia == "Troca de Local" and novo_local:
                    updates["local"] = novo_local

                if updates:
                    atualizar_item(gc, spreadsheet_id, item["_row"], updates)

                st.success(f"✅ Ocorrência registrada com sucesso em {data_ocorrencia.strftime('%d/%m/%Y')}!")
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# PÁGINA: HISTÓRICO
# ═══════════════════════════════════════════════════════════════════════════════
elif pagina == "📜 Histórico":
    st.markdown("# Histórico de Ocorrências")

    if df_historico.empty:
        st.info("Nenhum histórico registrado ainda. Lance ocorrências para começar a construir o histórico.")
    else:
        if "status_ocorrencia" not in df_historico.columns:
            df_historico["status_ocorrencia"] = "Aberta"
        if "data_finalizacao" not in df_historico.columns:
            df_historico["data_finalizacao"] = ""

        col1, col2, col3 = st.columns(3)
        with col1:
            filtro_tipo_oc = st.selectbox("Filtrar por tipo", ["Todos"] + sorted(df_historico["tipo_ocorrencia"].unique().tolist()))
        with col2:
            filtro_item = st.text_input("Filtrar por item / patrimônio")
        with col3:
            filtro_status = st.selectbox("Filtrar por Status", ["Todos", "Aberta", "Finalizada"])

        dh = df_historico.copy()
        dh["data_ocorrencia_dt"] = pd.to_datetime(dh["data_ocorrencia"], errors="coerce")

        if filtro_tipo_oc != "Todos":
            dh = dh[dh["tipo_ocorrencia"] == filtro_tipo_oc]
        if filtro_item:
            mask = dh.apply(lambda r: filtro_item.lower() in str(r["item_nome"]).lower()
                             or filtro_item.lower() in str(r["item_patrimonio"]).lower(), axis=1)
            dh = dh[mask]
        if filtro_status != "Todos":
            dh = dh[dh["status_ocorrencia"].str.lower() == filtro_status.lower()]

        dh = dh.sort_values("data_ocorrencia_dt", ascending=False)

        dh_show = dh.copy()
        dh_show["data_ocorrencia"] = pd.to_datetime(dh_show["data_ocorrencia"], errors="coerce").dt.strftime("%d/%m/%Y")
        if "timestamp" in dh_show.columns:
            dh_show["timestamp"] = pd.to_datetime(dh_show["timestamp"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")

        st.dataframe(dh_show.rename(columns={
            "timestamp":"Registrado em","item_nome":"Item","item_patrimonio":"Patrimônio",
            "tipo_ocorrencia":"Tipo","data_ocorrencia":"Data","responsavel":"Responsável",
            "observacoes":"Observações","novo_local":"Novo Local","necessidade":"Necessidade",
            "status_ocorrencia":"Status","data_finalizacao":"Data Finalização",
        }), use_container_width=True, hide_index=True)
        st.caption(f"{len(dh)} registros encontrados")

        st.markdown('<p class="section-title">✔️ Finalizar Ocorrência em Aberto</p>', unsafe_allow_html=True)
        ocorrencias_abertas = dh[dh["status_ocorrencia"].str.lower() != "finalizada"]

        if ocorrencias_abertas.empty:
            st.success("Todas as ocorrências filtradas já estão finalizadas! 🎉")
        else:
            opcoes_finalizar = (
                ocorrencias_abertas["item_nome"].astype(str) + " | " +
                ocorrencias_abertas["tipo_ocorrencia"].astype(str) + " | Pat:" +
                ocorrencias_abertas["item_patrimonio"].fillna("—").astype(str) + " | Linha: " +
                ocorrencias_abertas["_row"].astype(str)
            )
            oc_selecionada = st.selectbox("Selecione a ocorrência que deseja encerrar:", opcoes_finalizar)
            idx_oc   = opcoes_finalizar[opcoes_finalizar == oc_selecionada].index[0]
            dados_oc = ocorrencias_abertas.loc[idx_oc]

            col_btn1, _ = st.columns([1, 3])
            with col_btn1:
                data_fechamento = st.date_input("Data de Finalização", value=date.today())

            if st.button("🔒 Finalizar e Atualizar Consolidado", type="primary"):
                try:
                    hoje_iso = data_fechamento.isoformat()
                    atualizar_historico(gc, spreadsheet_id, int(dados_oc["_row"]), {
                        "status_ocorrencia": "Finalizada",
                        "data_finalizacao":  hoje_iso,
                    })

                    equipamento_match = df[df["patrimonio_novo"] == dados_oc["item_patrimonio"]]
                    if not equipamento_match.empty:
                        row_consolidado = equipamento_match.iloc[0]["_row"]
                        tipo_oc         = dados_oc["tipo_ocorrencia"]
                        updates_cons    = {}
                        if tipo_oc == "Higienização Terminal":
                            updates_cons["data_higienizacao"] = data_fechamento
                        elif tipo_oc in ["Manutenção Preventiva","Manutenção Corretiva"]:
                            updates_cons["data_manutencao"] = data_fechamento
                        elif tipo_oc == "Verificação":
                            updates_cons["data_verificacao"] = data_fechamento
                        if updates_cons:
                            atualizar_item(gc, spreadsheet_id, row_consolidado, updates_cons)
                            st.success("✅ Ocorrência finalizada e Consolidado atualizado!")
                        else:
                            st.info("ℹ️ Ocorrência finalizada no histórico.")
                    else:
                        st.warning("⚠️ Ocorrência atualizada no histórico, mas equipamento não encontrado no Consolidado.")

                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao finalizar: {e}")

        if not dh.empty:
            st.markdown('<p class="section-title">Ocorrências por mês</p>', unsafe_allow_html=True)
            dh2 = df_historico.copy()
            dh2["data_ocorrencia"] = pd.to_datetime(dh2["data_ocorrencia"], errors="coerce")
            dh2["mes"] = dh2["data_ocorrencia"].dt.to_period("M").astype(str)
            contagem = dh2.groupby(["mes","tipo_ocorrencia"]).size().reset_index(name="n")
            fig_ev = px.bar(contagem, x="mes", y="n", color="tipo_ocorrencia",
                            color_discrete_sequence=px.colors.qualitative.Set2)
            fig_ev.update_layout(xaxis_title="Mês", yaxis_title="Ocorrências",
                                  legend_title="Tipo", height=300)
            st.plotly_chart(fig_ev, use_container_width=True)
