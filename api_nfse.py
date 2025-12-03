from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import requests
from bs4 import BeautifulSoup
import re
from typing import Optional

app = FastAPI(
    title="API Extrator NFS-e",
    description="API para extração de faturamento do Portal NFS-e Nacional",
    version="1.0.0"
)

class FaturamentoRequest(BaseModel):
    cnpj: str = Field(..., description="CNPJ da empresa")
    senha: str = Field(..., description="Senha de acesso")
    ano: str = Field(..., description="Ano (ex: 2025)", pattern=r"^\d{4}$")
    mes: Optional[str] = Field(None, description="Mês (1-12, opcional)")

class FaturamentoResponse(BaseModel):
    CNPJ: str
    Faturamento: str
    Notas_Encontradas: int
    Periodo: str
    Mes: str

def fazer_login(session, cnpj, senha):
    url_login = "https://www.nfse.gov.br/EmissorNacional/Login"
    try:
        response = session.get(url_login, timeout=15)
        if response.status_code != 200:
            raise Exception("Autenticação não realizada. Favor inserir os dados corretamente de acesso")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        token_input = soup.find('input', {'name': '__RequestVerificationToken'})
        if not token_input:
            raise Exception("Autenticação não realizada. Favor inserir os dados corretamente de acesso")
        
        token = token_input.get('value')
        login_data = {
            '__RequestVerificationToken': token,
            'Inscricao': cnpj,
            'Senha': senha
        }
        
        response_login = session.post(url_login, data=login_data, timeout=15, allow_redirects=True)
        if response_login.status_code != 200:
            raise Exception("Autenticação não realizada. Favor inserir os dados corretamente de acesso")
        
        if "Login" in response_login.url or "login" in response_login.url.lower():
            raise Exception("Autenticação não realizada. Favor inserir os dados corretamente de acesso")
    except:
        raise Exception("Autenticação não realizada. Favor inserir os dados corretamente de acesso")

def processar_pagina(soup, ano_filtro, mes_filtro):
    faturamento_pagina = 0.0
    notas_na_pagina = 0
    continuar = True
    
    tbody = soup.find('tbody')
    if not tbody:
        return 0.0, 0, False
    
    linhas = tbody.find_all('tr')
    if not linhas:
        return 0.0, 0, False
    
    for linha in linhas:
        try:
            img_gerada = linha.find('img', src='/EmissorNacional/img/tb-gerada.svg')
            if not img_gerada:
                continue
            
            td_competencia = linha.find('td', class_='td-competencia')
            if not td_competencia:
                continue
            
            competencia_texto = td_competencia.get_text(strip=True)
            match = re.search(r'(\d{2})/(\d{4})', competencia_texto)
            if not match:
                continue
            
            mes_nota = match.group(1)
            ano_nota = match.group(2)
            
            if int(ano_nota) < int(ano_filtro):
                continuar = False
                break
            
            if int(ano_nota) > int(ano_filtro):
                continue
            
            if mes_filtro and mes_nota != mes_filtro:
                continue
            
            td_valor = linha.find('td', class_='td-valor')
            if not td_valor:
                continue
            
            valor_texto = td_valor.get_text(strip=True)
            valor_limpo = valor_texto.replace('.', '').replace(',', '.')
            valor = float(valor_limpo)
            
            faturamento_pagina += valor
            notas_na_pagina += 1
        except:
            continue
    
    return faturamento_pagina, notas_na_pagina, continuar

def buscar_notas(session, ano, mes):
    faturamento_total = 0.0
    notas_processadas = 0
    pagina = 1
    continuar = True
    url_base = "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas"
    
    while continuar:
        url = url_base if pagina == 1 else f"{url_base}?pg={pagina}"
        response = session.get(url, timeout=15)
        if response.status_code != 200:
            break
        
        soup = BeautifulSoup(response.text, 'html.parser')
        faturamento_pagina, notas_pagina, continuar = processar_pagina(soup, ano, mes)
        
        faturamento_total += faturamento_pagina
        notas_processadas += notas_pagina
        
        if not continuar:
            break
        
        paginacao = soup.find('div', class_='paginacao')
        if not paginacao:
            break
        
        link_proxima = paginacao.find('a', title='Próxima')
        if not link_proxima or 'javascript:' in link_proxima.get('href', ''):
            break
        
        pagina += 1
    
    return faturamento_total, notas_processadas

@app.get("/")
def read_root():
    return {"status": "ok", "message": "API Extrator NFS-e online", "docs": "/docs"}

@app.post("/api/faturamento", response_model=FaturamentoResponse)
def obter_faturamento(request: FaturamentoRequest):
    try:
        mes_filtro = None
        if request.mes:
            mes_int = int(request.mes)
            if mes_int < 1 or mes_int > 12:
                raise HTTPException(status_code=400, detail="Mês inválido")
            mes_filtro = str(mes_int).zfill(2)
        
        cnpj_limpo = re.sub(r'\D', '', request.cnpj)
        if len(cnpj_limpo) == 14:
            cnpj_formatado = f"{cnpj_limpo[:2]}.{cnpj_limpo[2:5]}.{cnpj_limpo[5:8]}/{cnpj_limpo[8:12]}-{cnpj_limpo[12:]}"
        else:
            cnpj_formatado = request.cnpj
        
        periodo = f"{mes_filtro}/{request.ano}" if mes_filtro else request.ano
        mes_label = mes_filtro if mes_filtro else "Ano todo"
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        })
        
        fazer_login(session, request.cnpj, request.senha)
        faturamento, quantidade = buscar_notas(session, request.ano, mes_filtro)
        
        return FaturamentoResponse(
            CNPJ=cnpj_formatado,
            Faturamento=round(faturamento,2),
            Notas_Encontradas=quantidade,
            Periodo=periodo,
            Mes=mes_label
        )
    except Exception as e:
        if "Autenticação não realizada" in str(e):
            raise HTTPException(status_code=401, detail=str(e))
        raise HTTPException(status_code=500, detail=f"Erro: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
