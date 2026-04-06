# Gemma 4 Family Overview

## Model Family

| Model | Architecture | Total Params | Active Params | Context | Modalities |
|-------|-------------|-------------|---------------|---------|------------|
| Gemma 4 E2B | Dense (PLE) | 5.1B | 2.3B effective | 128K | Text, Image, Audio |
| Gemma 4 E4B | Dense (PLE) | 8B | 4.5B effective | 128K | Text, Image, Audio |
| Gemma 4 26B-A4B | MoE | 26B | 3.8B active/token | 256K | Text, Image |
| Gemma 4 31B | Dense | 30.7B | 30.7B | 256K | Text, Image |

## Key Capabilities

1. **Reasoning**: Configurable thinking modes with `<|think|>` token
2. **Extended Multimodalities**: Text, Image (variable aspect ratio/resolution), Video, Audio (E2B/E4B only)
3. **Context Window**: Small models (128K), medium/large models (256K)
4. **Coding & Agentic**: Built-in function-calling support for autonomous agents
5. **System Prompt**: Native support for system role in conversations (new in Gemma 4)

## Memory Requirements

| Parameters | BF16 (16-bit) | SFP8 (8-bit) | Q4_0 (4-bit) |
|-----------|---------------|-------------|------------|
| Gemma 4 E2B | 9.6 GB | 4.6 GB | 3.2 GB |
| Gemma 4 E4B | 15 GB | 7.5 GB | 5 GB |
| Gemma 4 31B | 58.3 GB | 30.4 GB | 17.4 GB |
| Gemma 4 26B A4B | 48 GB | 25 GB | 15.6 GB |

## Architecture Notes

- **E2B/E4B**: "E" = "effective" parameters, uses Per-Layer Embeddings for on-device efficiency
- **26B MoE**: Only activates 4B params per token during generation, but all 26B must be loaded for routing
- **31B Dense**: Hybrid attention (sliding window + global), unified KV with p-RoPE

## Ollama Usage

```bash
ollama run gemma4:31b                        # Interactive chat
ollama run gemma4:31b "Your prompt here"     # Single query

# API
curl http://localhost:11434/api/chat \
  -d '{"model": "gemma4:31b", "messages": [{"role": "user", "content": "Hello!"}]}'
```

## Documentation Index

- [Prompt Formatting](prompt-formatting.md)
- [Function Calling](function-calling.md)
- [Model Card 31B](model-card-31b.md)
- Source: https://ai.google.dev/gemma/docs/core
