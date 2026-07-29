import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('platform package ships the bounded Owner MCP for authenticated web turns', () => {
  const packageJson = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
  assert.ok(packageJson.files.includes('owner/scripts/owner_client.py'));
  assert.ok(packageJson.files.includes('owner/scripts/owner_mcp.py'));

  const client = readFileSync(new URL('../owner/scripts/owner_client.py', import.meta.url), 'utf8');
  assert.match(client, /LENIN_OWNER_SESSION_COOKIE/);
  assert.match(client, /headers\["Cookie"\] = session_cookie/);
  assert.match(client, /LENIN_OWNER_PLATFORM_URL/);
});
