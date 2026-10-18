import { Icon } from '@/components/icon';
import { PROVIDER_LOGOS } from '@/generated/provider-logos';
import { cx, modelLabel } from '@/lib/format';

/** The provider a model belongs to. Connections carry `provider`; treasury rows carry only the model id, so the id decides. */
export function providerOf(model: string | null | undefined, provider?: string | null): string | null {
  const p = (provider ?? '').toLowerCase().replace(/^gemini$/, 'google');
  if (p && PROVIDER_LOGOS[p]) return p;
  const m = (model ?? '').toLowerCase().replace(/^[a-z0-9_-]+\//, ''); // "openrouter/…" style prefixes
  if (m.startsWith('claude')) return 'anthropic';
  if (/^(gpt|o\d|chatgpt)/.test(m)) return 'openai';
  if (/^(gemini|gemma)/.test(m)) return 'google';
  if (m.startsWith('deepseek')) return 'deepseek';
  if (/^(glm|chatglm)/.test(m)) return 'zhipu';
  if (/^(kimi|moonshot)/.test(m)) return 'moonshot';
  if (/^(qwen|qwq)/.test(m)) return 'qwen';
  if (/^(mistral|codestral|ministral|magistral|devstral|pixtral)/.test(m)) return 'mistral';
  if (m.startsWith('grok')) return 'xai';
  if (m.startsWith('llama')) return 'meta';
  return null;
}

/** The provider's logo beside a model in the treasury; a model of an unknown provider gets the neutral model glyph. */
export function ModelMark({ model, provider, size = 14, className }: { model?: string | null; provider?: string | null; size?: number; className?: string }) {
  const key = providerOf(model, provider);
  const logo = key ? PROVIDER_LOGOS[key] : undefined;
  if (!logo) return <Icon name="model" size={size} className={cx('flex-none text-muted', className)} />;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" role="img" aria-label={logo.title} className={cx('flex-none', className)}>
      {logo.paths.map((p, i) => <path key={i} d={p.d} fill={p.fill ?? 'currentColor'} fillRule={logo.evenodd ? 'evenodd' : undefined} />)}
    </svg>
  );
}

/** A model's name with its provider's logo before it (Latin figures, as every model name). */
export function ModelName({ model, provider, size, className }: { model: string; provider?: string | null; size?: number; className?: string }) {
  return (
    <span className={cx('inline-flex items-center gap-1.5', className)}>
      <ModelMark model={model} provider={provider} size={size} />
      <span className="fig">{modelLabel(model)}</span>
    </span>
  );
}
