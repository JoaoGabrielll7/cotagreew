# Sistema de Cotacao Greew

Site completo de cotacao de frete com:

- login master e cadastro de usuarios operadores
- calculo por cubagem, peso e NF
- medias simples e ponderada
- sugestao comercial (cheio, justo, desconto maximo)
- mensagem pronta para cliente
- historico de cotacoes por usuario
- backend preparado para Neon Postgres + deploy na Vercel

## Stack

- Backend: Flask
- Banco: PostgreSQL (Neon)
- Deploy: Vercel (Python serverless)
- Motor de cotacao: `src/greew_quote/engine.py`

## Estrutura

- `api/index.py`: entrada serverless da Vercel
- `vercel.json`: roteamento do deploy
- `site_app.py`: execucao local do site Flask
- `web/templates/*`: paginas HTML
- `web/static/site.css`: estilo do site
- `src/greew_quote/flask_site.py`: backend web (auth, rotas, persistencia)
- `src/greew_quote/engine.py`: regras de cotacao
- `streamlit_app.py`: interface Streamlit (opcional)
- `main.py`: CLI (opcional)

## Requisitos

- Python 3.10+
- pip
- banco Neon com `DATABASE_URL`

## Instalar dependencias

```bash
pip install -r requirements.txt
```

## Variaveis de ambiente

Obrigatoria:

- `DATABASE_URL`: string de conexao Postgres do Neon

Recomendadas:

- `GREEW_SECRET_KEY`: chave de sessao do Flask
- `GREEW_MASTER_USER`: login master (padrao `master`)
- `GREEW_MASTER_PASSWORD`: senha master (padrao `Master@123`)
- `GREEW_MASTER_NAME`: nome exibido do master (padrao `Master`)

Exemplo pronto: `.env.example`

## Rodar localmente (site completo)

```bash
python site_app.py
```

Acesse `http://localhost:5000`.

## Deploy na Vercel

1. Suba este projeto no GitHub.
2. Importe o repo na Vercel.
3. Configure as env vars no projeto da Vercel:
   - `DATABASE_URL`
   - `GREEW_SECRET_KEY`
   - `GREEW_MASTER_USER`
   - `GREEW_MASTER_PASSWORD`
   - `GREEW_MASTER_NAME`
4. Faca o deploy.

## Acesso

- Login master inicial:
  - usuario: `master`
  - senha: `Master@123`
- Troque essa senha via env var antes de publicar.
- Operadores podem se cadastrar em `/register`.
- Master visualiza todos os usuarios e cotacoes.

## Rotas principais

- `/login`
- `/register`
- `/dashboard`
- `/quotes/<codigo>`
- `/admin/users` (somente master)

## Regras de cotacao implementadas

- Rotas validas (ida e volta):
  - Sao Paulo <-> Belem
  - Sao Paulo <-> Manaus
  - Sao Paulo <-> Macapa
  - Sao Paulo <-> Boa Vista
  - Sao Paulo <-> Fortaleza
- Base cubagem: `m3 x tarifa m3`
- Base peso: `kg x tarifa kg`
- Base NF: `valor NF x percentual rota`
- Media simples: `(cubagem + peso + NF) / 3`
- Media ponderada: `(NF x 0.50) + (Peso x 0.30) + (Cubagem x 0.20)`
- Valor cheio: maior base
- Valor justo: media ponderada
- Desconto maximo: media simples

## Extras opcionais

- Streamlit:
  ```bash
  streamlit run streamlit_app.py
  ```
- CLI:
  ```bash
  python main.py
  ```

