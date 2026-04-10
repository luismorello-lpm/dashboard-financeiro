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

# --- FUNÇÕES AUXILIARES ---
MAPA_MESES = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 
    7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
}
MESES_ORDENADOS = list(MAPA_MESES.values())

MEIOS_PAGAMENTO_PADRAO = [
    'Vale Alimentação', 'Débito Nubank', 'Débito Santander', 'Crédito Nubank', 
    'Crédito Santander', 'Boleto', 'Crédito BTG', 'Dinheiro', 'Pix', 'Transf. BTG'
]

CLASSIFICACOES_PADRAO = ['Essencial', 'Não Essencial', 'Extra']

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

@st.cache_data(ttl=60)
def carregar_categorias():
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            ws = spreadsheet.worksheet("Categorias")
            lista = ws.col_values(1)[1:]
            return sorted([c for c in lista if c]) if lista else ["Geral"]
        except: return ["Entrada", "Transporte", "Saúde", "Moradia"]
    return []

def excluir_categoria_db(cat_nome, cat_substituta):
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            df_atual = carregar_dados()
            if not df_atual.empty and 'Categoria' in df_atual.columns:
                df_atual['Categoria'] = df_atual['Categoria'].replace(cat_nome, cat_substituta)
                salvar_dados(df_atual)
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
            df_atual = carregar_dados()
            if not df_atual.empty and 'Categoria' in df_atual.columns:
                df_atual['Categoria'] = df_atual['Categoria'].replace(nome_antigo, nome_novo)
                salvar_dados(df_atual)
            st.cache_data.clear()
            return True
        except: return False
    return False

# --- PÁGINAS ---

def pagina_inicial():
    st.title("🏠 Página Inicial")
    df = carregar_dados()
    if df.empty:
        st.warning("Base de dados vazia.")
        return

    df['Valor Fin.'] = np.where(df['Tipo'] == 'Despesa', -df['Valor'], df['Valor'])
    hoje = datetime.now()
    mes_atual_nome = MAPA_MESES[hoje.month]
    df_mes = df[(df['Ano'] == hoje.year) & (df['Mês'] == mes_atual_nome)]

    if not df_mes.empty:
        rec, desp = df_mes[df_mes['Valor Fin.'] > 0]['Valor Fin.'].sum(), df_mes[df_mes['Valor Fin.'] < 0]['Valor Fin.'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("🟢 Receitas", f"R$ {rec:,.2f}")
        c2.metric("🔴 Despesas", f"R$ {desp:,.2f}")
        c3.metric("💰 Saldo", f"R$ {rec+desp:,.2f}")

    st.markdown("---")
    st.subheader("📊 Distribuição de Despesas do Mês")
    despesas_df = df_mes[df_mes['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum().reset_index()
    
    if not despesas_df.empty:
        fig = px.pie(despesas_df, values='Valor', names='Categoria', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("### 🔍 Detalhamento por Categoria")
        sel_cat = st.selectbox("Selecione para ver detalhes:", ["Escolha..."] + list(despesas_df['Categoria'].unique()))
        if sel_cat != "Escolha...":
            det = df_mes[(df_mes['Categoria'] == sel_cat) & (df_mes['Tipo'] == 'Despesa')]
            st.dataframe(det[['Data', 'Descrição', 'Forma de Pagamento', 'Valor', 'Observações']], hide_index=True, use_container_width=True)
            st.metric(f"Total em {sel_cat}", f"R$ {det['Valor'].sum():,.2f}")

def pagina_adicionar():
    st.title("✍️ Adicionar Novo Lançamento")
    df_existente = carregar_dados()
    cats = carregar_categorias()
    proximo_id = int(df_existente['ID'].max() + 1) if not df_existente.empty else 1

    with st.form("novo_form"):
        c1, c2, c3 = st.columns(3)
        data_l = c1.date_input("Data", datetime.now())
        tipo = c2.selectbox("Tipo", ['Despesa', 'Receita', 'Sobra'])
        valor = c3.number_input("Valor Total (R$)", min_value=0.01, format="%.2f")
        desc, cat = st.text_input("Descrição"), st.selectbox("Categoria", cats)
        c1, c2 = st.columns(2)
        classif, metodo = c1.selectbox("Classificação", CLASSIFICACOES_PADRAO), c2.selectbox("Método", MEIOS_PAGAMENTO_PADRAO)
        forma, pago = c1.selectbox("Forma", ['À Vista', 'Parcelado']), c2.selectbox("Pago?", ['Sim', 'Não'])
        obs = st.text_area("Observações", "-")
        st.markdown("---")
        st.subheader("Configuração de Parcelas / Mês Contábil")
        cp1, cp2, cp3 = st.columns(3)
        n_parc = cp1.number_input("Número de parcelas", min_value=1, value=1)
        m_cont, a_cont = cp2.number_input("Mês Contábil", 1, 12, data_l.month), cp3.number_input("Ano Contábil", 2024, 2030, data_l.year)

        if st.form_submit_button("Adicionar Lançamento"):
            novos = []
            pago_str = 'OK' if pago == 'Sim' else 'NOK'
            if tipo != 'Despesa' or forma == 'À Vista':
                novos.append({'ID': proximo_id, 'Data': data_l.strftime('%d/%m/%Y'), 'Tipo': tipo, 'Descrição': desc, 'Valor': valor, 'Categoria': cat, 'Classificação': classif, 'Pagamento': forma, 'Forma de Pagamento': metodo, 'Parcelas': 'N/A', 'Pagamento Realizado': pago_str, 'Observações': obs, 'Mês': MAPA_MESES[m_cont], 'Ano': a_cont})
            else:
                for i in range(n_parc):
                    m, a = m_cont + i, a_cont
                    while m > 12: m -= 12; a += 1
                    novos.append({'ID': proximo_id + i, 'Data': data_l.strftime('%d/%m/%Y'), 'Tipo': tipo, 'Descrição': f"{desc} ({i+1}/{n_parc})", 'Valor': valor/n_parc, 'Categoria': cat, 'Classificação': classif, 'Pagamento': forma, 'Forma de Pagamento': metodo, 'Parcelas': f"{i+1:02d} de {n_parc:02d}", 'Pagamento Realizado': pago_str, 'Observações': obs, 'Mês': MAPA_MESES[m], 'Ano': a})
            df_final = pd.concat([df_existente, pd.DataFrame(novos)], ignore_index=True)
            if salvar_dados(df_final): st.success("Adicionado!"); st.rerun()

def pagina_gerenciar():
    st.title("🛠️ Gerenciar Lançamento")
    df = carregar_dados()
    if df is None or df.empty: return
    col_id, col_btn = st.columns([3, 1])
    id_in = col_id.number_input("Digite o ID", min_value=1, step=1)
    if col_btn.button("🔍 Buscar Lançamento", use_container_width=True): st.session_state.id_g = id_in

    if 'id_g' in st.session_state:
        idx = st.session_state.id_g
        if idx in df['ID'].values:
            row_idx = df.index[df['ID'] == idx].tolist()[0]
            dados = df.loc[row_idx]
            st.success(f"ID {idx} encontrado!")
            st.dataframe(df.loc[[row_idx]], hide_index=True)
            st.markdown("---")
            c_edit, c_del = st.columns(2)
            with c_edit:
                with st.expander("📝 Editar Lançamento"):
                    with st.form("edit_f"):
                        col1, col2, col3 = st.columns(3)
                        n_dt = col1.text_input("Data", value=str(dados['Data']))
                        n_tp = col1.selectbox("Tipo", ['Despesa','Receita','Sobra'], index=['Despesa','Receita','Sobra'].index(dados['Tipo']))
                        n_vl = col1.number_input("Valor", value=float(dados['Valor']))
                        n_ds = col2.text_input("Descrição", value=str(dados['Descrição']))
                        n_ct = col2.selectbox("Categoria", carregar_categorias(), index=0)
                        n_cl = col2.selectbox("Classificação", CLASSIFICACOES_PADRAO, index=0)
                        n_mt = col3.selectbox("Método", MEIOS_PAGAMENTO_PADRAO, index=0)
                        n_pg = col3.selectbox("Pago?", ['OK','NOK','N/A'], index=0)
                        n_pa = col3.text_input("Parcelas", value=str(dados['Parcelas']))
                        n_ob = st.text_area("Obs", value=str(dados['Observações']))
                        if st.form_submit_button("Salvar"):
                            df.at[row_idx,'Data'], df.at[row_idx,'Tipo'], df.at[row_idx,'Valor'], df.at[row_idx,'Descrição'], df.at[row_idx,'Categoria'], df.at[row_idx,'Classificação'], df.at[row_idx,'Forma de Pagamento'], df.at[row_idx,'Pagamento Realizado'], df.at[row_idx,'Observações'], df.at[row_idx,'Parcelas'] = n_dt, n_tp, n_vl, n_ds, n_ct, n_cl, n_mt, n_pg, n_ob, n_pa
                            if salvar_dados(df): st.toast("Atualizado!"); st.rerun()
            with c_del:
                with st.popover("🗑️ Excluir"):
                    if st.button("Confirmar Exclusão", type="primary"):
                        df = df.drop(row_idx).reset_index(drop=True)
                        if not df.empty: df['ID'] = range(1, len(df) + 1)
                        if salvar_dados(df): st.success(f"ID {idx} removido!"); del st.session_state.id_g; st.rerun()
        else: st.error("ID não encontrado.")

def pagina_relatorio():
    st.title("📊 Relatório Financeiro")
    c1, c2 = st.columns(2)
    ano, mes = c1.number_input("Ano", 2024, 2030, 2026), c2.selectbox("Mês", MESES_ORDENADOS, index=datetime.now().month-1)
    if st.button("Gerar Relatório"):
        df = carregar_dados()
        df_r = df[(df['Ano'] == ano) & (df['Mês'] == mes)]
        if not df_r.empty: st.dataframe(df_r[['ID','Data','Descrição','Categoria','Forma de Pagamento','Parcelas','Valor','Observações']], hide_index=True)
        else: st.warning("Sem dados.")

def pagina_faturas():
    st.title("💳 Faturas de Cartão")
    cartao = st.selectbox("Cartão", ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG'])
    if st.button("Ver Fatura"):
        df = carregar_dados()
        df_f = df[df['Forma de Pagamento'] == cartao]
        st.metric(f"Total {cartao}", f"R$ {df_f['Valor'].sum():,.2f}")
        st.dataframe(df_f[['ID','Data','Descrição','Categoria','Parcelas','Valor','Observações']], hide_index=True)

def pagina_configuracoes():
    st.title("⚙️ Configurações de Categoria")
    col1, col2, col3 = st.columns(3)
    with col1:
        nova = st.text_input("Nova")
        if st.button("Add"): 
            if salvar_categoria_db(nova): st.success("Ok!"); st.rerun()
    with col2:
        ed_cat, novo_n = st.selectbox("Editar", carregar_categorias()), st.text_input("Novo nome")
        if st.button("Atualizar"):
            if editar_categoria_db(ed_cat, novo_n): st.success("Atualizado!"); st.rerun()
    with col3:
        rm_cat, sub_cat = st.selectbox("Excluir", carregar_categorias()), st.selectbox("Substituir por", carregar_categorias())
        if st.button("Remover"):
            if excluir_categoria_db(rm_cat, sub_cat): st.success("Removido!"); st.rerun()

def pagina_graficos():
    st.title("🎨 Gráficos Analíticos")
    df = carregar_dados()
    escolha = st.selectbox("Escolha", ["Gastos por Categoria (Mensal)", "Balanço (Anual)"])
    if "Mensal" in escolha:
        res = df[df['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum().reset_index()
        st.plotly_chart(px.pie(res, values='Valor', names='Categoria', hole=0.4), use_container_width=True)

# --- MENU PRINCIPAL ---
st.sidebar.title("🏛️ Menu Principal")
paginas = {"Página Inicial": pagina_inicial, "Adicionar Lançamento": pagina_adicionar, "Gerenciar Lançamento": pagina_gerenciar, "Relatório Mensal": pagina_relatorio, "Ver Faturas de Cartão": pagina_faturas, "Configurações de Categoria": pagina_configuracoes, "Gráficos Analíticos": pagina_graficos}
escolha = st.sidebar.radio("Navegue pelas páginas", list(paginas.keys()))
paginas[escolha]()
