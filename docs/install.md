# Instalação — Canal Soberania

## Pré-requisitos

O app Canal Soberania é um frontend Tauri que consome a API FastAPI local.
Ambos (app + backend) precisam rodar na mesma máquina.

### Backend (Python)

```bash
# Clone do repositório
git clone git@github.com:xFelipe/cortes-soberania.git
cd cortes-soberania

# Instalar dependências
uv sync

# Configurar variáveis de ambiente
cp .env.example .env
# Edite .env com suas chaves (Anthropic API, YouTube OAuth, etc.)

# Inicializar banco de dados
sqlite3 data/canal.db < schema.sql

# Subir a API (deve rodar sempre que o app estiver aberto)
cs serve
# → imprime o token Bearer e o caminho do arquivo
# → fica em execução na porta 8000
```

O token é salvo automaticamente em `~/.config/canal-soberania/.api_token` (lido pelo app).

---

## Instalação do App (frontend)

### Linux

#### AppImage (recomendado — portable, sem instalação)

```bash
# Baixar da página de releases
wget https://github.com/xFelipe/cortes-soberania/releases/latest/download/canal-soberania_0.10.0_amd64.AppImage
chmod +x canal-soberania_0.10.0_amd64.AppImage
./canal-soberania_0.10.0_amd64.AppImage
```

Dependência do sistema:
```bash
sudo apt install libwebkit2gtk-4.1-dev
# ou equivalente no seu distro
```

#### .deb (Ubuntu/Debian)

```bash
wget https://github.com/xFelipe/cortes-soberania/releases/latest/download/canal-soberania_0.10.0_amd64.deb
sudo dpkg -i canal-soberania_0.10.0_amd64.deb
```

---

### Windows

Baixe o `.msi` ou `.exe` da [página de releases](https://github.com/xFelipe/cortes-soberania/releases/latest) e execute o instalador.

---

## Construir do zero (desenvolvimento)

```bash
# Dependências do sistema (Ubuntu/Debian)
sudo apt install -y \
  libwebkit2gtk-4.1-dev \
  libappindicator3-dev \
  librsvg2-dev \
  patchelf

# Rust (se não tiver)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Node + pnpm
# Veja as versões no README; recomendado Node 22 + pnpm 11

cd ui
pnpm install
pnpm tauri build
# Binários gerados em: ui/src-tauri/target/release/bundle/
```

---

## Publicar uma nova release (mantenedor)

### 1. Gerar keypair de assinatura (apenas na primeira vez)

```bash
# Instalar CLI Tauri
cargo install tauri-cli

# Gerar par de chaves Ed25519
cargo tauri signer generate -w ~/.tauri/canal-soberania.key

# Saída:
#   Private key: ~/.tauri/canal-soberania.key   (SEGREDO — não commitar)
#   Public key:  dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk...
```

### 2. Configurar GitHub Secrets

No repositório, vá em **Settings → Secrets → Actions** e adicione:

| Secret | Valor |
|---|---|
| `TAURI_SIGNING_PRIVATE_KEY` | Conteúdo do arquivo `.key` gerado acima |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | Senha definida ao gerar (ou vazio se sem senha) |

### 3. Commitar a chave pública

Abra [ui/src-tauri/tauri.conf.json](../ui/src-tauri/tauri.conf.json) e preencha o campo `plugins.updater.pubkey` com a chave pública gerada no passo 1:

```json
"plugins": {
  "updater": {
    "pubkey": "COLE_A_CHAVE_PUBLICA_AQUI",
    "endpoints": ["https://github.com/xFelipe/cortes-soberania/releases/latest/download/latest.json"]
  }
}
```

> A chave pública é segura para commitar — só a privada é segredo.

### 4. Criar a release

```bash
# Incrementar versão em ui/src-tauri/tauri.conf.json ("version": "X.Y.Z")
# Commitar a mudança de versão
git add ui/src-tauri/tauri.conf.json
git commit -m "chore: bump version to vX.Y.Z"

# Criar tag e push — dispara o workflow automaticamente
git tag vX.Y.Z
git push origin vX.Y.Z
```

O workflow `.github/workflows/release.yml` vai:
1. Compilar para Linux (AppImage + .deb) e Windows (.msi + .exe)
2. Assinar os binários com a chave privada
3. Criar um GitHub Release draft com todos os artefatos + `latest.json`
4. Você publica o draft manualmente após revisar

---

## Auto-update

O app verifica atualizações automaticamente via `tauri-plugin-updater` ao ser iniciado, consultando:

```
https://github.com/xFelipe/cortes-soberania/releases/latest/download/latest.json
```

Quando uma nova versão está disponível, o app pergunta ao usuário se deseja instalar.

> O auto-update só funciona depois que a `pubkey` estiver configurada em `tauri.conf.json` (passo 3 acima).
