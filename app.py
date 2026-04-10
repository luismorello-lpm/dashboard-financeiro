import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Meu Dashboard Financeiro",
    page_icon="📊",
    layout="wide"
)

# --- CONFIGURAÇÃO DA CONEXÃO ---
NOME_DA_PLANILHA = "DashboardFinanceiroDB"
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

@st.cache_resource
def connect_to_gsheet():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Erro ao conectar com o Google Sheets: {e}")
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
    last_comma = s.rfind(',')
    last_dot = s.rfind('.')
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
            spreadsheet = client.open(NOME_DA_PLANILHA)
            worksheet = spreadsheet.sheet1
            df_para_salvar = df.copy()
            if 'Valor' in df_para_salvar.columns:
                 df_para_salvar['Valor'] = df_para_salvar['Valor'].apply(lambda x: f"{x:.2f}".replace('.', ',') if pd.notna(x) else '')
            for col in df_para_salvar.columns: df_para_salvar[col] = df_para_salvar[col].astype(str)
            worksheet.clear()
            set_with_dataframe(worksheet, df_para_salvar, include_index=False, include_column_header=True, resize=True)
            st.cache_data.clear()
            return True
        except: return False
    return False

# --- GESTÃO DE CATEGORIAS (COM EDIÇÃO EM CASCATA) ---
@st.cache_data(ttl=60)
def carregar_categorias():
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            ws = spreadsheet.worksheet("Categorias")
            lista = ws.col_values(1)[1:]
            return sorted([c for c in lista if c]) if lista else ["Geral"]
        except: return ["Alimentação", "Transporte", "Saúde", "Moradia"]
    return []

def salvar_categoria_db(nova_cat):
    client = connect_to_gsheet()
    if client:
        try:
            ws = client.open(NOME_DA_PLANILHA).worksheet("Categorias")
            ws.append_row([nova_cat])
            st.cache_data.clear()
            return True
        except: return False
    return False

def excluir_categoria_db(cat_nome):
    client = connect_to_gsheet()
    if client:
        try:
            ws = client.open(NOME_DA_PLANILHA).worksheet("Categorias")
            celula = ws.find(cat_nome)
            if celula:
                ws.delete_rows(celula.row)
                st.cache_data.clear()
                return True
        except: return False
    return False

def editar_categoria_db(nome_antigo, nome_novo):
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            # 1. Atualiza na lista de categorias
            ws_cat = spreadsheet.worksheet("Categorias")
            celula = ws_cat.find(nome_antigo)
            if celula: ws_cat.update_cell(celula.row, celula.col, nome_novo)
            
            # 2. Atualiza registros antigos na Sheet1
            ws_dados = spreadsheet.sheet1
            dados = ws_dados.get_all_values()
            df_temp = pd.DataFrame(dados[1:], columns=dados[0])
            if 'Categoria' in df_temp.columns:
                df_temp['Categoria'] = df_temp['Categoria'].replace(nome_antigo, nome_novo)
                salvar_dados(df_temp) # Reutiliza a função de salvar para manter o formato
            return True
        except: return False
    return False

# --- PÁGINAS ---
def pagina_inicial():
    st.title("🏠 Página Inicial")
    df = carregar_dados()
    if df.empty:
        st.warning("Base vazia.")
        return
    df['Valor Fin.'] = np.where(df['Tipo'] == 'Despesa', -df['Valor'], df['Valor'])
    mes_atual = MAPA_MESES[datetime.now().month]
    df_mes = df[(df['Ano'] == datetime.now().year) & (df['Mês'] == mes_atual)]
    
    if not df_mes.empty:
        rec = df_mes[df_mes['Valor Fin.'] > 0]['Valor Fin.'].sum()
        desp = df_mes[df_mes['Valor Fin.'] < 0]['Valor Fin.'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Receitas", f"R$ {rec:,.2f}")
        c2.metric("Despesas", f"R$ {desp:,.2f}")
        c3.metric("Saldo", f"R$ {rec+desp:,.2f}")
        st.divider()
        st.subheader("Últimos Lançamentos")
        st.dataframe(df_mes.tail(5), hide_index=True)

def pagina_adicionar():
    st.title("✍️ Novo Lançamento")
    df_existente = carregar_dados()
    categorias = carregar_categorias()
    proximo_id = int(df_existente['ID'].max() + 1) if not df_existente.empty else 1

    with st.form("form_add"):
        c1, c2, c3 = st.columns(3)
        data = c1.date_input("Data", datetime.now())
        tipo = c2.selectbox("Tipo", ['Despesa', 'Receita', 'Sobra'])
        valor = c3.number_input("Valor", min_value=0.01, format="%.2f")
        desc = st.text_input("Descrição")
        cat = st.selectbox("Categoria", categorias)
        
        if tipo == 'Despesa':
            c1, c2 = st.columns(2)
            classif = c1.selectbox("Classificação", ['Essencial', 'Não Essencial', 'Extra'])
            pag = c1.selectbox("Forma", ['À Vista', 'Parcelado'])
            metodo = c2.selectbox("Método", ['Vale Alimentação', 'Débito Nubank', 'Débito Santander', 'Crédito Nubank', 'Crédito Santander', 'Boleto', 'Crédito BTG', 'Dinheiro', 'Pix'])
            pago = c2.selectbox("Pago?", ['Sim', 'Não'])
            
            if pag == 'Parcelado':
                cp1, cp2, cp3 = st.columns(3)
                n_parc = cp1.number_input("Parcelas", 2, 60, 2)
                m_ini = cp2.number_input("Mês Início", 1, 12, datetime.now().month)
                a_ini = cp3.number_input("Ano Início", 2024, 2030, datetime.now().year)
            else:
                m_ini, a_ini = datetime.now().month, datetime.now().year
        else:
            m_ini, a_ini = datetime.now().month, datetime.now().year

        if st.form_submit_button("Salvar"):
            novos = []
            if tipo != 'Despesa' or pag == 'À Vista':
                novos.append({'ID': proximo_id, 'Data': data.strftime('%d/%m/%Y'), 'Tipo': tipo, 'Descrição': desc, 'Valor': valor, 'Categoria': cat, 'Classificação': classif if tipo=='Despesa' else 'N/A', 'Pagamento': pag if tipo=='Despesa' else 'N/A', 'Forma de Pagamento': metodo if tipo=='Despesa' else 'N/A', 'Parcelas': 'N/A', 'Pagamento Realizado': 'OK' if (tipo!='Despesa' or pago=='Sim') else 'NOK', 'Observações': '-', 'Mês': MAPA_MESES[m_ini], 'Ano': a_ini})
            else:
                for i in range(n_parc):
                    m, a = m_ini + i, a_ini
                    while m > 12: m -= 12; a += 1
                    novos.append({'ID': proximo_id+i, 'Data': data.strftime('%d/%m/%Y'), 'Tipo': tipo, 'Descrição': f"{desc} ({i+1}/{n_parc})", 'Valor': valor/n_parc, 'Categoria': cat, 'Classificação': classif, 'Pagamento': pag, 'Forma de Pagamento': metodo, 'Parcelas': f"{i+1:02d}/{n_parc:02d}", 'Pagamento Realizado': 'OK' if pago=='Sim' else 'NOK', 'Observações': '-', 'Mês': MAPA_MESES[m], 'Ano': a})
            
            df_final = pd.concat([df_existente, pd.DataFrame(novos)], ignore_index=True)
            if salvar_dados(df_final): st.success("Salvo!"); st.rerun()

def pagina_configuracoes():
    st.title("⚙️ Configurações de Categorias")
    cats = carregar_categorias()
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.subheader("✨ Adicionar")
        n_cat = st.text_input("Nova Categoria")
        if st.button("Adicionar"):
            if n_cat and n_cat not in cats:
                if salvar_categoria_db(n_cat): st.success("Adicionada!"); st.rerun()

    with c2:
        st.subheader("📝 Editar")
        cat_ed = st.selectbox("Categoria Atual", ["Selecione..."] + cats)
        novo_n = st.text_input("Novo Nome")
        if st.button("Atualizar Tudo"):
            if cat_ed != "Selecione..." and novo_n:
                with st.spinner("Atualizando registros..."):
                    if editar_categoria_db(cat_ed, novo_n): st.success("Atualizado!"); st.rerun()

    with c3:
        st.subheader("🗑️ Remover")
        cat_rm = st.selectbox("Remover Categoria", ["Selecione..."] + cats)
        if st.button("Confirmar"):
            if cat_rm != "Selecione..." and excluir_categoria_db(cat_rm): st.success("Removida!"); st.rerun()

# --- DEMAIS PÁGINAS (VERSÃO SIMPLIFICADA) ---
def pagina_gerenciar():
    st.title("🛠️ Gerenciar")
    df = carregar_dados()
    id_sel = st.number_input("ID do Lançamento", min_value=1)
    if st.button("Excluir"):
        df = df[df['ID'] != id_sel]
        if salvar_dados(df): st.success("Excluído!"); st.rerun()

def pagina_relatorio():
    st.title("📊 Relatórios")
    df = carregar_dados()
    mes = st.selectbox("Mês", list(range(1, 13)), format_func=lambda x: MAPA_MESES[x])
    if st.button("Gerar"):
        df_r = df[df['Mês'] == MAPA_MESES[mes]]
        st.dataframe(df_r, hide_index=True)

def pagina_faturas():
    st.title("💳 Faturas")
    df = carregar_dados()
    cartao = st.selectbox("Cartão", ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG'])
    if st.button("Consultar"):
        df_f = df[df['Forma de Pagamento'] == cartao]
        st.dataframe(df_f, hide_index=True)

def pagina_graficos():
    st.title("🎨 Gráficos")
    df = carregar_dados()
    if not df.empty:
        res = df[df['Tipo']=='Despesa'].groupby('Categoria')['Valor'].sum()
        fig, ax = plt.subplots()
        ax.pie(res, labels=res.index, autopct='%1.1f%%')
        st.pyplot(fig)

# --- MENU ---
paginas = {
    "Página Inicial": pagina_inicial,
    "Adicionar Lançamento": pagina_adicionar,
    "Gerenciar Lançamento": pagina_gerenciar,
    "Relatório Mensal": pagina_relatorio,
    "Faturas de Cartão": pagina_faturas,
    "Configurações": pagina_configuracoes,
    "Gráficos Analíticos": pagina_graficos
}
escolha = st.sidebar.radio("Navegação", list(paginas.keys()))
paginas[escolha]()
