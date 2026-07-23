import test from 'node:test';
import assert from 'node:assert/strict';
import {
  LENIN_CORE_VERSION,
  PLATFORM_CORE_PERSONA,
  platformCoreSkills,
} from '../lenin-core/platform-core.js';

test('platform projection exposes the provider-neutral core only', () => {
  const skills = platformCoreSkills();
  assert.equal(LENIN_CORE_VERSION, '0.2.0');
  assert.deepEqual(skills.map((skill) => skill.name), [
    'atoms',
    'epistemic-postures',
    'explanation-forms',
    'keystone-first',
    'live-task-tethering',
    'pedagogical-lens',
    'trust-discipline',
  ]);
  assert.equal(skills.some((skill) => skill.name === 'work-with-lenin-projects'), false);
  assert.ok(skills.every((skill) => skill.description && skill.body));
});

test('platform persona is useful without local hooks or personal state', () => {
  assert.match(PLATFORM_CORE_PERSONA, /Ты — Ленин/);
  assert.match(PLATFORM_CORE_PERSONA, /личный и проектный контекст/);
  assert.doesNotMatch(PLATFORM_CORE_PERSONA, /hook|~\/\.claude|token|14D/i);
});

test('callers receive independent skill objects', () => {
  const first = platformCoreSkills();
  first[0].body = 'changed';
  assert.notEqual(platformCoreSkills()[0].body, 'changed');
});
