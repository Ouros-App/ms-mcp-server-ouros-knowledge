# Ouros Knowledge MCP

Servidor FastAPI que expõe um endpoint MCP via Streamable HTTP para busca semântica em uma coleção Qdrant, usando embeddings da NVIDIA, e para consulta contextual somente leitura dos dados do MIDAS.

<!-- REPO-METADATA:START -->
<div align="center">

[![Repo Size](https://img.shields.io/github/repo-size/Ouros-App/ms-mcp-server-ouros-knowledge?style=flat-square&label=REPO%20SIZE)](https://github.com/Ouros-App/ms-mcp-server-ouros-knowledge)
[![Languages](https://img.shields.io/github/languages/count/Ouros-App/ms-mcp-server-ouros-knowledge?style=flat-square&label=LANGUAGES)](https://github.com/Ouros-App/ms-mcp-server-ouros-knowledge/languages)
[![Issues](https://img.shields.io/github/issues/Ouros-App/ms-mcp-server-ouros-knowledge?style=flat-square&label=ISSUES)](https://github.com/Ouros-App/ms-mcp-server-ouros-knowledge/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/Ouros-App/ms-mcp-server-ouros-knowledge?style=flat-square&label=PULL%20REQUESTS)](https://github.com/Ouros-App/ms-mcp-server-ouros-knowledge/pulls)

</div>
<!-- REPO-METADATA:END -->

## Visão geral

O serviço conecta um cliente MCP a duas fontes de informação:

- Qdrant, para recuperar trechos semanticamente relevantes de documentos;
- PostgreSQL do MIDAS, para retornar perfil, empresas, farms e dados operacionais associados ao usuário.

O servidor não oferece SQL arbitrário. As consultas PostgreSQL são fixas no código e devem ser executadas com uma credencial de leitura. A autenticação do transporte MCP usa um token Bearer configurado no ambiente; a identidade MIDAS é informada em cada chamada das tools de contexto e validada antes da consulta.

Fluxo principal:

```text
Cliente MCP
    │  Streamable HTTP + Authorization: Bearer <token>
    ▼
FastAPI /mcp/
    ├── Busca semântica ──► NVIDIA Embeddings ──► Qdrant
    └── Contexto MIDAS ─────────────────────────► PostgreSQL read-only
```

## Recursos

- Endpoint MCP em `/mcp/`, compatível com Streamable HTTP.
- Busca semântica com `search_knowledge(query, limit)`.
- Diagnóstico da coleção Qdrant com `qdrant_status()`.
- Diagnóstico da conexão PostgreSQL com `postgres_status()`.
- Contexto personalizado com `get_user_context(...)` e `get_user_farm_data(...)`.
- CLI para extrair, dividir, embeddar e sincronizar documentos com o Qdrant.
- Ingestão incremental baseada em SHA-256, modelo, coleção e parâmetros de chunking.
- Endpoints REST de disponibilidade e saúde.
- Documentação OpenAPI gerada pelo FastAPI.
- Imagem Docker sem copiar o `.env` nem os secrets para dentro da imagem.

## Pré-requisitos

- Python 3.12 ou compatível com as dependências do projeto.
- Um Qdrant acessível, com a coleção configurada já criada.
- Uma chave da NVIDIA para busca e ingestão de embeddings.
- PostgreSQL do MIDAS, caso sejam usadas as tools de contexto.
- Docker e Docker Compose apenas para execução em container ou pelos scripts auxiliares.

## Configuração

Crie o ambiente local a partir do exemplo:

```bash
cp .env.example .env
```

Preencha os valores necessários no `.env`:

| Variável | Padrão | Finalidade |
| --- | --- | --- |
| `APP_PORT` | `8000` | Porta em que o Uvicorn escuta. |
| `APP_NAME` | `ouros_knowledge_mcp` | Nome usado pelos scripts Docker. |
| `PROJECT_NAME` | `Ouros Knowledge MCP` | Nome exibido pela API e pelo servidor MCP. |
| `DESCRIPTION` | — | Descrição exibida no OpenAPI. |
| `VERSION` | `0.1.0` | Versão exposta pela API. |
| `QDRANT_URL` | `http://localhost:6333` | URL do Qdrant. |
| `QDRANT_API_KEY` | vazio | Chave do Qdrant, quando necessária. |
| `QDRANT_COLLECTION_NAME` | `ouros_knowledge` | Coleção usada na busca e na ingestão. |
| `NVIDIA_API_KEY` | vazio | Chave da NVIDIA AI Endpoints. |
| `NVIDIA_BASE_URL` | `https://integrate.api.nvidia.com/v1` | Endpoint da API de embeddings. |
| `NVIDIA_EMBEDDING_MODEL` | `nvidia/llama-nemotron-embed-1b-v2` | Modelo usado para gerar embeddings. |
| `SEARCH_TOP_K` | `5` | Quantidade padrão de resultados da busca. |
| `MIDAS_DATABASE_URL` | vazio | URL de conexão PostgreSQL do MIDAS. |
| `MIDAS_DB_CONNECT_TIMEOUT` | `10` | Timeout da conexão PostgreSQL, em segundos. |
| `MCP_AUTH_TOKEN` | vazio | Token Bearer usado para autenticar clientes MCP. |
| `MCP_RESOURCE_URL` | `http://localhost:8000/mcp` | URL base do recurso MCP; em produção, use a URL pública. |

Exemplo mínimo:

```dotenv
APP_PORT=8000
APP_NAME=ouros_knowledge_mcp
PROJECT_NAME=Ouros Knowledge MCP

QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION_NAME=ouros_knowledge

NVIDIA_API_KEY=nvapi-...
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_EMBEDDING_MODEL=nvidia/llama-nemotron-embed-1b-v2

MIDAS_DATABASE_URL=postgresql://midas_ro:senha@host/segundo_prod?sslmode=require&channel_binding=require
MIDAS_DB_CONNECT_TIMEOUT=10

MCP_AUTH_TOKEN=gere-um-token-aleatorio-com-pelo-menos-32-caracteres
MCP_RESOURCE_URL=http://localhost:8000/mcp
```

Cuidados importantes:

- Use o mesmo `NVIDIA_EMBEDDING_MODEL` utilizado para criar os vetores da coleção Qdrant.
- A coleção Qdrant precisa existir antes da busca ou da ingestão.
- Gere `MCP_AUTH_TOKEN` aleatoriamente, com pelo menos 32 caracteres.
- Use uma role PostgreSQL com acesso somente leitura às tabelas necessárias do schema `midas`.
- Nunca versione tokens, senhas ou URLs de conexão reais. O `.env` está ignorado pelo Git.
- Em um deployment público, configure `MCP_RESOURCE_URL` para a URL pública terminada em `/mcp`, por exemplo `https://ms-midas-mcp.discloud.app/mcp`.

## Execução local

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

URLs locais:

| URL | Uso |
| --- | --- |
| `http://localhost:8000/` | Verificação básica de disponibilidade. |
| `http://localhost:8000/health` | Health check. |
| `http://localhost:8000/docs` | Swagger UI. |
| `http://localhost:8000/redoc` | ReDoc. |
| `http://localhost:8000/mcp/` | Transporte MCP via Streamable HTTP. |

Teste os endpoints básicos:

```bash
curl http://localhost:8000/
curl http://localhost:8000/health
```

O Swagger documenta somente as rotas REST. As tools MCP aparecem no handshake e na listagem de tools do cliente MCP, não como operações REST no OpenAPI.

## Tools MCP

Todas as chamadas MCP devem enviar:

```http
Authorization: Bearer <MCP_AUTH_TOKEN>
```

| Tool | Parâmetros | Comportamento |
| --- | --- | --- |
| `search_knowledge` | `query`, `limit` opcional entre 1 e 20 | Busca trechos similares no Qdrant e retorna conteúdo, metadata e score. |
| `qdrant_status` | nenhum | Verifica conectividade e existência da coleção sem chamar a NVIDIA. |
| `postgres_status` | nenhum | Testa a conexão PostgreSQL e informa database e usuário conectados. |
| `get_user_context` | `user_type`, `user_id` | Retorna perfil e empresas/farms que pertencem ao escopo do usuário. |
| `get_user_farm_data` | `user_type`, `user_id`, `limit` opcional entre 1 e 100 | Retorna farms, metas, consumos, lotes e dicas limitados ao escopo do usuário. |

Os valores aceitos para `user_type` são `farm_owner`, `company_employee` e `admin`. O `user_id` deve ser positivo.

Exemplo de argumentos:

```json
{
  "name": "get_user_farm_data",
  "arguments": {
    "user_type": "farm_owner",
    "user_id": 42,
    "limit": 20
  }
}
```

O token compartilhado autentica o cliente, mas não representa uma identidade individual: qualquer cliente que possua esse token pode solicitar outra identidade válida. Para clientes não confiáveis, prefira tokens individuais e uma estratégia de autorização que associe o token ao usuário.

## Ingestão de documentos

O comando `ingest` lê `./docs` por padrão e aceita PDF, DOCX, TXT, Markdown, CSV, JSON e HTML:

```bash
python -m app.cli ingest
python -m app.cli ingest ./docs
python -m app.cli ingest contrato.pdf manual.docx
```

Antes de enviar dados ao Qdrant, valide a descoberta e a divisão dos documentos:

```bash
python -m app.cli ingest --dry-run
```

Parâmetros disponíveis:

```bash
python -m app.cli ingest \
  --chunk-size 1000 \
  --chunk-overlap 150 \
  --batch-size 32 \
  --manifest docs/.qdrant-manifest.json
```

O manifesto registra SHA-256, coleção, modelo, parâmetros de chunking, quantidade de chunks e IDs dos pontos. Em execuções seguintes:

- arquivos inalterados são ignorados;
- arquivos modificados são reprocessados;
- pontos antigos de documentos alterados são removidos;
- documentos removidos do escopo processado são reconciliados no Qdrant.

O `--dry-run` não cria embeddings nem envia pontos ao Qdrant. PDFs escaneados sem camada de texto precisam passar por OCR antes da ingestão; OCR não faz parte deste projeto.

## Docker

Build e execução direta:

```bash
docker build -t ouros-knowledge-mcp .
docker run --rm --env-file .env -p 8000:8000 ouros-knowledge-mcp
```

O container usa `APP_PORT` (8000 por padrão), injeta o `.env` em runtime e não copia o arquivo de secrets para a imagem. Se `APP_PORT` for alterado, ajuste também o mapeamento de portas.

### Scripts auxiliares

`run.sh` cria instâncias Docker numeradas e escolhe uma porta livre:

```bash
./run.sh
./run.sh --list
./run.sh --reboot 1
./run.sh --remove 1
```

`run_compose.sh` gera temporariamente um Compose por instância:

```bash
./run_compose.sh
./run_compose.sh --rebuild
./run_compose.sh --rebuild 1
./run_compose.sh --reboot 1
./run_compose.sh --bind 1
./run_compose.sh --help
```

Os scripts exigem um `.env` válido com `APP_NAME`. O modo `--bind` usa `./app` montado no container e é útil para desenvolvimento; os modos de rebuild fazem uma nova construção da imagem.

## Testes e qualidade

Instale as ferramentas de desenvolvimento e execute a suíte:

```bash
python -m pip install pytest pytest-cov ruff
ruff check .
pytest --cov=app
python -m compileall .
```

O workflow do GitHub Actions também executa lint, testes com cobertura, compilação, SonarCloud e CodeQL.

## Estrutura do projeto

```text
.
├── app/
│   ├── api/routes.py          # endpoints REST de operação
│   ├── cli.py                 # ingestão incremental de documentos
│   ├── core/config.py         # configuração carregada do .env
│   ├── mcp_server.py          # tools MCP e transporte HTTP
│   ├── services/auth.py       # validação do token e da identidade
│   ├── services/database.py   # consultas read-only e escopo MIDAS
│   ├── services/knowledge.py  # Qdrant e embeddings NVIDIA
│   └── main.py                # aplicação FastAPI
├── docs/                      # documentos usados na ingestão
├── tests/                     # testes unitários e de integração
├── .env.example               # modelo de configuração
├── Dockerfile
├── requirements.txt
├── run.sh
└── run_compose.sh
```

## Licença

MIT. Consulte [LICENSE](LICENSE).

## Principais contribuidores

<!-- CONTRIBUTORS:START -->
- [@Nicolas25vlad](https://github.com/Nicolas25vlad) — 14 contribuições
- [@Andre-Roger](https://github.com/Andre-Roger) — 1 contribuição
- [@juwata](https://github.com/juwata) — 1 contribuição
<!-- CONTRIBUTORS:END -->
