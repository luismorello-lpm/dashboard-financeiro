import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe
import os

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Meu Dashboard Financeiro",
    page_icon="📊",
    layout="wide"
)

# --- CONFIGURAÇÃO DA CONEXÃO COM O GOOGLE SHEETS ---
NOME_DA_PLANILHA = "DashboardFinanceiroDB" # <-- VERIFIQUE SE ESTE NOME ESTÁ CORRETO
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Função para conectar ao Google Sheets usando os segredos do Streamlit
@st.cache_resource
def connect_to_gsheet():
    try:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=SCOPES
        )
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

@st.cache_data(ttl=60) # Cache de 1 minuto para os dados
def carregar_dados():
    """Carrega os dados da planilha do Google Sheets e retorna um DataFrame."""
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            worksheet = spreadsheet.sheet1 # Acessa a primeira página
            df = pd.DataFrame(worksheet.get_all_records())
            # Garante que colunas importantes sejam do tipo correto
            for col in ['ID', 'Ano', 'Valor']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce')
            return df
        except Exception as e:
            st.error(f"Erro ao carregar os dados da planilha: {e}")
            return pd.DataFrame() # Retorna um DataFrame vazio em caso de erro
    return pd.DataFrame()

def salvar_dados(df):
    """Salva o DataFrame na planilha do Google Sheets, sobrescrevendo o conteúdo."""
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            worksheet = spreadsheet.sheet1
            # A coluna 'Valor Financeiro' é criada apenas em memória e não deve ser salva.
            df_para_salvar = df.drop(columns=['Valor Financeiro'], errors='ignore')
            worksheet.clear()
            set_with_dataframe(worksheet, df_para_salvar, include_index=False, include_column_header=True, resize=True)
            st.cache_data.clear() # Limpa o cache para forçar a releitura dos dados
            return True
        except Exception as e:
            st.error(f"ERRO ao salvar os dados na planilha: {e}")
            return False
    return False

def clean_valor(valor_str):
    """Converte uma string de valor monetário para um formato numérico padrão."""
    valor_str = str(valor_str).strip()
    if ',' in valor_str:
        valor_str = valor_str.replace('.', '').replace(',', '.')
    return valor_str

# --- PÁGINAS DO STREAMLIT ---
# (As funções das páginas foram adaptadas para usar as novas funções de carregar/salvar)

def pagina_relatorio():
    st.title("📊 Gerador de Relatório Financeiro")
    
    df = carregar_dados()
    if df.empty:
        st.warning("Não foi possível carregar os dados ou a base de dados está vazia.")
        return

    # A conversão de tipo já é feita em carregar_dados, mas garantimos aqui
    df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce')
    df['Ano'] = pd.to_numeric(df['Ano'], errors='coerce')
    df.dropna(subset=['Valor', 'Ano', 'Mês'], inplace=True)
    df['Valor Financeiro'] = np.where(df['Tipo'] == 'Despesa', -df['Valor'], df['Valor'])

    # ... (Restante da função de relatório, sem alterações)
    col1, col2 = st.columns(2)
    with col1:
        ano = st.number_input("Selecione o Ano", min_value=2020, max_value=2030, value=datetime.now().year)
    with col2:
        mes_num = st.selectbox("Selecione o Mês", options=list(range(1, 13)), format_func=lambda x: MAPA_MESES[x], index=datetime.now().month - 1)
    
    if st.button("Gerar Relatório"):
        nome_mes = MAPA_MESES.get(mes_num)
        df_mes = df[(df['Ano'] == ano) & (df['Mês'] == nome_mes)].copy()

        if df_mes.empty:
            st.warning(f"Nenhum dado encontrado para {nome_mes}/{ano}.")
            return

        receitas = df_mes[df_mes['Valor Financeiro'] > 0]['Valor Financeiro'].sum()
        despesas = df_mes[df_mes['Valor Financeiro'] < 0]['Valor Financeiro'].sum()
        saldo = receitas + despesas

        st.subheader(f"Resumo para {nome_mes.upper()}/{ano}")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("🟢 Receitas Totais", f"R$ {receitas:,.2f}")
        col2.metric("🔴 Despesas Totais", f"R$ {despesas:,.2f}")
        col3.metric("💰 Saldo do Mês", f"R$ {saldo:,.2f}")

        st.subheader("Detalhamento de Despesas por Categoria")
        despesas_por_categoria = df_mes[df_mes['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum().sort_values(ascending=False)
        
        if not despesas_por_categoria.empty:
            st.dataframe(despesas_por_categoria.map("R$ {:,.2f}".format))
        else:
            st.info("Nenhuma despesa registrada para este mês.")
        
        with st.expander("Ver todos os lançamentos do mês"):
            colunas_para_ver = ['ID', 'Data', 'Tipo', 'Descrição', 'Categoria', 'Valor', 'Forma de Pagamento']
            st.dataframe(df_mes[colunas_para_ver], hide_index=True)

def pagina_adicionar():
    st.title("✍️ Adicionar Novo Lançamento")

    df_existente = carregar_dados()
    if df_existente is None:
        st.warning("Não foi possível carregar a base de dados.")
        return
        
    proximo_id = int(df_existente['ID'].max() + 1) if not df_existente.empty else 1

    with st.form("novo_lancamento_form"):
        # ... (O formulário continua igual)
        st.subheader("Detalhes do Lançamento")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            data_lancamento = st.date_input("Data do Lançamento", datetime.now())
        with col2:
            tipo = st.selectbox("Tipo", ['Despesa', 'Receita', 'Sobra'])
        with col3:
            valor = st.number_input("Valor (R$)", min_value=0.01, format="%.2f")
        
        descricao = st.text_input("Descrição")
        
        categorias = df_existente['Categoria'].dropna().unique().tolist()
        categoria = st.selectbox("Categoria", categorias)
        
        mes_contabil = None
        ano_contabil = None

        if tipo == 'Despesa':
            st.subheader("Detalhes da Despesa")
            col1, col2 = st.columns(2)
            with col1:
                classificacao = st.selectbox("Classificação", ['Essencial', 'Não Essencial', 'Extra'])
                pagamento = st.selectbox("Forma de Pagamento", ['À Vista', 'Parcelado'])
            with col2:
                meios_de_pagamento = df_existente['Forma de Pagamento'].dropna().unique().tolist()
                forma_pagamento = st.selectbox("Método de Pagamento", meios_de_pagamento)
                pagamento_realizado = st.selectbox("Já foi pago?", ['Sim', 'Não'])

            observacoes = st.text_area("Observações", "-")
            
            if pagamento == 'À Vista':
                st.subheader("Mês/Ano Contábil")
                col1, col2 = st.columns(2)
                with col1:
                    mes_contabil = st.number_input("Mês Contábil", min_value=1, max_value=12, value=datetime.now().month, step=1)
                with col2:
                    ano_contabil = st.number_input("Ano Contábil", min_value=2020, value=datetime.now().year, step=1)
            else: # Parcelado
                st.subheader("Detalhes do Parcelamento")
                col1, col2, col3 = st.columns(3)
                with col1:
                    total_parcelas = st.number_input("Número total de parcelas", min_value=2, value=2, step=1)
                with col2:
                    mes_inicial_parcela = st.number_input("Mês da 1ª parcela", min_value=1, max_value=12, value=datetime.now().month, step=1)
                with col3:
                    ano_inicial_parcela = st.number_input("Ano da 1ª parcela", min_value=2020, value=datetime.now().year, step=1)
        else: # Receita ou Sobra
            st.subheader("Mês/Ano Contábil")
            col1, col2 = st.columns(2)
            with col1:
                mes_contabil = st.number_input("Mês Contábil", min_value=1, max_value=12, value=datetime.now().month, step=1)
            with col2:
                ano_contabil = st.number_input("Ano Contábil", min_value=2020, value=datetime.now().year, step=1)
        
        submitted = st.form_submit_button("Adicionar Lançamento")

        if submitted:
            # ... (Lógica de adicionar lançamento permanece a mesma, mas usa o novo salvar_dados)
            novos_lancamentos = []
            
            if tipo in ['Receita', 'Sobra']:
                lancamento = {
                    'ID': proximo_id, 'Data': data_lancamento.strftime('%d/%m/%Y'), 'Tipo': tipo,
                    'Descrição': descricao, 'Valor': valor, 'Categoria': categoria,
                    'Classificação': 'N/A', 'Pagamento': 'N/A', 'Forma de Pagamento': 'N/A',
                    'Parcelas': 'N/A', 'Pagamento Realizado': 'OK', 'Observações': '-',
                    'Mês': MAPA_MESES[mes_contabil], 'Ano': ano_contabil
                }
                novos_lancamentos.append(lancamento)
            else: # Se for Despesa
                pagamento_realizado_str = 'OK' if pagamento_realizado == 'Sim' else 'NOK'
                if pagamento == 'À Vista':
                    lancamento = {
                        'ID': proximo_id, 'Data': data_lancamento.strftime('%d/%m/%Y'), 'Tipo': tipo,
                        'Descrição': descricao, 'Valor': valor, 'Categoria': categoria,
                        'Classificação': classificacao, 'Pagamento': pagamento, 'Forma de Pagamento': forma_pagamento,
                        'Parcelas': 'N/A', 'Pagamento Realizado': pagamento_realizado_str, 'Observações': observacoes,
                        'Mês': MAPA_MESES[mes_contabil], 'Ano': ano_contabil
                    }
                    novos_lancamentos.append(lancamento)
                else: # Se for Parcelado
                    for i in range(total_parcelas):
                        mes_atual = mes_inicial_parcela + i
                        ano_atual = ano_inicial_parcela
                        
                        while mes_atual > 12:
                            mes_atual -= 12
                            ano_atual += 1
                        
                        lancamento = {
                            'ID': proximo_id + i, 'Data': data_lancamento.strftime('%d/%m/%Y'), 'Tipo': tipo,
                            'Descrição': f"{descricao} ({i+1}/{total_parcelas})", 'Valor': valor / total_parcelas, 'Categoria': categoria,
                            'Classificação': classificacao, 'Pagamento': pagamento, 'Forma de Pagamento': forma_pagamento,
                            'Parcelas': f"{i+1:02d} de {total_parcelas:02d}", 
                            'Pagamento Realizado': pagamento_realizado_str, 'Observações': observacoes,
                            'Mês': MAPA_MESES[mes_atual], 'Ano': ano_atual
                        }
                        novos_lancamentos.append(lancamento)

            novos_df = pd.DataFrame(novos_lancamentos)
            df_atualizado = pd.concat([df_existente, novos_df], ignore_index=True)
            
            if salvar_dados(df_atualizado):
                st.success(f"{len(novos_lancamentos)} lançamento(s) adicionado(s) com sucesso!")
                st.dataframe(novos_df, hide_index=True)
                st.rerun()

# --- ESTRUTURA PRINCIPAL DO APP ---
# (As outras páginas, como gráficos e gerenciar, também precisam ser adaptadas)

st.sidebar.title("🏛️ Menu Principal")
paginas = {
    "Adicionar Lançamento": pagina_adicionar,
    "Relatório Mensal": pagina_relatorio,
    # "Gráficos Analíticos": pagina_graficos,
    # "Gerenciar Lançamento": pagina_gerenciar,
    # "Ver Faturas de Cartão": pagina_faturas,
}

escolha = st.sidebar.radio("Navegue pelas páginas", list(paginas.keys()))

paginas[escolha]()
