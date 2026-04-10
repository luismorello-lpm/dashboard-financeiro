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

# --- CONFIGURAÇÃO DA CONEXÃO COM O GOOGLE SHEETS ---
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
            
            colunas_numericas = ['ID', 'Ano', 'Valor']
            for col in colunas_numericas:
                if col in df.columns:
                    if col == 'Valor': df[col] = df[col].apply(clean_valor)
                    else: df[col] = pd.to_numeric(df[col], errors='coerce')

            df.dropna(subset=['ID'], inplace=True)
            df['ID'] = df['ID'].astype(int)
            df['Mês'] = pd.Categorical(df['Mês'], categories=MESES_ORDENADOS, ordered=True)
            return df
        except Exception as e:
            st.error(f"Erro ao carregar os dados da planilha: {e}")
            return pd.DataFrame()
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
            
            for col in df_para_salvar.columns:
                df_para_salvar[col] = df_para_salvar[col].astype(str)

            worksheet.clear()
            set_with_dataframe(worksheet, df_para_salvar, include_index=False, include_column_header=True, resize=True)
            st.cache_data.clear()
            return True
        except Exception as e:
            st.error(f"ERRO ao salvar os dados na planilha: {e}")
            return False
    return False

# --- FUNÇÕES DE CATEGORIAS DINÂMICAS ---
@st.cache_data(ttl=60)
def carregar_categorias():
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            try:
                worksheet = spreadsheet.worksheet("Categorias")
                lista = worksheet.col_values(1)[1:] # Pula cabeçalho
                return sorted([c for c in lista if c]) if lista else ["Geral"]
            except:
                # Fallback caso a aba não exista ainda
                return ["Alimentação", "Transporte", "Lazer", "Contas Fixas"]
        except:
            return ["Geral"]
    return []

def salvar_categoria_db(nova_cat):
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            worksheet = spreadsheet.worksheet("Categorias")
            worksheet.append_row([nova_cat])
            st.cache_data.clear()
            return True
        except Exception as e:
            st.error(f"Erro ao salvar categoria: {e}")
    return False

def excluir_categoria_db(cat_nome):
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            worksheet = spreadsheet.worksheet("Categorias")
            celula = worksheet.find(cat_nome)
            if celula:
                worksheet.delete_rows(celula.row)
                st.cache_data.clear()
                return True
        except Exception as e:
            st.error(f"Erro ao excluir categoria: {e}")
    return False

# --- PÁGINAS DO STREAMLIT ---

def pagina_inicial():
    st.title("🏠 Página Inicial")
    st.subheader("Resumo do Mês Corrente")

    df = carregar_dados()
    if df is None or df.empty:
        st.warning("A base de dados está vazia. Adicione um lançamento para começar.")
        return

    df['Valor Financeiro'] = np.where(df['Tipo'] == 'Despesa', -df['Valor'], df['Valor'])
    hoje = datetime.now()
    ano_atual = hoje.year
    mes_atual_num = hoje.month
    mes_atual_nome = MAPA_MESES[mes_atual_num]
    df_mes_atual = df[(df['Ano'] == ano_atual) & (df['Mês'] == mes_atual_nome)].copy()

    if df_mes_atual.empty:
        st.info(f"Nenhum dado encontrado para {mes_atual_nome}/{ano_atual}.")
    else:
        receitas = df_mes_atual[df_mes_atual['Valor Financeiro'] > 0]['Valor Financeiro'].sum()
        despesas = df_mes_atual[df_mes_atual['Valor Financeiro'] < 0]['Valor Financeiro'].sum()
        saldo = receitas + despesas

        col1, col2, col3 = st.columns(3)
        col1.metric("🟢 Receitas Totais", f"R$ {receitas:,.2f}")
        col2.metric("🔴 Despesas Totais", f"R$ {despesas:,.2f}")
        col3.metric("💰 Saldo do Mês", f"R$ {saldo:,.2f}")

    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Últimos 5 Lançamentos do Mês")
        if not df_mes_atual.empty:
            st.dataframe(df_mes_atual.tail(5), hide_index=True)
        else:
            st.info(f"Nenhum lançamento em {mes_atual_nome}.")
            
    with col2:
        st.subheader("Faturas do Próximo Mês")
        mes_proximo = mes_atual_num + 1
        ano_proximo = ano_atual
        if mes_proximo > 12:
            mes_proximo = 1
            ano_proximo += 1
        
        MAPA_MESES_REVERSO = {v: k for k, v in MAPA_MESES.items()}
        df_copy = df.copy()
        df_copy['Mes_Num'] = df_copy['Mês'].map(MAPA_MESES_REVERSO)
        cartoes = ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG']
        
        df_faturas_proximo_mes = df_copy[
            (df_copy['Forma de Pagamento'].isin(cartoes)) &
            (df_copy['Ano'] == ano_proximo) &
            (df_copy['Mes_Num'] == mes_proximo)
        ]

        if not df_faturas_proximo_mes.empty:
            faturas_em_aberto = df_faturas_proximo_mes.groupby('Forma de Pagamento')['Valor'].sum().reset_index()
            st.dataframe(faturas_em_aberto, hide_index=True)
        else:
            st.info(f"Nenhuma fatura para {MAPA_MESES[mes_proximo]}/{ano_proximo}.")

def pagina_adicionar():
    st.title("✍️ Adicionar Novo Lançamento")
    df_existente = carregar_dados()
    categorias = carregar_categorias()
    
    if df_existente is None:
        st.warning("Não foi possível carregar a base de dados.")
        return
        
    proximo_id = int(df_existente['ID'].max() + 1) if not df_existente.empty else 1

    with st.form("novo_lancamento_form"):
        col1, col2, col3 = st.columns(3)
        with col1: data_lancamento = st.date_input("Data", datetime.now())
        with col2: tipo = st.selectbox("Tipo", ['Despesa', 'Receita', 'Sobra'])
        with col3: valor = st.number_input("Valor (R$)", min_value=0.01, format="%.2f")
        
        descricao = st.text_input("Descrição")
        categoria = st.selectbox("Categoria", categorias)
        
        mes_contabil = datetime.now().month
        ano_contabil = datetime.now().year

        if tipo == 'Despesa':
            st.subheader("Detalhes da Despesa")
            c1, c2 = st.columns(2)
            with c1: 
                classificacao = st.selectbox("Classificação", ['Essencial', 'Não Essencial', 'Extra'])
                pagamento = st.selectbox("Forma", ['À Vista', 'Parcelado'])
            with c2:
                forma_pagamento = st.selectbox("Método", ['Vale Alimentação', 'Débito Nubank', 'Débito Santander', 'Crédito Nubank', 'Crédito Santander', 'Boleto', 'Crédito BTG', 'Dinheiro', 'Pix', 'Transf. BTG'])
                pagamento_realizado = st.selectbox("Pago?", ['Sim', 'Não'])

            observacoes = st.text_area("Observações", "-")
            
            if pagamento == 'À Vista':
                col1, col2 = st.columns(2)
                with col1: mes_contabil = st.number_input("Mês Contábil", 1, 12, datetime.now().month)
                with col2: ano_contabil = st.number_input("Ano Contábil", 2020, 2030, datetime.now().year)
            else:
                col1, col2, col3 = st.columns(3)
                with col1: total_parcelas = st.number_input("Total Parcelas", 2, 60, 2)
                with col2: mes_inicial = st.number_input("Mês da 1ª", 1, 12, datetime.now().month)
                with col3: ano_inicial = st.number_input("Ano da 1ª", 2020, 2030, datetime.now().year)
        else:
            col1, col2 = st.columns(2)
            with col1: mes_contabil = st.number_input("Mês Contábil", 1, 12, datetime.now().month)
            with col2: ano_contabil = st.number_input("Ano Contábil", 2020, 2030, datetime.now().year)
        
        submitted = st.form_submit_button("Adicionar Lançamento")

        if submitted:
            novos_lancamentos = []
            if tipo != 'Despesa' or (tipo == 'Despesa' and pagamento == 'À Vista'):
                lancamento = {
                    'ID': proximo_id, 'Data': data_lancamento.strftime('%d/%m/%Y'), 'Tipo': tipo,
                    'Descrição': descricao, 'Valor': valor, 'Categoria': categoria,
                    'Classificação': classificacao if tipo == 'Despesa' else 'N/A',
                    'Pagamento': pagamento if tipo == 'Despesa' else 'N/A',
                    'Forma de Pagamento': forma_pagamento if tipo == 'Despesa' else 'N/A',
                    'Parcelas': 'N/A', 'Pagamento Realizado': 'OK' if (tipo != 'Despesa' or pagamento_realizado == 'Sim') else 'NOK',
                    'Observações': observacoes if tipo == 'Despesa' else '-',
                    'Mês': MAPA_MESES[mes_contabil], 'Ano': ano_contabil
                }
                novos_lancamentos.append(lancamento)
            else:
                for i in range(total_parcelas):
                    m = mes_inicial + i
                    a = ano_inicial
                    while m > 12: m -= 12; a += 1
                    lancamento = {
                        'ID': proximo_id + i, 'Data': data_lancamento.strftime('%d/%m/%Y'), 'Tipo': tipo,
                        'Descrição': f"{descricao} ({i+1}/{total_parcelas})", 'Valor': valor / total_parcelas, 'Categoria': categoria,
                        'Classificação': classificacao, 'Pagamento': pagamento, 'Forma de Pagamento': forma_pagamento,
                        'Parcelas': f"{i+1:02d} de {total_parcelas:02d}", 'Pagamento Realizado': 'OK' if pagamento_realizado == 'Sim' else 'NOK',
                        'Observações': observacoes, 'Mês': MAPA_MESES[m], 'Ano': a
                    }
                    novos_lancamentos.append(lancamento)

            df_atualizado = pd.concat([df_existente, pd.DataFrame(novos_lancamentos)], ignore_index=True)
            if salvar_dados(df_atualizado):
                st.success("Lançamento(s) adicionado(s)!")
                st.rerun()

def pagina_gerenciar():
    st.title("🛠️ Gerenciar Lançamento")
    df = carregar_dados()
    if df is None or df.empty: return
    
    id_input = st.number_input("Buscar por ID", min_value=1, step=1)
    if st.button("Buscar"):
        if id_input in df['ID'].values:
            idx = df.index[df['ID'] == id_input].tolist()[0]
            st.session_state.idx_edit = idx
        else: st.error("ID não encontrado.")

    if 'idx_edit' in st.session_state:
        idx = st.session_state.idx_edit
        st.dataframe(df.loc[[idx]], hide_index=True)
        if st.button("Excluir"):
            df = df.drop(idx).copy()
            if salvar_dados(df): st.success("Excluído!"); st.rerun()

def pagina_configuracoes():
    st.title("⚙️ Configurações de Categorias")
    st.info("Adicione ou remova categorias que aparecem no formulário de lançamentos.")
    
    categorias = carregar_categorias()
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("✨ Nova Categoria")
        nova_cat = st.text_input("Nome da Categoria")
        if st.button("Adicionar"):
            if nova_cat and nova_cat not in categorias:
                if salvar_categoria_db(nova_cat):
                    st.success(f"'{nova_cat}' adicionada!"); st.rerun()
            else: st.warning("Categoria inválida ou repetida.")
            
    with col2:
        st.subheader("🗑️ Remover Categoria")
        cat_del = st.selectbox("Selecione para remover", ["Selecione..."] + categorias)
        if st.button("Confirmar Remoção"):
            if cat_del != "Selecione...":
                if excluir_categoria_db(cat_del):
                    st.success("Removida!"); st.rerun()

def pagina_relatorio():
    st.title("📊 Relatório Mensal")
    df = carregar_dados()
    if df.empty: return
    
    c1, c2 = st.columns(2)
    ano = c1.number_input("Ano", 2020, 2030, datetime.now().year)
    mes = c2.selectbox("Mês", list(range(1, 13)), format_func=lambda x: MAPA_MESES[x], index=datetime.now().month-1)
    
    if st.button("Ver Relatório"):
        df_mes = df[(df['Ano'] == ano) & (df['Mês'] == MAPA_MESES[mes])]
        if not df_mes.empty:
            st.write(f"### Total: R$ {df_mes[df_mes['Tipo']=='Despesa']['Valor'].sum():,.2f}")
            st.dataframe(df_mes, hide_index=True)
        else: st.warning("Sem dados.")

def pagina_faturas():
    st.title("💳 Faturas de Cartão")
    df = carregar_dados()
    cartao = st.selectbox("Cartão", ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG'])
    mes = st.selectbox("Mês", list(range(1, 13)), format_func=lambda x: MAPA_MESES[x], index=datetime.now().month-1)
    ano = st.number_input("Ano", 2020, 2030, datetime.now().year)
    
    if st.button("Consultar"):
        df_f = df[(df['Forma de Pagamento'] == cartao) & (df['Mês'] == MAPA_MESES[mes]) & (df['Ano'] == ano)]
        if not df_f.empty:
            st.metric("Total", f"R$ {df_f['Valor'].sum():,.2f}")
            st.dataframe(df_f[['Data', 'Descrição', 'Valor', 'Parcelas']], hide_index=True)
        else: st.info("Nenhuma compra encontrada.")

def pagina_graficos():
    st.title("🎨 Gráficos Analíticos")
    df = carregar_dados()
    if df.empty: return
    
    tipo = st.selectbox("Gráfico", ["Gastos por Categoria (Mês)", "Balanço Anual"])
    
    if "Categoria" in tipo:
        mes = st.selectbox("Mês", list(range(1, 13)), format_func=lambda x: MAPA_MESES[x])
        df_g = df[(df['Mês'] == MAPA_MESES[mes]) & (df['Tipo'] == 'Despesa')]
        if not df_g.empty:
            res = df_g.groupby('Categoria')['Valor'].sum()
            fig, ax = plt.subplots()
            ax.pie(res, labels=res.index, autopct='%1.1f%%')
            st.pyplot(fig)

# --- MENU PRINCIPAL ---
st.sidebar.title(f"Olá, {st.secrets.get('user_name', 'Luis Paulo')}")
paginas = {
    "Página Inicial": pagina_inicial,
    "Adicionar Lançamento": pagina_adicionar,
    "Gerenciar Lançamento": pagina_gerenciar,
    "Relatório Mensal": pagina_relatorio,
    "Faturas de Cartão": pagina_faturas,
    "Categorias": pagina_configuracoes,
    "Gráficos": pagina_graficos
}
escolha = st.sidebar.radio("Navegue:", list(paginas.keys()))
paginas[escolha]()
