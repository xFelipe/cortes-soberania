# Fine-tuning de modelo local — Canal Soberania

O pipeline coleta automaticamente todos os pares prompt/resposta das IAs durante a operação normal. Este documento explica como usar esse material para treinar um modelo local que substitua as chamadas à API do Claude.

---

## 1. O que é coletado e onde fica

A cada chamada à API, o pipeline grava um registro na tabela `training_examples` do banco `data/canal.db`:

| Campo | Conteúdo |
|---|---|
| `task` | Qual etapa gerou o exemplo (`triage_metadata`, `triage_caption`, `triage_transcript`, `find_clips`, `metadata`) |
| `prompt` | Texto exato enviado ao modelo, com todas as variáveis preenchidas |
| `completion` | Resposta bruta do modelo |
| `model` | Modelo usado (`claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, etc.) |
| `tokens_in / out` | Custo da chamada |
| `approved` | `NULL` = não curado · `1` = aprovado · `0` = rejeitado |
| `quality_note` | Anotação livre do curador |

Nenhuma configuração adicional é necessária — o log acontece automaticamente enquanto o pipeline roda.

---

## 2. Curadoria dos exemplos

A qualidade do fine-tuning depende diretamente da qualidade dos exemplos. Antes de exportar, revise e marque os exemplos:

```bash
# Ver quantos exemplos foram coletados por task
cs training-stats
```

Para curar via SQLite (aprovação em lote por task):

```bash
uv run python -c "
import sqlite3
conn = sqlite3.connect('data/canal.db')

# Aprovar todos os triage_metadata onde o modelo acertou o tema
# (ajuste o critério conforme necessário)
conn.execute(\"\"\"
    UPDATE training_examples
    SET approved = 1
    WHERE task = 'triage_metadata'
      AND approved IS NULL
\"\"\")

# Rejeitar exemplos com respostas claramente erradas
conn.execute(\"\"\"
    UPDATE training_examples
    SET approved = 0
    WHERE task = 'triage_metadata'
      AND completion NOT LIKE '%score%'
\"\"\")

conn.commit()
conn.close()
print('done')
"
```

Para curadoria manual interativa, use qualquer cliente SQLite com GUI:
- **DB Browser for SQLite** (gratuito, Windows/Mac/Linux) — `sqlitebrowser data/canal.db`
- **DBeaver** (multiplataforma)

Campos a editar na interface: `approved` (0 ou 1) e `quality_note` (observação livre).

---

## 3. Exportar para JSONL

```bash
# Só exemplos aprovados (recomendado para treino)
cs export-training

# Por task específica
cs export-training --task triage_metadata
cs export-training --task find_clips

# Todos sem filtro de curadoria (exploração)
cs export-training --all

# Caminho customizado
cs export-training --output /tmp/meu_dataset.jsonl
```

O arquivo gerado segue o **formato ChatML** (padrão da indústria):

```jsonl
{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}], "_task": "triage_metadata", "_model": "claude-haiku-4-5-20251001", "_id": 42}
```

Arquivos ficam em `data/training/` por padrão.

---

## 4. Quantos exemplos são necessários?

| Tarefa | Mínimo viável | Bom resultado | Excelente |
|---|---|---|---|
| Classificação binária (triagem) | 200 | 500 | 1.000+ |
| Extração estruturada (find_clips) | 500 | 1.000 | 2.000+ |
| Geração criativa (metadata) | 300 | 800 | 1.500+ |

Com o pipeline rodando nos 6 canais (2x/dia), você acumula ~100 exemplos/semana de triagem e ~20 exemplos/semana de find_clips e metadata. Em 1–2 meses já é possível treinar uma versão inicial.

---

## 5. Qual modelo base usar

| Modelo | Tamanho | Qualidade PT-BR | RAM (inference) | Fine-tune em |
|---|---|---|---|---|
| **Llama 3.1 8B Instruct** | 8B | Boa | 6 GB | GPU 8GB+ / CPU lento |
| **Gemma 2 9B Instruct** | 9B | Muito boa | 8 GB | GPU 8GB+ |
| **Qwen 2.5 7B Instruct** | 7B | Excelente (multilíngue) | 6 GB | GPU 8GB+ |
| **Phi-3.5 Mini** | 3.8B | Razoável | 3 GB | CPU viável |
| **Llama 3.1 70B** | 70B | Excelente | 40 GB | GPU A100/H100 |

**Recomendação para começar:** `Qwen 2.5 7B Instruct` — melhor PT-BR na faixa de 7B, roda em GPU de 8GB com quantização 4-bit.

---

## 6. Fine-tuning com Unsloth (recomendado)

[Unsloth](https://github.com/unslothai/unsloth) é a ferramenta mais eficiente para fine-tuning local — 2x mais rápido que HuggingFace puro, 60% menos memória.

### Instalação

```bash
pip install unsloth
# GPU NVIDIA (CUDA 12.1+):
pip install unsloth[cu121]
# Apple Silicon (M1/M2/M3):
pip install unsloth[mps]
```

### Script de fine-tuning

Salve como `scripts/finetune.py` e ajuste os caminhos:

```python
from unsloth import FastLanguageModel
from datasets import load_dataset
import torch

# 1. Carrega modelo base com LoRA
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="Qwen/Qwen2.5-7B-Instruct",
    max_seq_length=4096,
    dtype=None,          # auto-detect
    load_in_4bit=True,   # quantização 4-bit (cabe em 8GB de VRAM)
)

model = FastLanguageModel.get_peft_model(
    model,
    r=16,                # rank do LoRA — 16 é bom ponto de partida
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    lora_alpha=16,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
)

# 2. Carrega dataset exportado
dataset = load_dataset("json", data_files="data/training/export_all.jsonl", split="train")

# 3. Formata para ChatML
def format_example(example):
    messages = example["messages"]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    return {"text": text}

dataset = dataset.map(format_example)

# 4. Treina
from trl import SFTTrainer
from transformers import TrainingArguments

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=4096,
    args=TrainingArguments(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=10,
        num_train_epochs=3,
        learning_rate=2e-4,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=10,
        output_dir="data/training/checkpoints",
        save_strategy="epoch",
        optim="adamw_8bit",
        seed=42,
    ),
)
trainer.train()

# 5. Salva o adaptador LoRA
model.save_pretrained("data/training/lora_adapter")
tokenizer.save_pretrained("data/training/lora_adapter")
print("Fine-tuning concluído. Adaptador salvo em data/training/lora_adapter/")
```

### Hardware mínimo

| Configuração | Tempo estimado (1.000 exemplos) |
|---|---|
| GPU 8GB VRAM (RTX 3070/4060) | ~30 min |
| GPU 16GB VRAM (RTX 3080/4080) | ~15 min |
| Apple M2 Pro (16GB RAM) | ~60 min |
| CPU only | Não recomendado (horas) |

---

## 7. Fine-tuning com Axolotl (alternativa flexível)

[Axolotl](https://github.com/OpenAccess-AI-Collective/axolotl) é mais configurável, ideal se quiser misturar datasets ou usar técnicas avançadas.

```bash
pip install axolotl

# Crie config.yaml:
cat > data/training/axolotl_config.yaml << 'EOF'
base_model: Qwen/Qwen2.5-7B-Instruct
model_type: AutoModelForCausalLM
tokenizer_type: AutoTokenizer

load_in_4bit: true
adapter: lora
lora_r: 16
lora_alpha: 32
lora_dropout: 0.05
lora_target_modules:
  - q_proj
  - k_proj
  - v_proj
  - o_proj

datasets:
  - path: data/training/export_all.jsonl
    type: chat_template

sequence_len: 4096
num_epochs: 3
micro_batch_size: 2
gradient_accumulation_steps: 4
learning_rate: 0.0002
output_dir: data/training/axolotl_out

chat_template: chatml
EOF

axolotl train data/training/axolotl_config.yaml
```

---

## 8. Testar o modelo treinado

Antes de plugar no pipeline, teste a qualidade manualmente:

```bash
# Usando Ollama para servir o modelo fine-tuned
ollama create canal-soberania -f data/training/lora_adapter/Modelfile

ollama run canal-soberania "Dado o vídeo: [título] [descrição], score de 0-10 para relevância..."
```

Ou via Python:

```python
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    "data/training/lora_adapter",
    max_seq_length=4096,
    load_in_4bit=True,
)
FastLanguageModel.for_inference(model)

messages = [{"role": "user", "content": "SEU PROMPT AQUI"}]
inputs = tokenizer.apply_chat_template(messages, return_tensors="pt").to("cuda")
outputs = model.generate(inputs, max_new_tokens=512, temperature=0.1)
print(tokenizer.decode(outputs[0]))
```

---

## 9. Integrar de volta ao pipeline

Quando o modelo local for satisfatório, adicione suporte a ele no `llm.py`:

```python
# src/canal_soberania/llm.py — adição mínima
class LocalLLMClient:
    """Cliente para modelo local via Ollama."""
    def __init__(self, model_name: str = "canal-soberania") -> None:
        self._model = model_name

    def complete(self, prompt: str, model: str = "", task: str = "", **kwargs) -> LLMResponse:
        import urllib.request, json
        data = json.dumps({"model": self._model, "prompt": prompt, "stream": False}).encode()
        req = urllib.request.Request("http://localhost:11434/api/generate", data=data)
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
        text = result["response"]
        return LLMResponse(text=text, model=self._model, tokens_in=0, tokens_out=0, cost_usd=0.0)
```

No `.env`, adicione:

```env
LLM_PROVIDER=local          # ou "anthropic" (padrão)
LOCAL_MODEL_NAME=canal-soberania
```

E em `config.py`, leia `LLM_PROVIDER` para escolher qual cliente instanciar em cada stage.

---

## 10. Estratégia de substituição gradual

Não substitua tudo de uma vez. Ordem recomendada por risco:

1. **`triage_metadata`** — classificação binária simples, fácil de validar, alto volume → substitua primeiro
2. **`triage_caption`** — similar ao metadata, mesmo nível de complexidade
3. **`triage_transcript`** — texto longo, mais difícil → valide com 200+ exemplos antes
4. **`metadata`** — geração criativa → compare saídas lado a lado com o Claude por 2 semanas
5. **`find_clips`** — impacto maior em caso de erro (edição desnecessária) → substitua por último

Para cada stage, rode em paralelo (ambos os modelos, compare resultados) antes de desligar o Claude.
