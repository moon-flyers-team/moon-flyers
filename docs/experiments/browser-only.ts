// Experiment-local permission gate; not installed in user/global Pi configuration.
import type { ExtensionAPI } from '@earendil-works/pi-coding-agent';
const auditUrl = process.env.BROWSER_AUDIT_URL || 'http://127.0.0.1:5175';
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(auditUrl)) throw new Error('Audit URL must be a loopback HTTP origin');
const allowed = ['computer_open', 'computer_read', 'computer_click', 'computer_type', 'computer_press', 'computer_scroll', 'computer_wait'];
export default function (pi: ExtensionAPI) {
  const addresses = new Set<string>();
  let opened = false, actions = 0, calls = 0;
  const started = Date.now();
  pi.on('before_agent_start', () => { pi.setActiveTools(allowed); });
  pi.on('tool_call', event => {
    const input = event.input as Record<string, any>;
    const refuse = (reason: string, terminate = false) => ({ block: true, reason, terminate });
    if (!allowed.includes(event.toolName)) return refuse('Experiment permits browser interaction only.');
    if (++calls > 70 || Date.now() - started > 10 * 60_000) return refuse('Experiment time/tool budget exhausted.', true);
    if (event.toolName === 'computer_open') {
      if (opened || input.at !== 'computer:machine/local' || input.browser !== 'msedge'
        || input.url !== auditUrl || Object.keys(input).some(key => !['at','browser','url'].includes(key)))
        return refuse('Only one disposable Edge browser at the experiment URL is permitted.');
      opened = true;
      return;
    }
    const address = input.window || input.path;
    if (!addresses.has(address)) return refuse('Only this participant browser and its observations are permitted.');
    if (event.toolName === 'computer_read') {
      input.views = ['dom'];
      return;
    }
    if (event.toolName === 'computer_wait') return;
    if (++actions > 20) return refuse('20 input actions reached; report partial results.', true);
    if (input.space === 'window') return refuse('Browser chrome/native input is outside this experiment.');
    if (event.toolName === 'computer_press' && !/^(?:Tab|shift\+Tab|Enter|Escape|ArrowLeft|ArrowRight|ArrowUp|ArrowDown|Home|End|ctrl\+a|Backspace|Delete|Space)$/i.test(input.key))
      return refuse('Only page-level form/navigation keys are permitted.');
  });
  pi.on('tool_result', event => {
    if (!allowed.includes(event.toolName)) return;
    const text = event.content.filter(part => part.type === 'text').map(part => part.text).join('\n');
    for (const match of text.matchAll(/computer:local\/[wo][a-zA-Z0-9]+/g)) addresses.add(match[0]);
    return { content: event.content.filter(part => part.type === 'text') };
  });
}
