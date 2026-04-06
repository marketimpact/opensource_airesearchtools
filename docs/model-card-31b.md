# Gemma 4 31B Model Card

## Model Overview

- **Parameters**: 30.7B (dense architecture)
- **Context Window**: 256K tokens
- **Vision Encoder**: ~550M parameters
- **Modalities**: Text, Image
- **Layers**: 60
- **Sliding Window**: 1024 tokens
- **Vocabulary Size**: 262K
- **License**: Apache 2.0
- **Data Cutoff**: January 2025

## Core Capabilities

1. **Reasoning** - Built-in thinking mode with configurable step-by-step reasoning
2. **Long Context** - 256K token context window
3. **Image Understanding** - Object detection, document/PDF parsing, screen/UI, charts, OCR, handwriting
4. **Video Understanding** - Analyze videos via frame sequences
5. **Interleaved Multimodal Input** - Mix text and images in any order
6. **Function Calling** - Native support for structured tool use and agentic workflows
7. **Coding** - Code generation, completion, and correction
8. **Multilingual** - 35+ languages (pre-trained on 140+)

## System Prompt Support

Gemma 4 supports **native system role** (unlike Gemma 1-3 which only had user/model):

```json
[
  {"role": "system", "content": "You are a helpful assistant."},
  {"role": "user", "content": "Hello"},
]
```

## Recommended Sampling Parameters

- Temperature: 1.0
- Top-p: 0.95
- Top-k: 64

## Thinking Mode

- **Enable**: Include `<|think|>` token at start of system prompt
- **Output format**: `<|channel>thought\n[reasoning]\n<channel|>`
- **Multi-turn**: Do NOT include thinking content from previous turns in history
- **Efficiency**: Use system instructions to modulate thinking depth (~20% token reduction)

## Benchmark Results

| Benchmark | Score |
|-----------|-------|
| MMLU Pro | 85.2% |
| AIME 2026 (no tools) | 89.2% |
| LiveCodeBench v6 | 80.0% |
| Codeforces ELO | 2150 |
| GPQA Diamond | 84.3% |
| BigBench Extra Hard | 74.4% |
| MMMLU (multilingual) | 88.4% |
| MMMU Pro (Vision) | 76.9% |
| MATH-Vision | 85.6% |
| MRCR v2 8-needle 128k | 66.4% |

## Memory Requirements

| Precision | Size |
|-----------|------|
| BF16 (16-bit) | 58.3 GB |
| SFP8 (8-bit) | 30.4 GB |
| Q4_0 (4-bit) | 17.4 GB |

## Architecture Details

- **Hybrid Attention**: Interleaves local sliding window attention with full global attention
- **Key/Value Optimization**: Global layers feature unified Keys/Values and Proportional RoPE (p-RoPE)

## Limitations

- Generates based on training data patterns, not knowledge bases
- May produce incorrect or outdated statements (cutoff Jan 2025)
- No real-time information access
- May struggle with subtle nuances, sarcasm, figurative language
- Open-ended or highly complex tasks may be challenging
