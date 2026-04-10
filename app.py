import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px  
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Meu Dashboard Financeiro",
    page_icon="📊",
    layout="wide"
)

# --- URL OFICIAL DO SEU APP ---
BASE_URL = "https://dashboardfinanceiro-lpm.streamlit.app/"

# --- 1. LÓGICA DE NAVEGAÇÃO POR URL (QUERY PARAMS) ---
# Esta parte DEVE vir antes de qualquer desenho de interface
query_params = st.query_params

if "editar_id" in query_params:
    st.session_state.pagina_ativa = "Gerenciar Lançamento"
    st.session_state.id_para_gerenciar = int(query_params["editar_id"])
    st.session_state.acao_gerenciar = "editar"
elif "excluir_id" in query_params:
    st.session_state.pagina_ativa = "Gerenciar Lançamento"
    st.session_state.id_para_gerenciar = int(query_params["excluir_id"])
    st.session_state.acao_gerenciar = "excluir"
elif "pagina_ativa" not in st.session_state:
    st.session_state.pagina_ativa = "Página Inicial"

# --- CONFIGURAÇÃO DA CONEXÃO COM GOOGLE SHEETS ---
NOME_DA_PLANILHA = "DashboardFinanceiroDB"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

@st.cache_resource
def connect_to_gsheet():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Erro ao conectar: {e}")
        return None

# --- FUNÇÕES AUXILIARES DE DADOS ---
MAPA_MESES = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 
    7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
}
MESES_ORDENADOS = list(MAPA_MESES.values())

def clean_valor(valor_str):
    s = str(valor_str).strip().replace('R$', '').replace(' ', '')
    if not s: return np.nan
    last_comma, last_dot = s.rfind(','), s.rfind('.')
    if last_comma > last_dot: s = s.replace('.', '').replace(',', '.')
    elif last_dot > last_comma: s = s.replace(',', '')
    elif last_comma != -1 and last_dot == -1: s = s.replace(',', '.')
    return pd.to_numeric(s, errors='coerce')

@st.cache_data(ttl=60)
def carregar_dados():
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            worksheet = spreadsheet.sheet1
            data = worksheet.get_all_values()
            if not data or len(data) < 2: return pd.DataFrame()
            df = pd.DataFrame(data[1:], columns=[h.strip() for h in data[0]])
            for col in ['ID', 'Ano', 'Valor']:
                if col in df.columns:
                    if col == 'Valor': df[col] = df[col].apply(clean_valor)
                    else: df[col] = pd.to_numeric(df[col], errors='coerce')
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
            for col in df_para_salvar.columns: df_para_salvar[col] = df_para_salvar[col].astype(str)
            ws.clear()
            set_with_dataframe(ws, df_para_salvar, include_index=False, include_column_header=True, resize=True)
            st.cache_data.clear()
            return True
        except: return False
    return False

# --- GESTÃO DE CATEGORIAS ---
@st.cache_data(ttl=60)
def carregar_categorias():
    client = connect_to_gsheet()
    if client:
        try:
            ws = client.open(NOME_DA_PLANILHA).worksheet("Categorias")
            lista = ws.col_values(1)[1:]
            return sorted([c for c in lista if c]) if lista else ["Geral"]
        except: return ["Entrada", "Transporte", "Saúde", "Moradia"]
    return []

def excluir_categoria_db(cat_nome, cat_substituta):
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            df_temp = carregar_dados()
            if 'Categoria' in df_temp.columns:
                df_temp['Categoria'] = df_temp['Categoria'].replace(cat_nome, cat_substituta)
                salvar_dados(df_temp)
            ws_cat = spreadsheet.worksheet("Categorias")
            celula = ws_cat.find(cat_nome)
            if celula: ws_cat.delete_rows(celula.row)
            st.cache_data.clear()
            return True
        except: return False
    return False

def editar_categoria_db(nome_antigo, nome_novo):
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            ws_cat = spreadsheet.worksheet("Categorias")
            celula = ws_cat.find(nome_antigo)
            if celula: ws_cat.update_cell(celula.row, celula.col, nome_novo)
            df_temp = carregar_dados()
            if 'Categoria' in df_temp.columns:
                df_temp['Categoria'] = df_temp['Categoria'].replace(nome_antigo, nome_novo)
                salvar_dados(df_temp)
            return True
        except: return False
    return False

# --- PÁGINAS ---

def pagina_inicial():
    st.title("🏠 Página Inicial")
    st.subheader("Resumo do Mês Corrente")
    df = carregar_dados()
    if df.empty: return
    df['V_Fin'] = np.where(df['Tipo'] == 'Despesa', -df['Valor'], df['Valor'])
    hoje = datetime.now()
    df_mes = df[(df['Ano'] == hoje.year) & (df['Mês'] == MAPA_MESES[hoje.month])]
    if not df_mes.empty:
        rec, desp = df_mes[df_mes['V_Fin']>0]['V_Fin'].sum(), df_mes[df_mes['V_Fin']<0]['V_Fin'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("🟢 Receitas", f"R$ {rec:,.2f}"); c2.metric("🔴 Despesas", f"R$ {desp:,.2f}"); c3.metric("💰 Saldo", f"R$ {rec+desp:,.2f}")
    
    st.markdown("---")
    desp_df = df_mes[df_mes['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum().reset_index()
    if not desp_df.empty:
        fig = px.pie(desp_df, values='Valor', names='Categoria', hole=0.4, title="Distribuição de Despesas do Mês")
        st.plotly_chart(fig, use_container_width=True)

def pagina_adicionar():
    st.title("✍️ Adicionar Novo Lançamento")
    df = carregar_dados()
    cats = carregar_categorias()
    proximo_id = int(df['ID'].max() + 1) if not df.empty else 1
    with st.form("add_form"):
        c1, c2, c3 = st.columns(3)
        data = c1.date_input("Data", datetime.now()); tipo = c2.selectbox("Tipo", ['Despesa', 'Receita', 'Sobra']); valor = c3.number_input("Valor", 0.01, format="%.2f")
        desc, cat = st.text_input("Descrição"), st.selectbox("Categoria", cats)
        if st.form_submit_button("Adicionar"):
            novo = pd.DataFrame([{'ID': proximo_id, 'Data': data.strftime('%d/%m/%Y'), 'Tipo': tipo, 'Descrição': desc, 'Valor': valor, 'Categoria': cat, 'Mês': MAPA_MESES[data.month], 'Ano': data.year}])
            if salvar_dados(pd.concat([df, novo], ignore_index=True)): st.success("Salvo!"); st.rerun()

def pagina_gerenciar():
    st.title("🛠️ Gerenciar Lançamento")
    df = carregar_dados()
    
    # Recupera ID e ação dos estados
    id_alvo = st.session_state.get('id_para_gerenciar', 1)
    acao = st.session_state.get('acao_gerenciar', 'editar')
    
    id_input = st.number_input("ID do lançamento", min_value=1, value=int(id_alvo))
    res = df[df['ID'] == id_input]
    
    if not res.empty:
        st.dataframe(res, hide_index=True)
        if acao == "excluir":
            st.warning(f"⚠️ Confirmar exclusão do ID {id_input}?")
            if st.button("🔴 Confirmar"):
                df = df[df['ID'] != id_input]
                if salvar_dados(df): 
                    st.success("Excluído!"); st.query_params.clear(); st.rerun()
        else:
            if st.button("🗑️ Excluir Registro"):
                df = df[df['ID'] != id_input]
                if salvar_dados(df): st.success("Excluído!"); st.rerun()
    else: st.error("ID não encontrado.")

def pagina_relatorio():
    st.title("📊 Gerador de Relatório Financeiro")
    c1, c2 = st.columns(2)
    ano, mes = c1.number_input("Ano", 2020, 2030, datetime.now().year), c2.selectbox("Mês", list(range(1, 13)), format_func=lambda x: MAPA_MESES[x], index=datetime.now().month-1)
    
    if st.button("Gerar Relatório"):
        df = carregar_dados()
        df_r = df[(df['Ano'] == ano) & (df['Mês'] == MAPA_MESES[mes])].copy()
        if not df_r.empty:
            df_r['📝'] = df_r['ID'].apply(lambda x: f"{BASE_URL}?editar_id={x}")
            df_r['❌'] = df_r['ID'].apply(lambda x: f"{BASE_URL}?excluir_id={x}")
            cols = ['📝', '❌', 'ID', 'Data', 'Descrição', 'Categoria', 'Forma de Pagamento', 'Parcelas', 'Valor', 'Observações']
            st.dataframe(df_r[cols], hide_index=True, column_config={
                "📝": st.column_config.LinkColumn("Editar", display_text="📝"),
                "❌": st.column_config.LinkColumn("Excluir", display_text="❌"),
                "ID": st.column_config.NumberColumn(format="%d")
            })
        else: st.warning("Sem dados.")

def pagina_faturas():
    st.title("💳 Ver Faturas de Cartão de Crédito")
    df = carregar_dados()
    cartao = st.selectbox("Cartão", ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG'])
    if st.button("Consultar"):
        df_f = df[df['Forma de Pagamento'] == cartao]
        st.dataframe(df_f, hide_index=True)

def pagina_configuracoes():
    st.title("⚙️ Configurações de Categoria")
    cats = carregar_categorias()
    c1, c2, c3 = st.columns(3)
    with c1:
        n_cat = st.text_input("Nova Categoria")
        if st.button("Adicionar"):
            if n_cat and n_cat not in cats:
                if salvar_categoria_db(n_cat): st.success("Salvo!"); st.rerun()
    with c3:
        rm_cat = st.selectbox("Excluir Categoria", ["Selecione..."] + cats)
        cat_sub = st.selectbox("Substituir registros por", ["Selecione..."] + [c for c in cats if c != rm_cat])
        if st.button("Confirmar Exclusão"):
            if rm_cat != "Selecione..." and cat_sub != "Selecione...":
                if excluir_categoria_db(rm_cat, cat_sub): st.success("Excluído!"); st.rerun()

def pagina_graficos():
    st.title("🎨 Gráficos Analíticos")
    df = carregar_dados()
    if df.empty: return
    escolha = st.selectbox("Gráfico", ["Selecione...", "Gastos Mensais", "Balanço Anual"])
    if "Mensal" in escolha:
        res = df[df['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum().reset_index()
        st.plotly_chart(px.pie(res, values='Valor', names='Categoria', hole=0.4), use_container_width=True)

# --- MENU PRINCIPAL ---
st.sidebar.title("🏛️ Menu Principal")
paginas = {
    "Página Inicial": pagina_inicial, "Adicionar Lançamento": pagina_adicionar, "Gerenciar Lançamento": pagina_gerenciar,
    "Relatório Mensal": pagina_relatorio, "Ver Faturas de Cartão": pagina_faturas, "Configurações de Categoria": pagina_configuracoes,
    "Gráficos Analíticos": pagina_graficos
}

# Define qual página mostrar (baseado na URL ou no rádio)
def gerenciar_escolha():
    # Se a URL pediu uma troca de página, usamos ela
    pagina_solicitada = st.session_state.get("pagina_ativa", "Página Inicial")
    idx = list(paginas.keys()).index(pagina_solicitada)
    
    # Criamos o rádio. Se o usuário clicar nele, o radio ganha a prioridade.
    escolha = st.sidebar.radio("Navegue pelas páginas", list(paginas.keys()), index=idx)
    
    # Se o usuário trocou manualmente no rádio, atualizamos o estado
    if escolha != pagina_solicitada:
        st.session_state.pagina_ativa = escolha
        # Limpa os IDs da URL para evitar voltas infinitas
        if "id_para_gerenciar" in st.session_state: del st.session_state.id_para_gerenciar
        st.query_params.clear()
        
    return escolha

escolha_final = gerenciar_escolha()
paginas[escolha_final]()
