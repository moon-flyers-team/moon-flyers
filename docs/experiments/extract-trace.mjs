// Convert a local Pi JSONL stream into a reviewable text-only experiment transcript.
// Usage: node docs/experiments/extract-trace.mjs INPUT.jsonl OUTPUT.json
// No provider headers, system prompts, tool details, screenshots, credentials or model internals are retained.
import { readFile, writeFile } from 'node:fs/promises';
const [input, output] = process.argv.slice(2);
if (!input || !output) throw new Error('Specify input JSONL and output JSON paths');
const events = (await readFile(input, 'utf8')).trim().split(/\r?\n/).map(line => JSON.parse(line));
const transcript = events.filter(event => event.type === 'message_end' && ['user','assistant','toolResult'].includes(event.message?.role))
  .map(({ message }) => ({
    role: message.role, timestamp: message.timestamp,
    ...(message.toolName ? { tool: message.toolName, isError: !!message.isError } : {}),
    content: (Array.isArray(message.content) ? message.content : [{ type: 'text', text: message.content }])
      .filter(part => part.type === 'text' || part.type === 'toolCall')
      .map(part => part.type === 'text' ? { type: 'text', text: part.text }
        : { type: 'toolCall', name: part.name, arguments: part.arguments }),
  }));
const calls = transcript.flatMap(message => message.content.filter(part => part.type === 'toolCall'));
const result = {
  model: 'llama-local/qwen3.8-27b', modality: 'browser DOM/accessibility text, no images',
  tools: [...new Set(calls.map(call => call.name))],
  inputActionsAttempted: calls.filter(call => ['computer_click','computer_type','computer_press','computer_scroll'].includes(call.name)).length,
  toolCallsAttempted: calls.length,
  note: 'Attempted calls include errors/refusals. Read the transcript; counts do not establish successful actions or task completion.',
  transcript,
};
await writeFile(output, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ output, inputActionsAttempted: result.inputActionsAttempted, toolCallsAttempted: calls.length }));
