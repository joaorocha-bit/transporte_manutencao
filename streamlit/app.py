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
    PRAZO_HIGIENIZACAO_DIAS,
    PRAZO_MANUTENCAO_DIAS,
    VIDA_UTIL_ANOS,
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
    .metric-card.verde  { border-left-color: #16A34A; }
    .metric-card.amarelo{ border-left-color: #D97706; }
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

    # ── KPIs ─────────────────────────────────────────────────────────────────
    total_macas = len(df[df["tipo"].str.upper() == "MACA"])
    total_cadeiras = len(df[df["tipo"].str.upper() == "CADEIRA DE RODAS"])

    df_view["status_hig"] = df_view["data_higienizacao"].apply(calcular_status_higienizacao)
    df_view["status_man"] = df_view["data_manutencao"].apply(calcular_status_manutencao)
    df_view["status_vida"] = df_view["data_aquisicao"].apply(calcular_status_vida_util)

    hig_ok = (df_view["status_hig"] == "ok").sum()
    hig_alerta = (df_view["status_hig"] == "alerta").sum()
    hig_critico = (df_view["status_hig"] == "critico").sum()

    man_ok = (df_view["status_man"] == "ok").sum()
    man_alerta = (df_view["status_man"] == "alerta").sum()
    man_critico = (df_view["status_man"] == "critico").sum()

    # ── CÁLCULO DOS CONTADORES DE OCORRÊNCIAS ──
    # Filtra o histórico dinamicamente baseado no equipamento da View atual
    if tipo_filtro != "Todos":
        df_hist_view = df_historico[df_historico["item_patrimonio"].isin(df_view["patrimonio_novo"])].copy()
    else:
        df_hist_view = df_historico.copy()

    # Garante que a coluna exista para não gerar erros no primeiro carregamento
    if "status_ocorrencia" not in df_hist_view.columns:
        df_hist_view["status_ocorrencia"] = "Aberta"

    # Conta abertas (tudo que não for "finalizada" ou que estiver vazio) e finalizadas
    oc_abertas = (df_hist_view["status_ocorrencia"].str.lower() != "finalizada").sum()
    oc_finalizadas = (df_hist_view["status_ocorrencia"].str.lower() == "finalizada").sum()


    # ── RENDERIZAÇÃO DOS CARDS ──
    # Linha 1: Equipamentos e Pendências Gerais
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

    # Linha 2: Status das Ocorrências (Novos Contadores)
    col_oc1, col_oc2 = st.columns(2)
    with col_oc1:
        # Fica vermelho se houver alguma pendência aberta, senão fica verde
        cor_oc_aberta = "vermelho" if oc_abertas > 0 else "verde"
        st.markdown(f"""<div class="metric-card {cor_oc_aberta}">
            <div class="metric-value">{oc_abertas}</div>
            <div class="metric-label">📋 Ocorrências em Aberto</div></div>""", unsafe_allow_html=True)
    with col_oc2:
        st.markdown(f"""<div class="metric-card verde">
            <div class="metric-value">{oc_finalizadas}</div>
            <div class="metric-label">✅ Ocorrências Finalizadas</div></div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── GRÁFICOS ──────────────────────────────────────────────────────────────
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

    # ── ITENS CRÍTICOS ────────────────────────────────────────────────────────
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
        criticos["Manutenção"] = criticos["status_man"].apply(badge)
        criticos = criticos.rename(columns={"nome":"Item","tipo":"Tipo","local":"Local","patrimonio_novo":"Patrimônio"})
        st.write(criticos[["Item","Tipo","Local","Patrimônio","Higienização","Manutenção"]].to_html(
            escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)

    # ── NECESSIDADES DE MANUTENÇÃO ────────────────────────────────────────────
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

    busca = st.text_input("🔍 Buscar por nome, patrimônio ou local")
    if busca:
        mask = df_view.apply(lambda r: busca.lower() in str(r).lower(), axis=1)
        df_view = df_view[mask]

    df_view["status_hig"] = df_view["data_higienizacao"].apply(calcular_status_higienizacao)
    df_view["status_man"] = df_view["data_manutencao"].apply(calcular_status_manutencao)
    df_view["status_vida"] = df_view["data_aquisicao"].apply(calcular_status_vida_util)

    def fmt_data(val):
        if pd.isna(val) or val == "":
            return "—"
        try:
            return pd.to_datetime(val).strftime("%d/%m/%Y")
        except:
            return str(val)

    df_show = df_view[[
        "nome","tipo","local","patrimonio_novo","patrimonio_antigo",
        "numero_serie","data_aquisicao","data_higienizacao",
        "data_manutencao","data_verificacao","suporte_torpedo","necessidades",
        "status_hig","status_man","status_vida"
    ]].copy()

    for col in ["data_aquisicao","data_higienizacao","data_manutencao","data_verificacao"]:
        df_show[col] = df_show[col].apply(fmt_data)

    def colorir(row):
        cores = []
        for col in row.index:
            if col == "status_hig":
                c = {"ok":"#DCFCE7","alerta":"#FEF9C3","critico":"#FEE2E2","sem_data":"#F8FAFC"}.get(row[col],"")
            elif col == "status_man":
                c = {"ok":"#DCFCE7","alerta":"#FEF9C3","critico":"#FEE2E2","sem_data":"#F8FAFC"}.get(row[col],"")
            elif col == "status_vida":
                c = {"ok":"#DCFCE7","alerta":"#FEF9C3","critico":"#FEE2E2","sem_data":"#F8FAFC"}.get(row[col],"")
            else:
                c = ""
            cores.append(f"background-color: {c}" if c else "")
        return cores

    st.dataframe(
        df_show.rename(columns={
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
    st.caption(f"{len(df_view)} itens exibidos")


# ═══════════════════════════════════════════════════════════════════════════════
# PÁGINA: LANÇAR OCORRÊNCIA
# ═══════════════════════════════════════════════════════════════════════════════
elif pagina == "✏️ Lançar Ocorrência":
    st.markdown("# Lançar Ocorrência")
    st.info("Selecione o item e registre a ocorrência. O histórico será salvo e a planilha atualizada.")

    # Seleção do item
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
    responsavel = st.text_input("Responsável")
    observacoes = st.text_area("Observações / Detalhamento")

    novo_local = None
    if tipo_ocorrencia == "Troca de Local":
        novo_local = st.text_input("Novo local")

    nova_necessidade = None
    if tipo_ocorrencia in ["Troca de Estofado","Instalação Suporte de Soro",
                            "Instalação Suporte de O₂","Instalação Suporte de Torpedo","Outra necessidade"]:
        nova_necessidade = st.text_input("Descreva a necessidade")
        status_necessidade = st.selectbox("Status", ["Pendente","Em andamento","Concluído"])

    if st.button("💾 Registrar ocorrência", type="primary"):
        if not responsavel:
            st.warning("Informe o responsável.")
        else:
            try:
                registro = {
                    "timestamp": datetime.now().isoformat(),
                    "item_nome": item["nome"],
                    "item_patrimonio": item.get("patrimonio_novo",""),
                    "tipo_ocorrencia": tipo_ocorrencia,
                    "data_ocorrencia": data_ocorrencia.isoformat(),
                    "responsavel": responsavel,
                    "observacoes": observacoes,
                    "novo_local": novo_local or "",
                    "necessidade": nova_necessidade or "",
                }

                # Salva no histórico (aba "historico")
                salvar_historico(gc, spreadsheet_id, registro)

                # Atualiza campos na aba principal
                from utils import atualizar_item
                updates = {}
                if tipo_ocorrencia == "Higienização Terminal":
                    updates["data_higienizacao"] = data_ocorrencia.isoformat()
                elif tipo_ocorrencia in ["Manutenção Preventiva"]:
                    updates["data_manutencao"] = data_ocorrencia.isoformat()
                elif tipo_ocorrencia == "Verificação":
                    updates["data_verificacao"] = data_ocorrencia.isoformat()
                elif tipo_ocorrencia == "Troca de Local" and novo_local:
                    updates["local"] = novo_local

                if updates:
                    atualizar_item(gc, spreadsheet_id, item["_row"], updates)

                st.success(f"✅ Ocorrência registrada com sucesso em {data_ocorrencia.strftime('%d/%m/%Y')}!")
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# PÁGINA: HISTÓRICO (MODIFICADA)
# ═══════════════════════════════════════════════════════════════════════════════
elif pagina == "📜 Histórico":
    st.markdown("# Histórico de Ocorrências")

    if df_historico.empty:
        st.info("Nenhum histórico registrado ainda. Lance ocorrências para começar a construir o histórico.")
    else:
        # Garante que colunas de controle existam no DataFrame para evitar quebras
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

        # Aplicação dos filtros
        if filtro_tipo_oc != "Todos":
            dh = dh[dh["tipo_ocorrencia"] == filtro_tipo_oc]
        if filtro_item:
            mask = dh.apply(lambda r: filtro_item.lower() in str(r["item_nome"]).lower() or filtro_item.lower() in str(r["item_patrimonio"]).lower(), axis=1)
            dh = dh[mask]
        if filtro_status != "Todos":
            dh = dh[dh["status_ocorrencia"].str.lower() == filtro_status.lower()]

        dh = dh.sort_values("data_ocorrencia_dt", ascending=False)
        
        # Formatação visual para exibição
        dh_show = dh.copy()
        dh_show["data_ocorrencia"] = pd.to_datetime(dh_show["data_ocorrencia"], errors="coerce").dt.strftime("%d/%m/%Y")
        if "timestamp" in dh_show.columns:
            dh_show["timestamp"] = pd.to_datetime(dh_show["timestamp"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")

        # Exibição da tabela de histórico
        st.dataframe(dh_show.rename(columns={
            "timestamp": "Registrado em", "item_nome": "Item", "item_patrimonio": "Patrimônio",
            "tipo_ocorrencia": "Tipo", "data_ocorrencia": "Data", "responsavel": "Responsável",
            "observacoes": "Observações", "novo_local": "Novo Local", "necessidade": "Necessidade",
            "status_ocorrencia": "Status", "data_finalizacao": "Data Finalização"
        }), use_container_width=True, hide_index=True)
        st.caption(f"{len(dh)} registros encontrados")

        # ── SEÇÃO PARA FINALIZAR OCORRÊNCIA ──────────────────────────────────
        st.markdown('<p class="section-title">✔️ Finalizar Ocorrência em Aberto</p>', unsafe_allow_html=True)
        
        # Filtra apenas as ocorrências que estão abertas para seleção
        ocorrencias_abertas = dh[dh["status_ocorrencia"].str.lower() != "finalizada"]
        
        if ocorrencias_abertas.empty:
            st.success("Todas as ocorrências filtradas já estão finalizadas! 🎉")
        else:
            # Monta uma lista de opções legível convertendo tudo para TEXTO (.astype(str)) para evitar erros
            opcoes_finalizar = (
                ocorrencias_abertas["item_nome"].astype(str) + " | " + 
                ocorrencias_abertas["tipo_ocorrencia"].astype(str) + " | Pat:" + 
                ocorrencias_abertas["item_patrimonio"].fillna("—").astype(str) + " | Linha: " + 
                ocorrencias_abertas["_row"].astype(str)
            )
            
            oc_selecionada = st.selectbox("Selecione a ocorrência que deseja encerrar:", opcoes_finalizar)
            
            # Recupera o índice real do item selecionado
            idx_oc = opcoes_finalizar[opcoes_finalizar == oc_selecionada].index[0]
            dados_oc = ocorrencias_abertas.loc[idx_oc]
            
            col_btn1, col_btn2 = st.columns([1, 3])
            with col_btn1:
                data_fechamento = st.date_input("Data de Finalização", value=date.today())
            
            if st.button("🔒 Finalizar e Atualizar Consolidado", type="primary"):
                try:
                    hoje_iso = data_fechamento.isoformat()
                    
                    # 1. Atualiza a aba de Histórico
                    from utils import atualizar_historico
                    updates_hist = {
                        "status_ocorrencia": "Finalizada",
                        "data_finalizacao": hoje_iso
                    }
                    atualizar_historico(gc, spreadsheet_id, int(dados_oc["_row"]), updates_hist)
                    
                    # 2. Atualiza a aba principal (Consolidado) baseando-se no patrimônio do item
                    from utils import atualizar_item
                    
                    # Encontra a linha correspondente do equipamento no DataFrame principal (`df`)
                    equipamento_match = df[df["patrimonio_novo"] == dados_oc["item_patrimonio"]]
                    
                    if not equipamento_match.empty:
                        row_consolidado = equipamento_match.iloc[0]["_row"]
                        tipo_oc = dados_oc["tipo_ocorrencia"]
                        
                        updates_consolidado = {}
                        # Altera a respectiva data dependendo do que foi finalizado
                        if tipo_oc == "Higienização Terminal":
                            updates_consolidado["data_higienizacao"] = hoje_iso
                        elif tipo_oc in ["Manutenção Preventiva", "Manutenção Corretiva"]:
                            updates_consolidado["data_manutencao"] = hoje_iso
                        elif tipo_oc == "Verificação":
                            updates_consolidado["data_verificacao"] = hoje_iso
                        
                        # Se houver campo atualizável mapeado, envia para o Sheets
                        if updates_consolidado:
                            atualizar_item(gc, spreadsheet_id, row_consolidado, updates_consolidado)
                            st.success("✅ Ocorrência finalizada e aba Consolidado atualizada com sucesso!")
                        else:
                            st.info("ℹ️ Ocorrência finalizada no histórico. (Nenhum campo de data correspondente para o Consolidado).")
                    else:
                        st.warning("⚠️ Ocorrência atualizada no histórico, mas o equipamento correspondente não foi achado no Consolidado pelo Patrimônio.")
                    
                    # Limpa o cache e recarrega a página para atualizar os dados visuais
                    st.cache_data.clear()
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Erro ao finalizar ocorrência: {e}")

        # ── MINI GRÁFICO DE EVOLUÇÃO ──────────────────────────────────────────
        if not dh.empty:
            st.markdown('<p class="section-title">Ocorrências por mês</p>', unsafe_allow_html=True)
            dh2 = df_historico.copy()
            dh2["data_ocorrencia"] = pd.to_datetime(dh2["data_ocorrencia"], errors="coerce")
            dh2["mes"] = dh2["data_ocorrencia"].dt.to_period("M").astype(str)
            contagem = dh2.groupby(["mes", "tipo_ocorrencia"]).size().reset_index(name="n")
            fig_ev = px.bar(contagem, x="mes", y="n", color="tipo_ocorrencia", color_discrete_sequence=px.colors.qualitative.Set2)
            fig_ev.update_layout(xaxis_title="Mês", yaxis_title="Ocorrências", legend_title="Tipo", height=300)
            st.plotly_chart(fig_ev, use_container_width=True)
