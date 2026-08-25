# ms-mcp-server-ouros-knowledge

Servidor FastAPI com transporte MCP via Streamable HTTP para consultar uma coleção Qdrant usando embeddings da NVIDIA NIM.

<!-- REPO-METADATA:START -->
<!-- Metadados automáticos do repositório são mantidos pelo workflow. -->
<!-- REPO-METADATA:END -->

## O que já existe

- `GET /` e `GET /health` para operação básica.
- Endpoint MCP em `http://localhost:8000/mcp`.
- Ferramenta MCP `search_knowledge(query, limit)` para busca semântica.
- Ferramenta MCP `qdrant_status()` para verificar a coleção configurada.
- Ferramenta MCP `postgres_status()` para verificar a conexão somente leitura do MIDAS.
- Ferramentas MCP `get_user_context(...)` e `get_user_farm_data(...)` para contexto personalizado por usuário.
- CLI `ingest` para extrair, dividir, embeddar e enviar arquivos ao Qdrant.
- `QdrantVectorStore` e `NVIDIAEmbeddings` da stack LangChain.
- `.env` local ignorado pelo Git e `.env.example` como modelo de configuração.

## Configuração

Preencha o `.env` local:

```dotenv
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION_NAME=ouros_knowledge
NVIDIA_API_KEY=nvapi-...
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_EMBEDDING_MODEL=nvidia/llama-nemotron-embed-1b-v2
MIDAS_DATABASE_URL=postgresql://midas_ro:senha@host-neon/segundo_prod?sslmode=require&channel_binding=require
MIDAS_DB_CONNECT_TIMEOUT=10
```

O mesmo modelo de embedding precisa ter sido usado para gravar os vetores na coleção Qdrant. A coleção também precisa existir antes da busca; a ferramenta `qdrant_status` mostra essa condição sem chamar a NVIDIA.

`MIDAS_DATABASE_URL` deve usar a role `midas_ro` criada pela migration. A role acessa as views do schema `midas`, sem as colunas de senha, e não recebe uma ferramenta de SQL arbitrário. A senha real deve ficar somente no `.env`/secret manager.

## Execução local

```bash
python -m venv .venv

# Linux/macOS/WSL
source .venv/bin/activate

# Windows PowerShell
.venv\\Scripts\\Activate.ps1

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

URLs:

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- MCP: `http://localhost:8000/mcp`

## Docker

O container não copia `.env` para a imagem. Injete os secrets em runtime:

```bash
docker build -t ouros-knowledge-mcp .
docker run --rm --env-file .env -p 8000:8000 ouros-knowledge-mcp
```

## CLI de ingestão

O CLI lê `./docs` por padrão. Ele processa PDF, DOCX, TXT, Markdown, CSV, JSON e HTML:

```bash
python -m app.cli ingest
python -m app.cli ingest ./docs
python -m app.cli ingest contrato.pdf manual.docx
```

Antes do upload, confira os chunks sem gastar chamada da NVIDIA:

```bash
python -m app.cli ingest --dry-run
```

Opções úteis:

```bash
python -m app.cli ingest \
  --chunk-size 1000 \
  --chunk-overlap 150 \
  --batch-size 32
```

O CLI mantém `docs/.qdrant-manifest.json` com o SHA-256, modelo, coleção e IDs dos chunks. Em execuções seguintes, arquivos sem alteração são ignorados; documentos modificados são reprocessados e os chunks antigos que sobraram são removidos. Arquivos apagados do disco não são removidos automaticamente do Qdrant nesta versão. O mesmo modelo configurado no servidor (`NVIDIA_EMBEDDING_MODEL`) é usado no upload. PDFs escaneados sem camada de texto precisam de OCR, que ainda não está incluído.

## Próximo passo

Autenticação do endpoint MCP e um fluxo LangGraph podem ser adicionados quando o contrato de acesso estiver definido.

## Estrutura

```text
app/
├── api/routes.py          # endpoints FastAPI
├── core/config.py         # configuração carregada do .env
├── cli.py                 # ingestão incremental a partir de ./docs
├── mcp_server.py          # ferramentas MCP e transporte HTTP
├── services/database.py   # conexão read-only e contexto por usuário
├── services/knowledge.py  # Qdrant + NVIDIA embeddings
└── main.py                # aplicação FastAPI e montagem do MCP

docs/
└── .qdrant-manifest.json  # estado local da sincronização
```

## Licença

MIT. Consulte [LICENSE](LICENSE).

## Principais contribuidores

<!-- CONTRIBUTORS:START -->
- [@Nicolas25vlad](https://github.com/Nicolas25vlad) — 14 contribuições
- [@Andre-Roger](https://github.com/Andre-Roger) — 1 contribuição
- [@juwata](https://github.com/juwata) — 1 contribuição
<!-- CONTRIBUTORS:END -->
