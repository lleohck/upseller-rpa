# UpSeller RPA

Automacao web com Python + Playwright para operar variantes no painel da UpSeller.

## 1) Setup local (.venv)

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/mac
# .venv\\Scripts\\activate  # Windows
pip install -r requirements.txt
python -m playwright install chromium
```

## 2) Configuracao

1. Copie `.env.example` para `.env`.
2. Preencha as variaveis necessarias (`UPSELLER_DRAFT_URL`, `UPSELLER_VARIANT_NAME`, `UPSELLER_OPTION_NAMES`, etc.).
   - Se quiser pular criacao da variante e ir direto para opcoes: `UPSELLER_SKIP_VARIANT_CREATION=true`.
   - Se quiser preencher descricao automaticamente por opcao, defina `UPSELLER_OPTION_DESCRIPTION_TEMPLATE` com `{{OPTION_NAME}}` (ex.: `Descricao da opcao {{OPTION_NAME}} xxxxxxxx`).
   - Se quiser aplicar o mesmo preco para todas as opcoes, defina `UPSELLER_OPTION_PRICE_BRL` (ex.: `99,90`).
   - Se quiser copiar imagem da variacao para todas as variantes no card Midia, defina `UPSELLER_APPLY_VARIANT_IMAGES=true` (use junto com `UPSELLER_SKIP_VARIANT_CREATION=true`).
3. Garanta que `storage_state.json` esteja valido.

## 3) Interface visual (Fase 2)

### Linux/mac

```bash
./run_ui.sh
```

### Windows

```bat
run_ui.bat
```

O launcher detecta ambiente ativo; se nao houver, tenta usar `.venv` local.

Na UI, use a secao **Renovar Sessao (Login Assistido)**:
1. Informe URL de login.
2. Clique em `Abrir navegador para login manual`.
3. Conclua o login/CAPTCHA/confirmacoes manualmente no navegador.
4. Clique em `OK, salvar sessão` para gravar `storage_state.json`.

Na execucao da automacao de variantes, use `Cancelar automação e fechar janela` para interromper e fechar o navegador.

## 4) CLI de automacao

```bash
python variant.py
```

## 5) Renovacao de sessao

```bash
python login.py
python session.py
```

## 6) Build de executavel Windows (sem Python no destino)

```bat
build_windows_exe.bat
```

Se der erro e a janela fechar, rode pelo `cmd`:

```bat
build_windows_exe.bat
```

O script gera log em `build_windows_exe.log` com o detalhe do erro.

Saida esperada: pasta `dist\\upseller-rpa-ui\\`

Conteudo principal da pasta final:
- `upseller-rpa-ui.exe`
- `start.bat`
- `.env.example`
- `ms-playwright\\` (browser embutido)

### Publicacao para outro PC Windows

1. Compacte a pasta `dist\\upseller-rpa-ui\\` em `.zip`.
2. Copie para o computador final.
3. Extraia em uma pasta simples (ex.: `C:\\UpSellerRPA\\`).
4. Edite o `.env` (se nao existir, o `start.bat` cria a partir do `.env.example` na primeira execucao).
5. Execute `start.bat`.

Observacoes:
- O computador destino nao precisa de Python/IDE.
- Mantenha toda a pasta junta; nao execute apenas o `.exe` isolado.
- Se abrir `localhost:3000` em branco, refaca o build com a versao mais recente deste projeto e use `start.bat`.
- O `start.bat` abre automaticamente `http://127.0.0.1:8501`.
- No Windows, o salvamento de sessao usa worker separado para evitar erro de `asyncio` no Streamlit.
