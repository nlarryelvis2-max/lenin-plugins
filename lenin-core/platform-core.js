import { readFileSync } from 'node:fs';

export const LENIN_CORE_VERSION = '0.2.0';

export const PLATFORM_CORE_PERSONA = [
  'Ты — Ленин, постоянный AI-партнёр пользователя и участник его проектов.',
  'Сначала пойми живую задачу и несущий неизвестный, затем действуй самым коротким достаточным способом.',
  'Отделяй проверенное от предположений, проверяй факты подходящим источником и честно называй оставшуюся неопределённость.',
  'Используй личный и проектный контекст только в пределах текущего доступа. Не смешивай приватное пользователя с общим знанием проекта.',
  'Внутренние линзы, модели и служебные термины не показывай без пользы для человека: ответ должен быть естественным, ясным и предметным.',
].join('\n');

const PLATFORM_SKILL_NAMES = Object.freeze([
  'atoms',
  'epistemic-postures',
  'explanation-forms',
  'keystone-first',
  'live-task-tethering',
  'pedagogical-lens',
  'trust-discipline',
]);

function frontmatterValue(frontmatter, key) {
  const match = frontmatter.match(new RegExp(`^${key}:\\s*(.+)$`, 'm'));
  if (!match) throw new Error(`Missing ${key} in Lenin Core skill`);
  return match[1].trim().replace(/^(['"])(.*)\1$/, '$2');
}

function loadSkill(name) {
  const source = readFileSync(new URL(`./skills/${name}/SKILL.md`, import.meta.url), 'utf8');
  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]+)$/);
  if (!match) throw new Error(`Invalid frontmatter in Lenin Core skill: ${name}`);
  const parsedName = frontmatterValue(match[1], 'name');
  if (parsedName !== name) throw new Error(`Lenin Core skill name mismatch: ${name}`);
  return Object.freeze({
    name,
    description: frontmatterValue(match[1], 'description'),
    body: match[2].trim(),
  });
}

const PLATFORM_SKILLS = Object.freeze(PLATFORM_SKILL_NAMES.map(loadSkill));

export function platformCoreSkills() {
  return PLATFORM_SKILLS.map((skill) => ({ ...skill }));
}
