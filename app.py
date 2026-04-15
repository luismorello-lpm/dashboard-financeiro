import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Meu Dashboard Financeiro", page_icon="📊", layout="wide")

# --- CONFIGURAÇÃO DA CONEXÃO ---
NOME_DA_PLANILHA = "DashboardFinanceiroDB"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

@st.cache_resource
def connect_to_gsheet():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
        return gspread.authorize(creds)
    except: return None

# --- CONSTANTES E AUXILIARES ---
MAPA_MESES = {1:'Janeiro', 2:'Fevereiro', 3:'Março', 4:'Abril', 5:'Maio', 6:'Junho', 7:'Julho', 8:'Agosto', 9:'Setembro', 10:'Outubro', 11:'Novembro', 12:'Dezembro'}
MESES_ORDENADOS = list(MAPA_MESES.values())
MEIOS_PAGAMENTO_PADRAO = ['Vale Alimentação', 'Débito Nubank', 'Débito Santander', 'Crédito Nubank', 'Crédito Santander', 'Boleto', 'Crédito BTG', 'Dinheiro', 'Pix', 'Transf. BTG']
CLASSIFICACOES_PADRAO = ['Essencial', 'Não Essencial', 'Extra']

def clean_valor(valor_str):
    s = str(valor_str).strip().replace('R$', '').replace(' ', '')
    if not s: return np.nan
    last_comma, last_dot = s.rfind(','), s.rfind('.')
    if last_comma > last_dot: s = s.replace('.', '').replace(',', '.')
    elif last_dot > last_comma: s = s.replace(',', '')
    return pd.to_numeric(s, errors='coerce')

@st.cache_data(ttl=60)
def carregar_dados():
    client = connect_to_gsheet()
    if client:
        try:
            ws = client.open(NOME_DA_PLANILHA).sheet1
            data = ws.get_all_values()
            if len(data) < 2: return pd.DataFrame()
            df = pd.DataFrame(data[1:], columns=[h.strip() for h in data[0]])
            for col in ['ID', 'Ano', 'Valor']:
                if col in df.columns:
                    df[col] = df[col].apply(clean_valor) if col == 'Valor' else pd.to_numeric(df[col], errors='coerce')
            df.dropna(subset=['ID'], inplace=True)
            df['ID'] = df['ID'].astype(int)
            df['Mês'] = pd.Categorical(df['Mês'], categories=MESES_ORDENADOS, ordered=True)
            return df
        except: return pd.DataFrame()
    return pd.DataFrame()

def salvar_dados(df):
    client = connect_to_gsheet()
    if client:
        try:
            ws = client.open(NOME_DA_PLANILHA).sheet1
            df_para_salvar = df.copy()
            if 'Valor' in df_para_salvar.columns:
                 df_para_salvar['Valor'] = df_para_salvar['Valor'].apply(lambda x: f"{x:.2f}".replace('.', ',') if pd.notna(x) else '')
            ws.clear()
            set_with_dataframe(ws, df_para_salvar.astype(str), include_index=False, resize=True)
            st.cache_data.clear()
            return True
        except: return False
    return False

@st.cache_data(ttl=60)
def carregar_categorias():
    try:
        ws = connect_to_gsheet().open(NOME_DA_PLANILHA).worksheet("Categorias")
        return sorted([c for c in ws.col_values(1)[1:] if c])
    except: return ["Geral"]

# --- PÁGINAS ---

def pagina_inicial():
    st.title("🏠 Página Inicial")
    df = carregar_dados()
    if df.empty: return
    df['Valor Fin.'] = np.where(df['Tipo'] == 'Despesa', -df['Valor'], df['Valor'])
    df_mes = df[(df['Ano'] == datetime.now().year) & (df['Mês'] == MAPA_MESES[datetime.now().month])]
    if not df_mes.empty:
        r, d = df_mes[df_mes['Valor Fin.'] > 0]['Valor Fin.'].sum(), df_mes[df_mes['Valor Fin.'] < 0]['Valor Fin.'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("🟢 Receitas", f"R$ {r:,.2f}"); c2.metric("🔴 Despesas", f"R$ {d:,.2f}"); c3.metric("💰 Saldo", f"R$ {r+d:,.2f}")
    
    st.markdown("---")
    st.subheader("📊 Distribuição de Despesas do Mês")
    desp_df = df_mes[df_mes['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum().reset_index()
    if not desp_df.empty:
        fig = px.pie(desp_df, values='Valor', names='Categoria', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig, use_container_width=True)
        # FUNCIONALIDADE DRILL-DOWN (O que você pediu: clicar e ver detalhes)
        st.markdown("### 🔍 Detalhamento por Categoria")
        sel_cat = st.selectbox("Escolha uma categoria para abrir a tabela de gastos:", ["Selecione..."] + list(desp_df['Categoria'].unique()))
        if sel_cat != "Selecione...":
            detalhe = df_mes[(df_mes['Categoria'] == sel_cat) & (df_mes['Tipo'] == 'Despesa')]
            st.dataframe(detalhe[['Data', 'Descrição', 'Forma de Pagamento', 'Valor', 'Observações']], hide_index=True, use_container_width=True)

def pagina_adicionar():
    st.title("✍️ Adicionar Lançamento")
    df_existente = carregar_dados()
    cats = carregar_categorias()
    prox_id = int(df_existente['ID'].max() + 1) if not df_existente.empty else 1
    with st.form("novo_lancamento_form"):
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data", datetime.now()); tp = c2.selectbox("Tipo", ['Despesa', 'Receita', 'Sobra']); vl = c3.number_input("Valor Total", 0.01)
        ds, ct = st.text_input("Descrição"), st.selectbox("Categoria", cats)
        cl, mt = c1.selectbox("Classificação", CLASSIFICACOES_PADRAO), c2.selectbox("Método", MEIOS_PAGAMENTO_PADRAO)
        fr, pg = c1.selectbox("Forma", ['À Vista', 'Parcelado']), c2.selectbox("Pago?", ['Sim', 'Não'])
        ob = st.text_area("Observações", "-")
        st.markdown("---")
        cp1, cp2, cp3 = st.columns(3)
        n_p = cp1.number_input("Nº parcelas", 1, 60, 1)
        m_c, a_c = cp2.number_input("Mês Contábil", 1, 12, dt.month), cp3.number_input("Ano Contábil", 2024, 2030, dt.year)
        if st.form_submit_button("Adicionar Lançamento"):
            novos = []; p_str = 'OK' if pg == 'Sim' else 'NOK'
            if fr == 'À Vista' or tp != 'Despesa':
                novos.append({'ID':prox_id,'Data':dt.strftime('%d/%m/%Y'),'Tipo':tp,'Descrição':ds,'Valor':vl,'Categoria':ct,'Classificação':cl,'Pagamento':fr,'Forma de Pagamento':mt,'Parcelas':'N/A','Pagamento Realizado':p_str,'Observações':ob,'Mês':MAPA_MESES[m_c],'Ano':a_c})
            else:
                v_p = vl / n_p
                for i in range(n_p):
                    m, a = m_c+i, a_c
                    while m > 12: m-=12; a+=1
                    novos.append({'ID':prox_id+i,'Data':dt.strftime('%d/%m/%Y'),'Tipo':tp,'Descrição':f"{ds} ({i+1}/{n_p})",'Valor':v_p,'Categoria':ct,'Classificação':cl,'Pagamento':fr,'Forma de Pagamento':mt,'Parcelas':f"{i+1:02d} de {n_p:02d}",'Pagamento Realizado':p_str,'Observações':ob,'Mês':MAPA_MESES[m],'Ano':a})
            if salvar_dados(pd.concat([df_existente, pd.DataFrame(novos)], ignore_index=True)): st.success("Salvo!"); st.rerun()

def pagina_gerenciar():
    st.title("🛠️ Gerenciar Lançamento")
    df = carregar_dados()
    col_id, col_btn = st.columns([3, 1])
    id_in = col_id.number_input("Digite o ID", min_value=1, step=1)
    if col_btn.button("🔍 Buscar Lançamento", use_container_width=True): st.session_state.id_g = id_in
    if 'id_g' in st.session_state:
        idx = st.session_state.id_g
        if idx in df['ID'].values:
            row = df.index[df['ID'] == idx].tolist()[0]
            st.success(f"ID {idx} encontrado!"); st.dataframe(df.loc[[row]], hide_index=True)
            ce, cd = st.columns(2)
            with ce:
                with st.expander("📝 Editar"):
                    with st.form("ed"):
                        col1, col2 = st.columns(2)
                        n_dt = col1.text_input("Data", df.at[row, 'Data']); n_ds = col2.text_input("Desc", df.at[row, 'Descrição'])
                        n_vl = col1.number_input("Valor", value=float(df.at[row, 'Valor'])); n_ct = col2.selectbox("Cat", carregar_categorias())
                        n_cl = col1.selectbox("Classif", CLASSIFICACOES_PADRAO); n_mt = col2.selectbox("Método", MEIOS_PAGAMENTO_PADRAO)
                        n_pg = col1.selectbox("Pago?", ['OK','NOK','N/A']); n_pa = col2.text_input("Parcelas", df.at[row, 'Parcelas'])
                        if st.form_submit_button("Salvar"):
                            df.at[row,'Data'], df.at[row,'Descrição'], df.at[row,'Valor'], df.at[row,'Categoria'], df.at[row,'Classificação'], df.at[row,'Forma de Pagamento'], df.at[row,'Pagamento Realizado'], df.at[row,'Parcelas'] = n_dt, n_ds, n_vl, n_ct, n_cl, n_mt, n_pg, n_pa
                            if salvar_dados(df): st.toast("Atualizado!"); st.rerun()
            with cd:
                with st.popover("🗑️ Excluir"):
                    if st.button("Confirmar Exclusão Definitiva"):
                        df = df.drop(row).reset_index(drop=True); df['ID'] = range(1, len(df)+1)
                        if salvar_dados(df): st.success("Excluído!"); del st.session_state.id_g; st.rerun()
        else: st.error("Não encontrado.")

def pagina_relatorio():
    st.title("📊 Relatório Mensal")
    c1, c2 = st.columns(2)
    ano, mes = c1.number_input("Ano", 2024, 2030, 2026), c2.selectbox("Mês", MESES_ORDENADOS, index=datetime.now().month-1)
    if st.button("Gerar"):
        df_r = carregar_dados()
        df_r = df_r[(df_r['Ano'] == ano) & (df_r['Mês'] == mes)]
        if not df_r.empty: st.dataframe(df_r[['ID','Data','Descrição','Categoria','Forma de Pagamento','Parcelas', 'Valor','Observações']], hide_index=True)

def pagina_faturas():
    st.title("💳 Faturas de Cartão")
    cartao = st.selectbox("Cartão", ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG'])
    if st.button("Ver Fatura"):
        df_f = carregar_dados()
        df_f = df_f[df_f['Forma de Pagamento'] == cartao]
        st.metric(f"Total", f"R$ {df_f['Valor'].sum():,.2f}")
        st.dataframe(df_f[['ID','Data','Descrição','Categoria','Parcelas','Valor','Observações']], hide_index=True)

def pagina_configuracoes():
    st.title("⚙️ Categorias")
    c1, c2, c3 = st.columns(3)
    with c1:
        nova = st.text_input("Nova")
        if st.button("Add"):
            ws = connect_to_gsheet().open(NOME_DA_PLANILHA).worksheet("Categorias")
            ws.append_row([nova]); st.rerun()
    with c2:
        ed, nv = st.selectbox("Editar", carregar_categorias()), st.text_input("Novo nome")
        if st.button("Atualizar"):
            df = carregar_dados(); df['Categoria'] = df['Categoria'].replace(ed, nv)
            if salvar_dados(df):
                ws = connect_to_gsheet().open(NOME_DA_PLANILHA).worksheet("Categorias")
                cel = ws.find(ed); ws.update_cell(cel.row, 1, nv); st.rerun()
    with c3:
        rm, sb = st.selectbox("Excluir", carregar_categorias()), st.selectbox("Substituir por", carregar_categorias())
        if st.button("Remover"):
            df = carregar_dados(); df['Categoria'] = df['Categoria'].replace(rm, sb)
            if salvar_dados(df):
                ws = connect_to_gsheet().open(NOME_DA_PLANILHA).worksheet("Categorias")
                cel = ws.find(rm); ws.delete_rows(cel.row); st.rerun()

def pagina_graficos():
    st.title("🎨 Gráficos Analíticos")
    df = carregar_dados()
    if not df.empty:
        res = df[df['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum().reset_index()
        st.plotly_chart(px.bar(res, x='Categoria', y='Valor', color='Categoria'), use_container_width=True)

# --- MENU PRINCIPAL ---
st.sidebar.title("🏛️ Menu Principal")
paginas = {"Página Inicial": pagina_inicial, "Adicionar Lançamento": pagina_adicionar, "Gerenciar Lançamento": pagina_gerenciar, "Relatório Mensal": pagina_relatorio, "Ver Faturas de Cartão": pagina_faturas, "Configurações de Categoria": pagina_configuracoes, "Gráficos Analíticos": pagina_graficos}
escolha = st.sidebar.radio("Navegue:", list(paginas.keys()))
paginas[escolha]()
