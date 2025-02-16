# Teledown

Um aplicativo para baixar vídeos de canais do Telegram usando a API oficial.

## Configuração

Você pode usar o Teledown de duas maneiras: com sua conta pessoal ou com um bot.

### 1a. Usando Conta Pessoal - Obter Credenciais da API do Telegram

Antes de começar, você precisa obter suas credenciais da API do Telegram:

1. Visite [https://my.telegram.org/auth](https://my.telegram.org/auth)
2. Faça login com seu número de telefone
3. Clique em "API development tools"
4. Preencha o formulário (você pode usar "Teledown" como título do app e uma breve descrição)
5. Após enviar, você receberá:
   - `api_id` (um número)
   - `api_hash` (uma string)

### 1b. Usando Bot - Criar um Bot no Telegram

Se preferir usar um bot em vez de sua conta pessoal, siga estes passos:

1. Abra o Telegram e procure por "@BotFather"
2. Inicie uma conversa e envie o comando `/newbot`
3. Siga as instruções:
   - Digite um nome para seu bot
   - Digite um username para seu bot (deve terminar em 'bot')
4. O BotFather fornecerá um token no formato `123456789:ABCdefGHIjklmNOPQRstuvwxyz`
5. Guarde este token, você vai precisar dele

### 2. Configurar o Ambiente

1. Clone este repositório
2. Crie um arquivo `.env` na raiz do projeto:

   Se estiver usando conta pessoal:
   ```
   API_ID=your_api_id_here
   API_HASH=your_api_hash_here
   ```

   OU se estiver usando bot:
   ```
   BOT_TOKEN=your_bot_token_here
   ```

   Substitua os valores conforme sua escolha de autenticação.

### 3. Executar com Docker

O projeto usa Docker para facilitar a execução. Para iniciar:

```bash
docker-compose up -d
```

## Uso

1. Na primeira execução:
   - Se estiver usando conta pessoal, você precisará fazer login:
     - Digite seu número de telefone (com código do país, ex: +5511999999999)
     - Digite o código de verificação que você receberá no Telegram
   - Se estiver usando bot, apenas cole o token do bot quando solicitado

2. Como encontrar o link ou nome do canal no Telegram Desktop:
   - **Método 1 - Pelo link do canal:**
     1. Abra o canal no Telegram Desktop
     2. Clique nos 3 pontos (...) no topo direito
     3. Selecione "Copiar Link"
     4. O link será algo como `https://t.me/nomedocanal`

   - **Método 2 - Pelo nome do canal:**
     1. Abra o canal no Telegram Desktop
     2. O nome do canal começará com @ (exemplo: @nomedocanal)
     3. Você pode copiar esse nome diretamente do topo da janela do canal

3. Para baixar vídeos:
   - Cole o link ou nome do canal que você copiou
   - O programa listará todos os vídeos disponíveis no formato:
     ```
     □ [123456] Nome do Vídeo (2024-02-15 22:48:16)
     ↑   ↑        ↑              ↑
     |   |        |              +-- Data do vídeo
     |   |        +-- Título do vídeo
     |   +-- ID do vídeo (este é o número que você precisa)
     +-- Status: □ (não baixado) ou ✓ (já baixado)
     ```
   - Copie os números entre colchetes [123456] dos vídeos que deseja baixar
   - Cole os IDs separados por vírgula quando solicitado, exemplo:
     ```
     123456,123457,123458
     ```

Os vídeos serão salvos na pasta `downloads/`.

## Estrutura de Pastas

- `downloads/`: Pasta onde os vídeos são salvos
- `session/`: Armazena dados da sessão do Telegram
- `.env`: Arquivo com as credenciais da API

## Observações

- Os vídeos já baixados são marcados com ✓ verde
- Vídeos pendentes são marcados com □ amarelo
- O progresso do download é mostrado em tempo real