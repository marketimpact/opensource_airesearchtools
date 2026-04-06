# Gemma 4 Prompt Formatting

## Core Control Tokens

Gemma 4 uses five fundamental control tokens to structure conversations:

- **`system`**: Indicates system instructions
- **`user`**: Marks user turns
- **`model`**: Marks model turns
- **`<|turn>`** and **`<turn|>`**: Delimit dialogue turns

### Basic Dialogue Structure

```
<|turn>system
    You are a helpful assistant.<turn|>
    <|turn>user
    Hello.<turn|>
```

## Multimodal Tokens

| Token Pair | Purpose |
|---|---|
| `<\|image>` / `<image\|>` | Image embeddings |
| `<\|audio>` / `<audio\|>` | Audio embeddings |

**Example multimodal prompt:**
```
<|turn>user
    Describe this image: <|image|>
    And translate these audio:
    a. <|audio|>
    b. <|audio|><turn|>
    <|turn>model
```

## Function Calling Tokens

Six special tokens manage tool use:

| Token Pair | Purpose |
|---|---|
| `<\|tool>` / `<tool\|>` | Tool definitions |
| `<\|tool_call>` / `<tool_call\|>` | Model requests tool usage |
| `<\|tool_response>` / `<tool_response\|>` | Tool execution results (acts as stop sequence) |

**String delimiter:** `<|"|>` encloses all string values in structured data blocks.

### Function Calling Example

```
<|turn>system
    <|think|>You are a helpful assistant.<|tool>declaration:get_current_temperature{...}<tool|><turn|>
    <|turn>user
    What's the temperature in London?<turn|>
    <|turn>model
    <|channel>thought
    ...
    <channel|><|tool_call>call:get_current_temperature{location:<|"|>London<|"|>}<tool_call|><|tool_response>
response:get_current_weather{temperature:15,weather:<|"|>sunny<|"|>}<tool_response|>
```

## Thinking Mode

Activate with `<|think|>` in system instructions.

| Token Pair | Purpose |
|---|---|
| `<\|think\|>` | Activates thinking mode |
| `<\|channel>` / `<channel\|>` | Internal model processes (followed by "thought") |

**Example:**
```
<|turn>system
    <|think|><turn|>
    <|turn>user
    What is the water formula?<turn|>
    <|turn>model
    <|channel>thought
    ...
    <channel|>The most common interpretation of "the water formula" refers...<turn|>
```

## Multi-Turn Conversation Management

- **Standard conversations:** Strip model-generated thoughts before passing history back to the model.
- **Function calling exception:** Do NOT remove thoughts between function calls within a single turn.
- **Long-running agents:** Consider summarizing previous thoughts and injecting them as standard text to maintain reasoning context.

## JSON Chat Format

```json
[
  {"role": "system", "content": "You are a helpful assistant."},
  {"role": "user", "content": "What's the temperature in London?"},
  {
    "role": "assistant",
    "tool_calls": [{"function": {"name": "get_current_weather", "arguments": {"location": "London"}}}],
    "tool_responses": [{"name": "get_current_weather", "response": {"temperature": 15, "weather": "sunny"}}],
    "content": "The temperature in London is 15 degrees and it is sunny."
  }
]
```

## Key Implementation Notes

- `<|channel>` tokens hide Chain-of-Thought content from end-users
- Application intercepts `tool_call`, executes code, returns within `tool_response`
- Larger models may generate thought channels even when disabled
- Use system instructions to modulate thinking depth (~20% token reduction with "LOW" thinking)
