import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px  
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Dashboard Financeiro", page_icon="📊", layout="wide")
NOME_P = "DashboardFinanceiroDB"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

@st.cache_resource
def connect():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
        return gspread.authorize(creds)
    except: return None

MAPA_M = {1:'Janeiro',2:'Fevereiro',3:'Março',4:'Abril',5:'Maio',6:'Junho',7:'Julho',8:'Agosto',9:'Setembro',10:'Outubro',11:'Novembro',12:'Dezembro'}
MESES_O = list(MAPA_M.values())
MEIOS_P = ['Vale Alimentação','Débito Nubank','Débito Santander','Crédito Nubank','Crédito Santander','Boleto','Crédito BTG','Dinheiro','Pix','Transf. BTG']
CLASS_P = ['Essencial','Não Essencial','Extra']

def clean_v(v):
    s = str(v).strip().replace('R$', '').replace(' ', '')
    if not s: return np.nan
    lc, ld = s.rfind(','), s.rfind('.')
    if lc > ld: s = s.replace('.', '').replace(',', '.')
    elif ld > lc: s = s.replace(',', '')
    return pd.to_numeric(s, errors='coerce')

@st.cache_data(ttl=60)
def load_data():
    c = connect()
    if not c: return pd.DataFrame()
    try:
        ws = c.open(NOME_P).sheet1
        data = ws.get_all_values()
        if len(data) < 2: return pd.DataFrame()
        df = pd.DataFrame(data[1:], columns=[h.strip() for h in data[0]])
        for col in ['ID', 'Ano', 'Valor']:
            if col in df.columns:
                df[col] = df[col].apply(clean_v) if col == 'Valor' else pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=['ID'], inplace=True); df['ID'] = df['ID'].astype(int)
        df['Mês'] = pd.Categorical(df['Mês'], categories=MESES_O, ordered=True)
        return df
    except: return pd.DataFrame()

def save_data(df):
    c = connect()
    try:
        ws = c.open(NOME_P).sheet1
        df_s = df.copy()
        if 'Valor' in df_s.columns: df_s['Valor'] = df_s['Valor'].apply(lambda x: f"{x:.2f}".replace('.', ',') if pd.notna(x) else '')
        ws.clear(); set_with_dataframe(ws, df_s.astype(str), include_index=False, resize=True)
        st.cache_data.clear(); return True
    except: return False

@st.cache_data(ttl=60)
def get_cats():
    try: return sorted([v for v in connect().open(NOME_P).worksheet("Categorias").col_values(1)[1:] if v])
    except: return ["Entrada", "Saúde", "Transporte", "Moradia"]

# --- PÁGINAS ---
def pg_home():
    st.title("🏠 Página Inicial")
    df = load_data()
    if df.empty: return
    df['VF'] = np.where(df['Tipo'] == 'Despesa', -df['Valor'], df['Valor'])
    m_n = MAPA_M[datetime.now().month]
    df_m = df[(df['Ano'] == datetime.now().year) & (df['Mês'] == m_n)]
    if not df_m.empty:
        r, d = df_m[df_m['VF']>0]['VF'].sum(), df_m[df_m['VF']<0]['VF'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("🟢 Receitas", f"R$ {r:,.2f}"); c2.metric("🔴 Despesas", f"R$ {d:,.2f}"); c3.metric("💰 Saldo", f"R$ {r+d:,.2f}")
    st.markdown("---"); st.subheader("📊 Distribuição de Despesas")
    res = df_m[df_m['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum().reset_index()
    if not res.empty:
        st.plotly_chart(px.pie(res, values='Valor', names='Categoria', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel), use_container_width=True)
        st.markdown("### 🔍 Detalhamento por Categoria")
        sel = st.selectbox("Escolha uma categoria:", ["Selecione..."] + list(res['Categoria'].unique()))
        if sel != "Selecione...":
            det = df_m[(df_m['Categoria'] == sel) & (df_m['Tipo'] == 'Despesa')]
            st.dataframe(det[['Data', 'Descrição', 'Forma de Pagamento', 'Valor', 'Observações']], hide_index=True, use_container_width=True)

def pg_add():
    st.title("✍️ Adicionar Lançamento")
    df = load_data(); cats = get_cats()
    prox_id = int(df['ID'].max() + 1) if not df.empty else 1
    with st.form("add_f"):
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data", datetime.now()); tp = c2.selectbox("Tipo", ['Despesa','Receita','Sobra']); vl = c3.number_input("Valor Total", 0.01)
        ds, ct = st.text_input("Descrição"), st.selectbox("Categoria", cats)
        cl, mt = c1.selectbox("Classificação", CLASS_P), c2.selectbox("Método", MEIOS_P)
        fr, pg = c1.selectbox("Forma", ['À Vista','Parcelado']), c2.selectbox("Pago?", ['Sim','Não'])
        ob, n_p = st.text_area("Obs"), st.number_input("Nº Parcelas", 1, 60, 1)
        m_c, a_c = st.number_input("Mês Contábil", 1, 12, dt.month), st.number_input("Ano Contábil", 2024, 2030, dt.year)
        if st.form_submit_button("Adicionar"):
            novos = []; p_txt = 'OK' if pg == 'Sim' else 'NOK'
            if fr == 'À Vista' or tp != 'Despesa':
                novos.append({'ID':prox_id,'Data':dt.strftime('%d/%m/%Y'),'Tipo':tp,'Descrição':ds,'Valor':vl,'Categoria':ct,'Classificação':cl,'Pagamento':fr,'Forma de Pagamento':mt,'Parcelas':'N/A','Pagamento Realizado':p_txt,'Observações':ob,'Mês':MAPA_M[m_c],'Ano':a_c})
            else:
                for i in range(n_p):
                    m, a = m_c+i, a_c
                    while m > 12: m-=12; a+=1
                    novos.append({'ID':prox_id+i,'Data':dt.strftime('%d/%m/%Y'),'Tipo':tp,'Descrição':f"{ds} ({i+1}/{n_p})",'Valor':vl/n_p,'Categoria':ct,'Classificação':cl,'Pagamento':fr,'Forma de Pagamento':mt,'Parcelas':f"{i+1:02d} de {n_p:02d}",'Pagamento Realizado':p_txt,'Observações':ob,'Mês':MAPA_M[m],'Ano':a})
            if save_data(pd.concat([df, pd.DataFrame(novos)], ignore_index=True)): st.success("Salvo!"); st.rerun()

def pg_manage():
    st.title("🛠️ Gerenciar Lançamento")
    df = load_data()
    c1, c2 = st.columns([3, 1])
    id_in = c1.number_input("ID", min_value=1, step=1)
    if c2.button("🔍 Buscar"): st.session_state.id_g = id_in
    if 'id_g' in st.session_state:
        idx = st.session_state.id_g
        if idx in df['ID'].values:
            r_idx = df.index[df['ID'] == idx].tolist()[0]
            dados = df.loc[r_idx]
            st.success(f"ID {idx} encontrado!"); st.dataframe(df.loc[[r_idx]], hide_index=True)
            ce, cd = st.columns(2)
            with ce:
                with st.expander("📝 Editar"):
                    with st.form("ed"):
                        n_dt = st.text_input("Data", dados['Data']); n_ds = st.text_input("Desc", dados['Descrição'])
                        n_vl = st.number_input("Valor", value=float(dados['Valor']))
                        n_ct = st.selectbox("Cat", get_cats()); n_cl = st.selectbox("Class", CLASS_P)
                        if st.form_submit_button("Gravar"):
                            df.at[r_idx,'Data'], df.at[r_idx,'Descrição'], df.at[r_idx,'Valor'], df.at[r_idx,'Categoria'], df.at[r_idx,'Classificação'] = n_dt, n_ds, n_vl, n_ct, n_cl
                            if save_data(df): st.toast("Ok!"); st.rerun()
            with cd:
                with st.popover("🗑️ Excluir"):
                    if st.button("Confirmar Exclusão", type="primary"):
                        df = df.drop(r_idx).reset_index(drop=True)
                        df['ID'] = range(1, len(df)+1)
                        if save_data(df): st.success("Excluído!"); del st.session_state.id_g; st.rerun()
        else: st.error("Não encontrado.")

def pg_relat():
    st.title("📊 Relatório Financeiro")
    c1, c2 = st.columns(2)
    ano, mes = c1.number_input("Ano", 2024, 2030, 2026), c2.selectbox("Mês", MESES_O, index=datetime.now().month-1)
    if st.button("Gerar"):
        df = load_data()
        df_r = df[(df['Ano'] == ano) & (df['Mês'] == mes)]
        if not df_r.empty: st.dataframe(df_r[['ID','Data','Descrição','Categoria','Forma de Pagamento','Parcelas','Valor','Observações']], hide_index=True)
        else: st.warning("Sem dados.")

def pg_fats():
    st.title("💳 Faturas de Cartão")
    cart = st.selectbox("Cartão", ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG'])
    if st.button("Ver Fatura"):
        df = load_data()
        df_f = df[df['Forma de Pagamento'] == cart]
        st.metric("Total", f"R$ {df_f['Valor'].sum():,.2f}")
        st.dataframe(df_f[['ID','Data','Descrição','Categoria','Parcelas','Valor','Observações']], hide_index=True)

def pg_cats():
    st.title("⚙️ Categorias")
    cats = get_cats(); c1, c2, c3 = st.columns(3)
    with c1:
        nova = st.text_input("Nova")
        if st.button("Add"): connect().open(N_P).worksheet("Categorias").append_row([nova]); st.rerun()
    with c2:
        ed, nv = st.selectbox("Editar", cats), st.text_input("Novo nome")
        if st.button("Atualizar"):
            df = load_data(); df['Categoria'] = df['Categoria'].replace(ed, nv)
            if save_data(df):
                ws = connect().open(N_P).worksheet("Categorias")
                cel = ws.find(ed)
                if cel: ws.update_cell(cel.row, 1, nv)
                st.rerun()
    with c3:
        rm, sb = st.selectbox("Excluir", cats), st.selectbox("Subst. por", cats)
        if st.button("Remover"):
            df = load_data(); df['Categoria'] = df['Categoria'].replace(rm, sb)
            if save_data(df):
                ws = connect().open(N_P).worksheet("Categorias")
                cel = ws.find(rm)
                if cel: ws.delete_rows(cel.row)
                st.rerun()

def pg_grafs():
    st.title("🎨 Gráficos")
    df = load_data()
    if not df.empty:
        res = df[df['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum().reset_index()
        st.plotly_chart(px.bar(res, x='Categoria', y='Valor', color='Categoria'), use_container_width=True)

# --- MENU ---
st.sidebar.title("🏛️ Menu Principal")
paginas = {"Página Inicial": pg_home, "Adicionar Lançamento": pg_add, "Gerenciar Lançamento": pg_manage, "Relatório Mensal": pg_relat, "Ver Faturas de Cartão": pg_fats, "Configurações de Categoria": pg_cats, "Gráficos Analíticos": pg_grafs}
escolha = st.sidebar.radio("Navegue:", list(paginas.keys()))
paginas[escolha]()
