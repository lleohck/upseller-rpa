# README_AGENT

## Visão geral

Este repositório contém uma automação Python/Playwright para operar variantes no painel da UpSeller. O principal fluxo suporta:
- geração/atualização de sessão via `storage_state.json`
- criação de variantes e opções no painel
- aplicação automática de descrições, preços e mídias
- interface visual local via Streamlit

## Estrutura principal do repositório

Arquivos e pastas mais importantes:

- `README.md` - guia de instalação e uso principal.
- `instructions.md` - instruções de instalação e execução para Windows.
- `.env.example` - modelo de variáveis de ambiente usadas pelos scripts.
- `requirements.txt` - dependências Python.
- `run_ui.py` - launcher da interface Streamlit.
- `ui_app.py` - aplicação Streamlit que controla o fluxo e mostra resultados.
- `variant.py` - CLI principal para executar a automação de variantes.
- `login.py` - script de login automático e geração de `storage_state.json`.
- `session.py` - valida e atualiza sessão existente usando `storage_state.json`.
- `rpa/variant_runner.py` - motor central que executa a automação de variantes.
- `login_manual_worker.py` - worker para abrir navegador e permitir login manual.
- `extract_storage_state.py` - extrai `storage_state.json` usando Chrome CDP.
- `save_storage_state_worker.py` - worker auxiliar para salvar estado de sessão via CDP.
- `variant_job_worker.py` - worker que executa jobs de variante por request/result JSON.

## Instalação e uso

### 1) Criar ambiente Python

No terminal do Windows:

```bat
cd c:\Users\diego\Projects\upseller-rpa
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
```

### 2) Configurar `.env`

Copie:

```bat
copy .env.example .env
```

Edite `.env` e defina pelo menos:

- `UPSELLER_BASE_URL`
- `UPSELLER_LOGIN_URL`
- `UPSELLER_DRAFT_URL`
- `STORAGE_STATE_PATH`
- `UPSELLER_USERNAME`
- `UPSELLER_PASSWORD`

Campos de automação úteis:

- `UPSELLER_VARIANT_NAME`
- `UPSELLER_OPTION_NAMES`
- `UPSELLER_OPTION_DESCRIPTION_TEMPLATE`
- `UPSELLER_HAS_LOCAL_FIELD`
- `UPSELLER_OPTION_PRICE_BRL`
- `UPSELLER_APPLY_VARIANT_IMAGES`
- `UPSELLER_AUTH_SUCCESS_SELECTOR`
- `UPSELLER_CAPTCHA_SELECTORS`
- `UPSELLER_POST_LOGIN_BLOCKING_SELECTORS`
- `UPSELLER_POST_LOGIN_BLOCKING_URL_KEYWORDS`

### 3) Gerar/atualizar sessão

Preferência de uso do repositório:

- `python login.py` — login automático com credenciais e salva `storage_state.json`
- `python session.py` — valida e atualiza sessão existente usando `storage_state.json`
- `python login_manual_worker.py --login-url <LOGIN_URL> --cdp-port 9222 --maximize` — abre navegador para login manual, útil para CAPTCHA ou confirmação adicional
- `python extract_storage_state.py` — exporta `storage_state.json` a partir de uma sessão de Chrome com CDP ativa

### 4) Executar a UI

```bat
python run_ui.py
```

Ou use o atalho:

```bat
run_ui.bat
```

A interface fica em:

- `http://127.0.0.1:8501`

Fluxo recomendado:

1. Use a opção de renovação de sessão/login assistido.
2. Preencha parâmetros de variante/opções.
3. Execute a automação.

### 5) Executar a automação diretamente

```bat
python variant.py
```

Isso usa as variáveis carregadas de `.env`.

## Inventário para agentes LLM

### Objetivo principal

- criar variantes e opções na UpSeller
- aplicar descrições automáticas
- aplicar preços para opções
- copiar mídia de variantes, se configurado

### Papéis dos principais scripts

- `login.py`: login automático via seletores configuráveis e salva `storage_state.json`
- `session.py`: valida e atualiza a sessão salva para evitar re-login
- `variant.py`: executa o job principal de automação de variantes
- `ui_app.py`/`run_ui.py`: interface visual que permite rodar e monitorar a execução
- `rpa/variant_runner.py`: lógica de navegação/edição do painel UpSeller
- `login_manual_worker.py`: serve para login manual em um navegador real
- `extract_storage_state.py`: cria `storage_state.json` via conexão CDP com Chrome
- `variant_job_worker.py`: wrapper worker para executar jobs de variantes por JSON

### Como agentes devem agir

1. Verificar `README.md` e `instructions.md` para contexto e instalação
2. Confirmar dependências em `requirements.txt`
3. Checar/ou usar `.env.example` para montar `.env`
4. Gerar e validar sessão via `login.py` ou `session.py`
5. Executar `variant.py` para teste de automação principal
6. Usar `artifacts/` para checar screenshots e logs quando houver erro
7. Ajustar seletores e variáveis de ambiente se o login ou a interface UpSeller mudar

## Notas adicionais

- `storage_state.json` é o arquivo crítico de sessão; sem ele, o bot não consegue usar a sessão salva.
- O sistema tenta login automático, mas há suporte manual para CAPTCHA e etapas de verificação adicionais.
- Os seletores no código são genéricos e podem precisar de refinamento para estabilidade.

## Tags de interesse para agentes

- `setup` — instalação do ambiente
- `config` — `.env` e variáveis de ambiente
- `login` — scripts de autenticação e sessão
- `variant` — automação de variantes
- `ui` — interface Streamlit
- `cdp` — extração de estado/Chrome DevTools
- `worker` — execução via request/result JSON

## Comandos úteis

```bat
python login.py
python session.py
python variant.py
python run_ui.py
python login_manual_worker.py --login-url https://app.upseller.com/login --cdp-port 9222 --maximize
python extract_storage_state.py
```

Fim do README_AGENT.
