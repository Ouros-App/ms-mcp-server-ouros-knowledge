# Especificação para o DBA — importação histórica via Midas

## Objetivo

Permitir que o produtor (`farm_owner`) importe para o Ouros registros históricos que já possui em Excel, PDF ou texto em linguagem natural — inicialmente consumo de água e energia elétrica — usando o Midas como interface e o MCP como camada de integração.

O Midas não deve receber acesso genérico de escrita nem executar SQL arbitrário. A gravação deve ocorrer exclusivamente por uma função PostgreSQL controlada, com validação, escopo da granja, idempotência e auditoria.

## Contexto atual

- O banco do Midas é PostgreSQL, no schema `midas`.
- O servidor `ms-mcp-server-ouros-knowledge` hoje usa uma credencial de leitura (`midas_ro`) e expõe apenas consultas fixas.
- O fluxo atual resolve o escopo do `farm_owner` por `midas.farm_owners.id -> farm_owners.id_farm -> farms.id`.
- As tabelas relevantes existentes são `midas.water_registries` e `midas.energy_registries`.
- Os registros atuais de água possuem `registration_date`, `start_hydrometer`, `end_hydrometer` e `id_farm`.
- Os registros atuais de energia possuem `registration_date`, `energy_consumption` e `id_farm`.
- O produto é offline-first; a importação poderá ser preparada offline e enviada posteriormente.

Antes de implementar, confirmar no catálogo os tipos, constraints, triggers, índices e colunas obrigatórias dessas tabelas. Não assumir que o README substitui o schema real.

## Proposta de contrato da função

Criar uma função no schema `midas`, com nome versionável, por exemplo:

```sql
midas.import_resource_records(
    p_request_id uuid,
    p_actor_user_type text,
    p_actor_user_id bigint,
    p_source_type text,
    p_source_name text,
    p_records jsonb
) returns jsonb
```

Recomenda-se que o servidor MCP chame essa função usando parâmetros, nunca concatenando SQL. A função deve retornar um resumo seguro, por exemplo:

```json
{
  "request_id": "...",
  "status": "accepted",
  "inserted": 12,
  "skipped_duplicates": 2,
  "rejected": 1,
  "errors": [{"index": 4, "code": "INVALID_VALUE", "message": "..."}]
}
```

Se o lote tiver qualquer erro, decidir com o produto entre `all_or_nothing` (preferível no primeiro MVP) ou aceitação parcial explícita. A decisão deve fazer parte do contrato, não ser implícita.

## Formato canônico dos registros

O Midas pode interpretar Excel/PDF/linguagem natural, mas deve converter tudo para um formato estruturado antes da chamada ao banco:

```json
{
  "resource_type": "water",
  "farm_id": 123,
  "registration_date": "2025-01-31",
  "start_hydrometer": 1000.0,
  "end_hydrometer": 1250.0,
  "energy_consumption": null,
  "source_row": 8,
  "confidence": 0.98
}
```

Para energia, usar `resource_type: "energy"` e `energy_consumption`. Campos não aplicáveis devem ser `null`. O DBA deve documentar unidades e escala decimal; não aceitar unidade ambígua. Valores monetários, quando existirem no documento, não devem ser gravados nessas tabelas sem uma decisão de modelo separada.

## Regras obrigatórias da função

1. Aceitar somente `p_actor_user_type = 'farm_owner'` no MVP. `company_employee` e `admin` ficam fora até haver política específica.
2. Confirmar que `p_actor_user_id` existe em `midas.farm_owners`.
3. Derivar a granja permitida exclusivamente do banco (`farm_owners.id_farm`); nunca confiar em `farm_id` enviado pelo Midas.
4. Rejeitar qualquer registro cujo `farm_id` seja diferente da granja derivada.
5. Aceitar somente `water` e `energy`, com lista fechada de campos.
6. Validar data, números finitos e não negativos; para água, exigir `end_hydrometer >= start_hydrometer`.
7. Aplicar limites de lote e tamanho do JSONB para evitar abuso de memória/tempo.
8. Usar uma transação única e bloquear/garantir consistência contra duplicidade concorrente.
9. Tornar a operação idempotente por `p_request_id`; repetir a mesma requisição não pode inserir novamente.
10. Não permitir UPDATE ou DELETE por essa função. Correções devem ser um fluxo separado, auditado e autorizado.
11. Não retornar dados pessoais, SQL, stack trace ou conteúdo integral do documento; retornar apenas o resumo e erros por índice.

## Idempotência e duplicidade

Criar uma tabela de controle, por exemplo `midas.resource_import_requests`, contendo ao menos:

- `request_id uuid primary key`;
- ator (`actor_user_type`, `actor_user_id`);
- `source_type`, `source_name` e hash SHA-256 do arquivo/payload;
- status, contagens, timestamps e mensagem de erro segura;
- `created_at`, `completed_at` e, se aplicável, `schema_version`.

Criar também uma chave natural/índice único adequado nas tabelas de registros, ou uma estratégia equivalente definida após inspecionar o schema. A chave deve considerar granja, tipo e data e, para medição de água, as leituras inicial/final. Não deduplicar apenas por data sem avaliar medições legítimas múltiplas no mesmo dia.

## Auditoria e rastreabilidade

Registrar quem solicitou a importação, quando, qual origem, hash do conteúdo, quantidade recebida/inserida/rejeitada e a versão do contrato. Se o sistema guardar o arquivo original, ele deve ficar fora do PostgreSQL ou em armazenamento apropriado, com referência/retention definida; não colocar PDFs potencialmente sensíveis dentro de logs.

## Permissões PostgreSQL

Criar uma role exclusiva para o serviço MCP, sem login humano e sem privilégios de owner/superuser:

- `CONNECT` no banco e `USAGE` no schema necessário;
- `EXECUTE` somente em `midas.import_resource_records`;
- sem `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE` ou `CREATE` nas tabelas de negócio;
- sem acesso às demais funções de escrita;
- revogar `EXECUTE` do `PUBLIC`;
- manter a função como `SECURITY DEFINER` somente se necessário, com `search_path` fixo e seguro (`midas, pg_catalog`), nomeando objetos sem depender de resolução controlada pelo chamador;
- dono da função separado da role de execução;
- não conceder `BYPASSRLS`.

Se a função não precisar de privilégios elevados, preferir `SECURITY INVOKER`. O DBA deve entregar evidência dos `GRANT`s e de uma tentativa de escrita direta negada.

## Integração MCP/API

O servidor deverá ganhar uma tool específica, por exemplo `import_user_resource_records`, que:

- autentique o transporte MCP;
- resolva/valide a identidade do usuário;
- aceite somente o formato canônico;
- valide limites básicos antes do banco;
- chame apenas a função parametrizada;
- não exponha uma tool de SQL, tabela ou operação genérica;
- rejeite `admin`/outros perfis no MVP;
- aplique timeout e limite de tamanho;
- registre `request_id` para correlação, sem registrar tokens ou documentos completos.

O Midas deve mostrar uma prévia e pedir confirmação explícita antes de gravar, especialmente quando a extração veio de PDF ou linguagem natural. A confiança do parser é sinal para revisão, não autorização automática.

## Entregáveis esperados do DBA

- migration SQL versionada;
- definição da função e comentários de contrato;
- tabela de controle de importações e índices;
- constraints/índices de idempotência;
- criação da role e `GRANT/REVOKE` mínimos;
- rollback seguro da migration;
- exemplo de chamada parametrizada e respostas;
- teste em QA com sucesso, duplicidade, usuário inexistente, granja de terceiro, payload inválido e lote acima do limite;
- evidência de que `midas_ro` continua somente leitura e a nova role não executa SQL direto.

## Critérios de aceite

- Um `farm_owner` só insere registros na própria granja.
- Uma requisição repetida pelo mesmo `request_id` não duplica dados.
- Uma tentativa de apontar outra granja é rejeitada integralmente.
- Dados inválidos não chegam às tabelas de negócio.
- Não existe caminho MCP para SQL arbitrário ou escrita direta.
- Toda importação pode ser rastreada até ator, origem, hash e resultado.
- Falhas não deixam metade do lote gravado, caso seja adotado `all_or_nothing`.
- A função não altera nem remove registros existentes.
- O contrato suporta retry seguro após perda de conexão.

## Decisões pendentes do produto

- Confirmar se o MVP aceita apenas água/energia ou também custos, lotes e produção.
- Definir unidades oficiais e fuso/data de competência.
- Escolher `all_or_nothing` ou parcial com revisão.
- Definir retenção do arquivo original e política LGPD.
- Definir o fluxo separado para correção/estorno de importações.

### Referências

- README da organização Ouros: https://github.com/Ouros-App
- README deste serviço: `ms-mcp-server-ouros-knowledge/README.md`
- Implementação atual de contexto PostgreSQL: `app/services/database.py`
- Implementação atual de autenticação MCP: `app/services/auth.py`
