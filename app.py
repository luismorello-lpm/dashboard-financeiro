import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import os

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Meu Dashboard Financeiro",
    page_icon="📊",
    layout="wide"
)

# --- FUNÇÕES AUXILIARES (O "CÉREBRO" DO NOSSO SCRIPT ANTIGO) ---

# Define o caminho do arquivo de forma mais robusta
NOME_ARQUIVO = 'Banco de Dados.csv'
CAMINHO_ARQUIVO = os.path.join(os.path.dirname(__file__), NOME_ARQUIVO)
MAPA_MESES = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 
    7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
}


def carregar_dados(caminho_arquivo):
    """Carrega o arquivo CSV e retorna um DataFrame."""
    try:
        return pd.read_csv(caminho_arquivo, sep=';', encoding='latin-1', engine='python')
    except FileNotFoundError:
        st.error(f"ERRO: O arquivo '{caminho_arquivo}' não foi encontrado.")
        return None

def salvar_dados(df, caminho_arquivo):
    """Salva o DataFrame no arquivo CSV, sobrescrevendo o conteúdo existente."""
    try:
        # A coluna 'Valor Financeiro' é criada apenas em memória e não deve ser salva.
        df_para_salvar = df.drop(columns=['Valor Financeiro'], errors='ignore')
        df_para_salvar.to_csv(caminho_arquivo, sep=';', encoding='latin-1', index=False)
        return True
    except Exception as e:
        st.error(f"ERRO ao salvar o arquivo: {e}")
        return False

def clean_valor(valor_str):
    """Converte uma string de valor monetário para um formato numérico padrão."""
    valor_str = str(valor_str).strip()
    if ',' in valor_str:
        valor_str = valor_str.replace('.', '').replace(',', '.')
    return valor_str

# --- PÁGINAS DO STREAMLIT ---

def pagina_relatorio():
    st.title("📊 Gerador de Relatório Financeiro")
    
    df = carregar_dados(CAMINHO_ARQUIVO)
    if df is None:
        return

    # Limpeza e preparação dos dados
    df.columns = df.columns.str.strip()
    df['Valor'] = df['Valor'].astype(str).apply(clean_valor)
    df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce')
    df['Mês'] = df['Mês'].astype(str).str.strip()
    df['Ano'] = pd.to_numeric(df['Ano'], errors='coerce')
    df.dropna(subset=['Valor', 'Ano', 'Mês'], inplace=True)
    # Cria a coluna 'Valor Financeiro' em memória para os cálculos
    df['Valor Financeiro'] = np.where(df['Tipo'] == 'Despesa', -df['Valor'], df['Valor'])

    # Interface do usuário
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

    df_existente = carregar_dados(CAMINHO_ARQUIVO)
    if df_existente is None:
        st.warning("Não foi possível carregar a base de dados para adicionar um novo lançamento.")
        return
        
    proximo_id = df_existente['ID'].max() + 1 if not df_existente.empty else 1

    with st.form("novo_lancamento_form", clear_on_submit=True):
        st.subheader("Detalhes do Lançamento")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            data_lancamento = st.date_input("Data do Lançamento", datetime.now())
        with col2:
            tipo = st.selectbox("Tipo", ['Despesa', 'Receita', 'Sobra'])
        with col3:
            valor = st.number_input("Valor (R$)", min_value=0.01, format="%.2f")
        
        descricao = st.text_input("Descrição")
        
        categorias = [
            'Entrada', 'Transporte', 'Saúde', 'Cuidados Pessoais', 'Entretenimento',
            'Bar / Restaurante / Churrasco', 'Contas Fixas', 'Moradia', 'Roupas e Calçados',
            'Gastos Gerais Corrida', 'Viagens', 'Poupado / Investimento', 
            'Gastos Extras / Diversos', 'Reposição Reserva', 'Ca'
        ]
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
                meios_de_pagamento = [
                    'Vale Alimentação', 'Débito Nubank', 'Débito Santander', 'Crédito Nubank',
                    'Crédito Santander', 'Boleto', 'Crédito BTG', 'Dinheiro', 'Pix', 'Transf. BTG'
                ]
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
            
            if salvar_dados(df_atualizado, CAMINHO_ARQUIVO):
                st.success(f"{len(novos_lancamentos)} lançamento(s) adicionado(s) com sucesso!")
                st.dataframe(novos_df, hide_index=True)


def pagina_graficos():
    st.title("🎨 Gerador de Gráficos Analíticos")

    df = carregar_dados(CAMINHO_ARQUIVO)
    if df is None:
        return

    # Limpeza e preparação dos dados
    df.columns = df.columns.str.strip()
    df['Valor'] = df['Valor'].astype(str).apply(clean_valor)
    df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce')
    df['Mês'] = df['Mês'].astype(str).str.strip()
    df['Ano'] = pd.to_numeric(df['Ano'], errors='coerce')
    df.dropna(subset=['Valor', 'Ano', 'Mês'], inplace=True)

    opcoes_graficos = [
        "Selecione um tipo de gráfico...",
        "1- Gastos por Categoria (Mensal)",
        "2- Gasto com Cartão de Crédito (Mensal)",
        "3- Gastos por Classificação (Mensal)",
        "4- Gastos por Categoria (Anual)",
        "5- Balanço Receitas x Despesas x Sobras (Anual)",
        "6- Faturas de Cartão de Crédito (Anual)"
    ]
    escolha = st.selectbox("Escolha o Gráfico", opcoes_graficos)

    # --- Lógica para cada gráfico ---
    if escolha.endswith("(Mensal)"):
        col1, col2 = st.columns(2)
        with col1:
            ano = st.number_input("Ano", min_value=2020, max_value=2030, value=datetime.now().year)
        with col2:
            mes_num = st.selectbox("Mês", options=list(range(1, 13)), format_func=lambda x: MAPA_MESES[x], index=datetime.now().month - 1)
        
        if st.button("Gerar Gráfico Mensal"):
            nome_mes = MAPA_MESES.get(mes_num)
            df_filtrado = df[(df['Ano'] == ano) & (df['Mês'] == nome_mes)]
            periodo_str = f"{nome_mes}/{ano}"

            if df_filtrado.empty:
                st.warning(f"Nenhum dado encontrado para {periodo_str}.")
                return

            if escolha.startswith("1-"):
                despesas_df = df_filtrado[df_filtrado['Tipo'] == 'Despesa']
                dados_grafico = despesas_df.groupby('Categoria')['Valor'].sum()
                if not dados_grafico.empty:
                    fig, ax = plt.subplots(figsize=(10, 7))
                    ax.pie(dados_grafico, labels=dados_grafico.index, autopct=lambda pct: f"{pct:.1f}%\n(R$ {pct/100.*dados_grafico.sum():,.2f})", startangle=140)
                    ax.set_title(f'Distribuição de Despesas por Categoria - {periodo_str}')
                    st.pyplot(fig)
                else:
                    st.info(f"Nenhuma despesa encontrada em {periodo_str}.")
            
            elif escolha.startswith("2-"):
                despesas_cartao = df_filtrado[(df_filtrado['Tipo'] == 'Despesa') & (df_filtrado['Forma de Pagamento'].str.contains('Crédito', na=False))]
                dados_grafico = despesas_cartao.groupby('Forma de Pagamento')['Valor'].sum()
                if not dados_grafico.empty:
                    fig, ax = plt.subplots(figsize=(10, 6))
                    bars = ax.bar(dados_grafico.index, dados_grafico.values, color='skyblue')
                    ax.set_title(f'Gastos com Cartão de Crédito - {periodo_str}')
                    ax.set_ylabel('Valor (R$)')
                    ax.set_xlabel('Cartão')
                    ax.tick_params(axis='x', rotation=45)
                    for bar in bars:
                        yval = bar.get_height()
                        ax.text(bar.get_x() + bar.get_width()/2.0, yval, f'R$ {yval:,.2f}', va='bottom', ha='center')
                    st.pyplot(fig)
                else:
                    st.info(f"Nenhum gasto com cartão de crédito encontrado em {periodo_str}.")

            elif escolha.startswith("3-"):
                despesas_df = df_filtrado[df_filtrado['Tipo'] == 'Despesa']
                dados_grafico = despesas_df.groupby('Classificação')['Valor'].sum()
                if not dados_grafico.empty:
                    fig, ax = plt.subplots(figsize=(10, 7))
                    ax.pie(dados_grafico, labels=dados_grafico.index, autopct=lambda pct: f"{pct:.1f}%\n(R$ {pct/100.*dados_grafico.sum():,.2f})", startangle=90)
                    ax.set_title(f'Gastos por Classificação - {periodo_str}')
                    st.pyplot(fig)
                else:
                    st.info(f"Nenhuma despesa classificada encontrada em {periodo_str}.")


    elif escolha.endswith("(Anual)"):
        ano = st.number_input("Ano", min_value=2020, max_value=2030, value=datetime.now().year)
        
        if st.button("Gerar Gráfico Anual"):
            df_filtrado = df[df['Ano'] == ano]
            periodo_str = f"Ano {ano}"

            if df_filtrado.empty:
                st.warning(f"Nenhum dado encontrado para {periodo_str}.")
                return

            if escolha.startswith("4-"):
                despesas_df = df_filtrado[df_filtrado['Tipo'] == 'Despesa']
                dados_grafico = despesas_df.groupby('Categoria')['Valor'].sum()
                if not dados_grafico.empty:
                    fig, ax = plt.subplots(figsize=(12, 8))
                    ax.pie(dados_grafico, labels=dados_grafico.index, autopct=lambda pct: f"{pct:.1f}%\n(R$ {pct/100.*dados_grafico.sum():,.2f})", startangle=140)
                    ax.set_title(f'Distribuição de Despesas por Categoria - {periodo_str}')
                    st.pyplot(fig)
                else:
                    st.info(f"Nenhuma despesa encontrada em {periodo_str}.")

            elif escolha.startswith("5-"):
                receitas = df_filtrado[df_filtrado['Tipo'] == 'Receita'].groupby('Mês')['Valor'].sum()
                despesas = df_filtrado[df_filtrado['Tipo'] == 'Despesa'].groupby('Mês')['Valor'].sum()
                sobras = df_filtrado[df_filtrado['Tipo'] == 'Sobra'].groupby('Mês')['Valor'].sum()
                
                df_anual = pd.DataFrame({'Receitas': receitas, 'Despesas': despesas, 'Sobras': sobras}).fillna(0)
                df_anual = df_anual.reindex(list(MAPA_MESES.values()), fill_value=0)

                fig, ax = plt.subplots(figsize=(12, 7))
                df_anual.plot(kind='bar', stacked=False, ax=ax, color=['green', 'red', 'blue'])
                ax.set_title(f'Balanço Anual - {periodo_str}')
                ax.set_ylabel('Valor (R$)')
                ax.set_xlabel('Mês')
                ax.tick_params(axis='x', rotation=45)
                for container in ax.containers:
                    ax.bar_label(container, fmt='R$ {:,.2f}', label_type='edge')
                st.pyplot(fig)

            elif escolha.startswith("6-"):
                faturas_df = df_filtrado[(df_filtrado['Tipo'] == 'Despesa') & (df_filtrado['Forma de Pagamento'].str.contains('Crédito', na=False))]
                dados_grafico = faturas_df.pivot_table(index='Mês', columns='Forma de Pagamento', values='Valor', aggfunc='sum').fillna(0)
                
                if not dados_grafico.empty:
                    dados_grafico = dados_grafico.reindex(list(MAPA_MESES.values()), fill_value=0)
                    fig, ax = plt.subplots(figsize=(12, 7))
                    dados_grafico.plot(kind='bar', stacked=True, ax=ax)
                    ax.set_title(f'Faturas de Cartão de Crédito - {periodo_str}')
                    ax.set_ylabel('Valor (R$)')
                    ax.set_xlabel('Mês')
                    ax.tick_params(axis='x', rotation=45)
                    # Adicionar rótulos de total em barras empilhadas
                    for i, total in enumerate(dados_grafico.sum(axis=1)):
                        if total > 0:
                            ax.text(i, total, f'R$ {total:,.2f}', ha='center', va='bottom')
                    st.pyplot(fig)
                else:
                    st.info(f"Nenhum gasto com cartão de crédito encontrado em {periodo_str}.")

def pagina_gerenciar():
    st.title("🛠️ Gerenciar Lançamento")

    df = carregar_dados(CAMINHO_ARQUIVO)
    if df is None:
        return

    if 'id_gerenciar' not in st.session_state:
        st.session_state.id_gerenciar = 0

    id_input = st.number_input(
        "Digite o ID do lançamento para buscar", 
        min_value=1, 
        step=1, 
        key="id_input_widget"
    )

    if st.button("Buscar ID"):
        st.session_state.id_gerenciar = id_input
        st.rerun()

    if st.session_state.id_gerenciar > 0:
        if st.session_state.id_gerenciar in df['ID'].values:
            index_alvo = df.index[df['ID'] == st.session_state.id_gerenciar].tolist()[0]
            
            st.subheader(f"Detalhes do Lançamento ID: {st.session_state.id_gerenciar}")
            st.dataframe(df.loc[[index_alvo]], hide_index=True)

            with st.expander("✏️ Editar este lançamento"):
                colunas_editaveis = df.columns.tolist()
                if 'Valor Finaceiro' in colunas_editaveis:
                    colunas_editaveis.remove('Valor Finaceiro')
                colunas_editaveis.remove('ID')

                coluna_para_editar = st.selectbox("Qual coluna deseja editar?", colunas_editaveis, key="edit_column_select")
                
                with st.form(key=f"edit_form_{coluna_para_editar}"):
                    valor_atual = df.loc[index_alvo, coluna_para_editar]
                    
                    st.write(f"Editando a coluna: **{coluna_para_editar}**")
                    
                    novo_valor = None
                    if coluna_para_editar == 'Data':
                        try:
                            default_date = datetime.strptime(str(valor_atual), '%d/%m/%Y')
                        except (ValueError, TypeError):
                            default_date = datetime.now()
                        novo_valor = st.date_input("Novo valor", value=default_date)
                    elif coluna_para_editar == 'Valor':
                        try:
                            valor_atual_float = float(clean_valor(valor_atual))
                        except (ValueError, TypeError):
                            valor_atual_float = 0.0
                        novo_valor = st.number_input("Novo valor", value=valor_atual_float, format="%.2f")
                    else:
                        novo_valor = st.text_input("Novo valor", value=str(valor_atual))

                    edit_submitted = st.form_submit_button("Salvar Alteração")

                    if edit_submitted:
                        valor_final = novo_valor.strftime('%d/%m/%Y') if isinstance(novo_valor, (datetime, pd.Timestamp)) else novo_valor
                        df.loc[index_alvo, coluna_para_editar] = valor_final
                        if salvar_dados(df, CAMINHO_ARQUIVO):
                            st.success(f"Coluna '{coluna_para_editar}' do ID {st.session_state.id_gerenciar} atualizada!")
                            st.rerun()
                        else:
                            st.error("Falha ao salvar os dados.")

            with st.expander("🗑️ Excluir este lançamento"):
                st.warning("Esta ação é permanente e não pode ser desfeita.")
                if st.button("Confirmar Exclusão"):
                    df = df.drop(index_alvo).copy()
                    df['ID'] = range(1, len(df) + 1)
                    if salvar_dados(df, CAMINHO_ARQUIVO):
                        st.success(f"Lançamento ID {st.session_state.id_gerenciar} foi excluído.")
                        st.session_state.id_gerenciar = 0
                        st.rerun()
        else:
            st.error(f"ID {st.session_state.id_gerenciar} não encontrado. Pode ter sido excluído.")
            st.session_state.id_gerenciar = 0

def pagina_faturas():
    st.title("💳 Ver Faturas de Cartão de Crédito")

    df = carregar_dados(CAMINHO_ARQUIVO)
    if df is None:
        return
        
    cartoes = ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG']
    cartao_selecionado = st.selectbox("Selecione o Cartão de Crédito", cartoes)
    
    col1, col2 = st.columns(2)
    with col1:
        ano = st.number_input("Ano da fatura", min_value=2020, max_value=2030, value=datetime.now().year)
    with col2:
        mes_num = st.selectbox("Mês da fatura", options=list(range(1, 13)), format_func=lambda x: MAPA_MESES[x], index=datetime.now().month - 1)

    if st.button("Ver Fatura"):
        nome_mes = MAPA_MESES.get(mes_num)
        
        df['Ano'] = pd.to_numeric(df['Ano'], errors='coerce')
        df['Valor'] = df['Valor'].astype(str).apply(clean_valor)
        df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce')
        df.dropna(subset=['Valor', 'Ano', 'Mês', 'Forma de Pagamento'], inplace=True)

        fatura_df = df[
            (df['Forma de Pagamento'] == cartao_selecionado) &
            (df['Ano'] == ano) & 
            (df['Mês'] == nome_mes)
        ]

        if fatura_df.empty:
            st.warning(f"Nenhum lançamento encontrado para a fatura de {cartao_selecionado} em {nome_mes}/{ano}.")
        else:
            total_fatura = fatura_df['Valor'].sum()
            st.metric(f"Total da Fatura de {nome_mes.upper()}/{ano}", f"R$ {total_fatura:,.2f}")
            
            with st.expander("Ver detalhes da fatura"):
                colunas_para_ver = ['ID', 'Data', 'Descrição', 'Parcelas', 'Valor']
                st.dataframe(fatura_df[colunas_para_ver], hide_index=True)


# --- ESTRUTURA PRINCIPAL DO APP ---

st.sidebar.title("🏛️ Menu Principal")
paginas = {
    "Adicionar Lançamento": pagina_adicionar,
    "Gerenciar Lançamento": pagina_gerenciar,
    "Relatório Mensal": pagina_relatorio,
    "Ver Faturas de Cartão": pagina_faturas,
    "Gráficos Analíticos": pagina_graficos,
}

escolha = st.sidebar.radio("Navegue pelas páginas", list(paginas.keys()))

paginas[escolha]()
