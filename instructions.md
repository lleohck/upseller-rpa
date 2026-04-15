# Instruções - Instalar e Rodar no Windows (via Python)

## 1) Pré-requisito
- Instale **Python 3.12+** no Windows.
- Durante a instalação, marque **Add Python to PATH**.

## 2) Abrir projeto no terminal
No **Prompt de Comando (cmd)**:

```bat
cd C:\caminho\upseller-rpa
```

## 3) Criar e ativar ambiente virtual
```bat
python -m venv .venv
.venv\Scripts\activate
```

## 4) Instalar dependências
```bat
pip install --upgrade pip
pip install -r requirements.txt
```

## 5) Instalar navegador do Playwright
```bat
python -m playwright install chromium
```

## 6) Criar arquivo de configuração
```bat
copy .env.example .env
```

## 7) Configurar variáveis no `.env`
Preencha pelo menos:
- `UPSELLER_LOGIN_URL`
- `UPSELLER_DRAFT_URL`
- `STORAGE_STATE_PATH` (ex.: `storage_state.json`)

Se a página tiver campo **Local**:
- `UPSELLER_HAS_LOCAL_FIELD=true`

## 8) Iniciar a aplicação
```bat
python run_ui.py
```

Alternativa:
```bat
run_ui.bat
```

## 9) Abrir no navegador
- `http://127.0.0.1:8501`

## 10) Fluxo recomendado
1. Na UI, use **Renovar Sessão (Login Manual)** para gerar/atualizar `storage_state.json`.
2. Preencha os campos da automação.
3. Clique em **Executar RPA**.
