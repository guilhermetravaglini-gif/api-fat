#!/usr/bin/env python
# coding: utf-8

# In[1]:


import requests
from bs4 import BeautifulSoup
import json
import re

def validar_entrada():
    """Valida e coleta as entradas do usuário"""
    while True:
        cnpj = input("Digite o CNPJ: ").strip()
        if not cnpj:
            print("❌ ERRO: CNPJ é obrigatório!")
            continue
        
        senha = input("Digite a senha: ").strip()
        if not senha:
            print("❌ ERRO: Senha é obrigatória!")
            continue
        
        ano = input("Digite o ano (ex: 2025): ").strip()
        if not ano or not ano.isdigit() or len(ano) != 4:
            print("❌ ERRO: Ano é obrigatório e deve ter 4 dígitos!")
            continue
        
        mes = input("Digite o mês (1-12) ou deixe em branco para o ano todo: ").strip()
        
        # Se o mês foi informado, valida
        if mes:
            if not mes.isdigit() or int(mes) < 1 or int(mes) > 12:
                print("❌ ERRO: Mês inválido! Digite um número entre 1 e 12.")
                continue
            # Formata o mês com 2 dígitos (ex: 3 -> 03)
            mes = str(int(mes)).zfill(2)
        
        return cnpj, senha, ano, mes

def fazer_login(session, cnpj, senha):
    """Realiza o login no portal NFS-e"""
    print("\n🔐 Fazendo login...")
    
    url_login = "https://www.nfse.gov.br/EmissorNacional/Login"
    
    try:
        # 1. Acessa a página de login para pegar o token CSRF
        response = session.get(url_login, timeout=15)
        
        if response.status_code != 200:
            raise Exception("Autenticação não realizada. Favor inserir os dados corretamente de acesso")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 2. Extrai o token CSRF
        token_input = soup.find('input', {'name': '__RequestVerificationToken'})
        if not token_input:
            raise Exception("Autenticação não realizada. Favor inserir os dados corretamente de acesso")
        
        token = token_input.get('value')
        
        # 3. Prepara os dados de login
        login_data = {
            '__RequestVerificationToken': token,
            'Inscricao': cnpj,
            'Senha': senha
        }
        
        # 4. Faz o POST de login
        response_login = session.post(url_login, data=login_data, timeout=15, allow_redirects=True)
        
        if response_login.status_code != 200:
            raise Exception("Autenticação não realizada. Favor inserir os dados corretamente de acesso")
        
        # 5. Verifica se o login foi bem-sucedido
        if "Login" in response_login.url or "login" in response_login.url.lower():
            raise Exception("Autenticação não realizada. Favor inserir os dados corretamente de acesso")
        
        print("✅ Login realizado com sucesso!")
        
    except requests.exceptions.Timeout:
        raise Exception("Autenticação não realizada. Favor inserir os dados corretamente de acesso")
    except requests.exceptions.RequestException:
        raise Exception("Autenticação não realizada. Favor inserir os dados corretamente de acesso")
    except Exception as e:
        # Se a exceção já tem a mensagem padrão, repassa
        if "Autenticação não realizada" in str(e):
            raise
        # Caso contrário, padroniza
        raise Exception("Autenticação não realizada. Favor inserir os dados corretamente de acesso")

def processar_pagina(soup, ano_filtro, mes_filtro):
    """Processa uma página de notas e retorna faturamento, quantidade e se deve continuar"""
    faturamento_pagina = 0.0
    notas_na_pagina = 0
    continuar = True
    
    # Encontra o tbody
    tbody = soup.find('tbody')
    if not tbody:
        return 0.0, 0, False
    
    # Encontra todas as linhas
    linhas = tbody.find_all('tr')
    
    if not linhas:
        return 0.0, 0, False
    
    for linha in linhas:
        try:
            # Verifica se tem a imagem de nota emitida (tb-gerada.svg)
            img_gerada = linha.find('img', src='/EmissorNacional/img/tb-gerada.svg')
            if not img_gerada:
                continue
            
            # Extrai a competência
            td_competencia = linha.find('td', class_='td-competencia')
            if not td_competencia:
                continue
            
            competencia_texto = td_competencia.get_text(strip=True)  # Ex: "10/2025"
            
            # Extrai mês e ano
            match = re.search(r'(\d{2})/(\d{4})', competencia_texto)
            if not match:
                continue
            
            mes_nota = match.group(1)
            ano_nota = match.group(2)
            
            # Se encontrou um ano menor que o solicitado, para a busca
            if int(ano_nota) < int(ano_filtro):
                print(f"✋ Encontrou competência {competencia_texto} (ano {ano_nota}), parando busca.")
                continuar = False
                break
            
            # Se o ano é maior que o solicitado, pula
            if int(ano_nota) > int(ano_filtro):
                continue
            
            # Se chegou aqui, o ano é igual ao solicitado
            # Verifica se deve filtrar por mês
            if mes_filtro and mes_nota != mes_filtro:
                continue
            
            # Extrai o valor
            td_valor = linha.find('td', class_='td-valor')
            if not td_valor:
                continue
            
            valor_texto = td_valor.get_text(strip=True)  # Ex: "51,60" ou "4.333,97"
            
            # Converte para float
            valor_limpo = valor_texto.replace('.', '').replace(',', '.')
            valor = float(valor_limpo)
            
            faturamento_pagina += valor
            notas_na_pagina += 1
            
        except Exception as e:
            print(f"⚠️  Erro ao processar linha: {e}")
            continue
    
    return faturamento_pagina, notas_na_pagina, continuar

def buscar_notas(session, ano, mes):
    """Busca e processa todas as notas fiscais"""
    print(f"\n🔍 Buscando notas fiscais...")
    
    faturamento_total = 0.0
    notas_processadas = 0
    pagina = 1
    continuar = True
    
    url_base = "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas"
    
    while continuar:
        print(f"📄 Processando página {pagina}...")
        
        # Monta a URL da página
        if pagina == 1:
            url = url_base
        else:
            url = f"{url_base}?pg={pagina}"
        
        # Faz a requisição
        response = session.get(url, timeout=15)
        
        if response.status_code != 200:
            print(f"⚠️  Erro ao acessar página {pagina}. Status: {response.status_code}")
            break
        
        # Parseia o HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Processa a página
        faturamento_pagina, notas_pagina, continuar = processar_pagina(soup, ano, mes)
        
        faturamento_total += faturamento_pagina
        notas_processadas += notas_pagina
        
        print(f"   ✓ {notas_pagina} notas válidas encontradas nesta página")
        
        if not continuar:
            break
        
        # Verifica se há próxima página
        paginacao = soup.find('div', class_='paginacao')
        if not paginacao:
            break
        
        # Procura pelo link "Próxima"
        link_proxima = paginacao.find('a', title='Próxima')
        if not link_proxima or 'javascript:' in link_proxima.get('href', ''):
            break
        
        pagina += 1
    
    print(f"\n✅ Total de notas processadas: {notas_processadas}")
    
    return faturamento_total, notas_processadas

def main():
    print("=" * 70)
    print("🚀 EXTRATOR DE FATURAMENTO - PORTAL NFS-E NACIONAL (REQUESTS)")
    print("=" * 70)
    print()
    
    # Valida e coleta entradas
    cnpj, senha, ano, mes = validar_entrada()
    
    # Formata o CNPJ para o padrão XX.XXX.XXX/XXXX-XX
    cnpj_limpo = re.sub(r'\D', '', cnpj)  # Remove tudo que não é dígito
    if len(cnpj_limpo) == 14:
        cnpj_formatado = f"{cnpj_limpo[:2]}.{cnpj_limpo[2:5]}.{cnpj_limpo[5:8]}/{cnpj_limpo[8:12]}-{cnpj_limpo[12:]}"
    else:
        cnpj_formatado = cnpj
    
    # Define o período para exibição
    if mes:
        periodo = f"{mes}/{ano}"
        mes_label = mes
    else:
        periodo = ano
        mes_label = "Ano todo"
    
    print(f"\n📊 Buscando dados para: {periodo}")
    print(f"📋 CNPJ: {cnpj_formatado}")
    print("-" * 70)
    
    # Cria sessão
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    })
    
    try:
        # Faz login
        fazer_login(session, cnpj, senha)
        
        # Busca as notas
        faturamento, quantidade_notas = buscar_notas(session, ano, mes)
        
        # Monta o resultado
        resultado = {
            "CNPJ": cnpj_formatado,
            "Faturamento": f"R$ {faturamento:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'),
            "Notas_Encontradas": quantidade_notas,
            "Periodo": periodo,
            "Mes": mes_label
        }
        
        # Exibe o resultado
        print("\n" + "=" * 70)
        print("📈 RESULTADO")
        print("=" * 70)
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
        print("=" * 70)
        
        # Salva em arquivo
        nome_arquivo = f'faturamento_{cnpj_limpo}_{periodo.replace("/", "-")}.json'
        with open(nome_arquivo, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Resultado salvo em: {nome_arquivo}")
        
    except Exception as e:
        print(f"\n❌ ERRO: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())

