import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px  
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

# --- CONFIGURAÇÃO E NAVEGAÇÃO ---
st.set_page_config(page_title="Dashboard Financeiro", page_icon="📊", layout="wide")
BASE_URL = "https://dashboardfinanceiro-lpm.streamlit.app/"

params = st.query_params
if "editar_id" in params:
    st.session_state.pg = "Gerenciar Lançamento"
    st.session_state.id_alvo = int(params["editar_id"])
    st.session_state.modo = "editar"
elif "excluir_id" in params:
    st.session_state.pg = "Gerenciar Lançamento"
    st.session_state.id_alvo = int(params["excluir_id"])
    st.session_state.modo = "excluir"
elif "pg" not in st.session_state:
    st.session_state.pg = "Página Inicial"

# --- CONEXÃO GOOGLE SHEETS ---
NOME_DB = "DashboardFinanceiroDB"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

@st.cache_resource
def connect():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Erro Conexão: {e}"); return None

MAPA_MESES = {1:'Janeiro', 2:'Fevereiro', 3:'Março', 4:'Abril', 5:'Maio', 6:'Junho', 7:'Julho', 8:'Agosto', 9:'Setembro', 10:'Outubro', 11:'Novembro', 12:'Dezembro'}

def clean_val(v):
    s = str(v).strip().replace('R$', '').replace(' ', '')
    if not s: return np.nan
    l_c, l_d = s.rfind(','), s.rfind('.')
    if l_c > l_d: s = s.replace('.', '').replace(',', '.')
    elif l_d > l_c: s = s.replace(',', '')
    return pd.to_numeric(s, errors='coerce')

@st.cache_data(ttl=60)
def load_data():
    c = connect()
    if not c: return pd.DataFrame()
    try:
        ws = c.open(NOME_DB).sheet1
        data = ws.get_all_values()
        if len(data) < 2: return pd.DataFrame()
        df = pd.DataFrame(data[1:], columns=[h.strip() for h in data[0]])
        for col in ['ID', 'Ano', 'Valor']:
            if col in df.columns:
                df[col] = df[col].apply(clean_val) if col == 'Valor' else pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=['ID'], inplace=True)
        df['ID'] = df['ID'].astype(int)
        df['Mês'] = pd.Categorical(df['Mês'], categories=list(MAPA_MESES.values()), ordered=True)
        return df
    except: return pd.DataFrame()

def save_data(df):
    c = connect()
    if not c: return False
    try:
        ws = c.open(NOME_DB).sheet1
        df_s = df.copy()
        if 'Valor' in df_s.columns:
            df_s['Valor'] = df_s['Valor'].apply(lambda x: f"{x:.2f}".replace('.', ',') if pd.notna(x) else '')
        ws.clear()
        set_with_dataframe(ws, df_s.astype(str), include_index=False, resize=True)
        st.cache_data.clear(); return True
    except: return False

@st.cache_data(ttl=60)
def get_cats():
    try:
        ws = connect().open(NOME_DB).worksheet("Categorias")
        return sorted([v for v in ws.col_values(1)[1:] if v])
    except: return ["Entrada", "Saúde", "Transporte", "Moradia"]

# --- PÁGINAS ---
def pg_home():
    st.title("🏠 Página Inicial")
    df = load_data()
    if df.empty: return
    df['V_Fin'] = np.where(df['Tipo'] == 'Despesa', -df['Valor'], df['Valor'])
    df_m = df[(df['Ano'] == datetime.now().year) & (df['Mês'] == MAPA_MESES[datetime.now().month])]
    if not df_m.empty:
        r, d = df_m[df_m['V_Fin']>0]['V_Fin'].sum(), df_m[df_m['V_Fin']<0]['V_Fin'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("🟢 Receitas", f"R$ {r:,.2f}"); c2.metric("🔴 Despesas", f"R$ {d:,.2f}"); c3.metric("💰 Saldo", f"R$ {r+d:,.2f}")
    st.markdown("---")
    res = df_m[df_m['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum().reset_index()
    if not res.empty:
        fig = px.pie(res, values='Valor', names='Categoria', hole=0.4, title="Despesas do Mês", color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig, use_container_width=True)

def pg_add():
    st.title("✍️ Adicionar Novo Lançamento")
    df = load_data(); cats = get_cats()
    prox_id = int(df['ID'].max() + 1) if not df.empty else 1
    with st.form("f_add"):
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data", datetime.now()); tp = c2.selectbox("Tipo", ['Despesa', 'Receita', 'Sobra']); vl = c3.number_input("Valor", 0.01)
        ds, ct = st.text_input("Descrição"), st.selectbox("Categoria", cats)
        if st.form_submit_button("Adicionar"):
            novo = pd.DataFrame([{'ID':prox_id, 'Data':dt.strftime('%d/%m/%Y'), 'Tipo':tp, 'Descrição':ds, 'Valor':vl, 'Categoria':ct, 'Mês':MAPA_MESES[dt.month], 'Ano':dt.year}])
            if save_data(pd.concat([df, novo], ignore_index=True)): st.success("Salvo!"); st.rerun()

def pg_manage():
    st.title("🛠️ Gerenciar Lançamento")
    df = load_data()
    id_v = st.session_state.get('id_alvo', 1); modo = st.session_state.get('modo', 'editar')
    idx = st.number_input("Digite o ID", min_value=1, value=int(id_v))
    res = df[df['ID'] == idx]
    if not res.empty:
        st.dataframe(res, hide_index=True)
        if modo == "excluir":
            st.warning(f"⚠️ Confirmar exclusão do ID {idx}?")
            if st.button("🔴 CONFIRMAR EXCLUSÃO"):
                if save_data(df[df['ID'] != idx]): 
                    st.query_params.clear(); st.session_state.pg="Página Inicial"; st.rerun()
        elif st.button("🗑️ Excluir Registro"):
            if save_data(df[df['ID'] != idx]): st.success("Excluído!"); st.rerun()
    else: st.error("ID não encontrado.")

def pg_relat():
    st.title("📊 Gerador de Relatório Financeiro")
    c1, c2 = st.columns(2)
    ano = c1.number_input("Ano", 2024, 2030, datetime.now().year)
    mes = c2.selectbox("Mês", list(MAPA_MESES.values()), index=datetime.now().month-1)
    if st.button("Gerar Relatório"):
        df = load_data()
        df_r = df[(df['Ano'] == ano) & (df['Mês'] == mes)].copy()
        if not df_r.empty:
            df_r['📝'] = df_r['ID'].apply(lambda x: f"{BASE_URL}?editar_id={x}")
            df_r['❌'] = df_r['ID'].apply(lambda x: f"{BASE_URL}?excluir_id={x}")
            cols = ['📝', '❌', 'ID', 'Data', 'Descrição', 'Categoria', 'Valor', 'Observações']
            st.dataframe(df_r[cols], hide_index=True, column_config={
                "📝": st.column_config.LinkColumn("Ed", display_text="📝"),
                "❌": st.column_config.LinkColumn("Ex", display_text="❌"),
                "ID": st.column_config.NumberColumn(format="%d")
            })

def pg_cats():
    st.title("⚙️ Configurações de Categoria")
    cats = get_cats(); col1, col2 = st.columns(2)
    with col1:
        nova = st.text_input("Nova Categoria")
        if st.button("Adicionar"):
            connect().open(NOME_DB).worksheet("Categorias").append_row([nova])
            st.cache_data.clear(); st.rerun()
    with col2:
        rem = st.selectbox("Excluir", ["Selecione"] + cats)
        sub = st.selectbox("Substituir por", [c for c in cats if c != rem])
        if st.button("Substituir e Remover"):
            df = load_data()
            df['Categoria'] = df['Categoria'].replace(rem, sub)
            if save_data(df):
                ws = connect().open(NOME_DB).worksheet("Categorias")
                cel = ws.find(rem)
                if cel: ws.delete_rows(cel.row)
                st.rerun()

# --- MENU PRINCIPAL ---
paginas = {"Página Inicial": pg_home, "Adicionar Lançamento": pg_add, "Gerenciar Lançamento": pg_manage, "Relatório Mensal": pg_relat, "Configurações de Categoria": pg_cats}
idx_m = list(paginas.keys()).index(st.session_state.pg)
st.sidebar.title("🏛️ Menu Principal")
escolha = st.sidebar.radio("Navegue pelas páginas", list(paginas.keys()), index=idx_m)

if escolha != st.session_state.pg:
    st.session_state.pg = escolha
    st.query_params.clear()
    if 'id_alvo' in st.session_state: del st.session_state.id_alvo
    st.rerun()

paginas[escolha]()
