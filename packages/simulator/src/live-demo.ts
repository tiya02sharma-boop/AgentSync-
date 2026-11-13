/**
 * Local, two-agent demo bridge.
 *
 * It intentionally observes files rather than pretending to call a model API:
 * two Codex CLI sessions edit their own folders and this process converts those
 * real filesystem writes into room events for the dashboard.
 */
import { randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, watch, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import type { NewEvent, Payload } from '@agentigram/protocol';
import { createMockCoordinator } from './server.js';

const repositoryRoot = resolve(dirname(new URL(import.meta.url).pathname), '../../..');
const demoRoot = join(repositoryRoot, '.agentsync-live');
const authRoot = join(demoRoot, 'auth-agent');
const profileRoot = join(demoRoot, 'profile-agent');
const authFile = join(authRoot, 'src', 'user.ts');
const profileFile = join(profileRoot, 'src', 'profile.ts');
const USER_ID = 'src/user.ts#User.user_id:property';
const roomId = 'hackathon';

const authTemplate = `export interface User {
  user_id: number;
  email: string;
}

export function createUser(user_id: number, email: string): User {
  return { user_id, email };
}
`;

const profileTemplate = `export type Profile = {
  user_id: number;
  displayName: string;
};

export function loadProfile(user_id: number): Profile {
  return { user_id, displayName: "Demo user" };
}
`;

function ensureFile(path: string, content: string): void {
  if (existsSync(path)) return;
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content);
}

export function setupLiveDemo(): void {
  ensureFile(authFile, authTemplate);
  ensureFile(profileFile, profileTemplate);
  console.log(`Live demo folders are ready:\n  Auth:    ${authRoot}\n  Profile: ${profileRoot}`);
}

function hasUuid(path: string): boolean {
  return /UUID|string/.test(readFileSync(path, 'utf8'));
}

if (process.argv.includes('--setup')) {
  setupLiveDemo();
  process.exit(0);
}

setupLiveDemo();
const coordinator = await createMockCoordinator({ port: 8787, log: (line) => console.log(`[live] ${line}`) });
console.log(`[live] dashboard coordinator on ${coordinator.url}/room/${roomId}`);

function submit(sessionId: 'auth' | 'profile' | 'system', source: NewEvent['source'], payload: Payload) {
  const actor =
    sessionId === 'system'
      ? { engineerId: 'agentsync', kind: 'system' as const }
      : { engineerId: `demo-${sessionId}`, sessionId, kind: 'agent' as const };
  coordinator.room(roomId).submit({
    id: randomUUID(),
    roomId,
    actor,
    source,
    payload,
  });
}

submit('auth', 'hook', {
  type: 'SESSION_STARTED',
  sessionId: 'auth',
  host: 'Codex CLI',
  model: 'gpt-5-codex',
  branch: 'live/auth-user-id',
  role: 'Auth Agent',
  task: 'Migrate user_id from number to UUID string',
});
submit('profile', 'hook', {
  type: 'SESSION_STARTED',
  sessionId: 'profile',
  host: 'Codex CLI',
  model: 'gpt-5-codex',
  branch: 'live/profile-user-id',
  role: 'Profile Agent',
  task: 'Keep profile API compatible with user_id',
});
submit('auth', 'mcp', {
  type: 'INTENT',
  task: 'Change User.user_id from number to UUID string',
  files: ['src/user.ts'],
  symbols: [USER_ID],
});
submit('profile', 'hook', { type: 'FILE_READ', path: 'src/profile.ts', symbols: [USER_ID] });
submit('profile', 'mcp', {
  type: 'INTENT',
  task: 'Maintain profile lookup while the user_id migration happens',
  files: ['src/profile.ts'],
  symbols: [USER_ID],
});

let authConflictRaised = false;
let profileResolved = false;

function onAuthChange(): void {
  if (!hasUuid(authFile) || authConflictRaised) return;
  authConflictRaised = true;
  submit('auth', 'watcher', { type: 'FILE_WRITE', path: 'src/user.ts', worktree: authRoot });
  submit('auth', 'watcher', {
    type: 'API_DELTA',
    module: 'src/user.ts',
    changes: [
      {
        symbol: USER_ID,
        before: 'number',
        after: 'string (UUID)',
        breaking: true,
        reason: 'The user_id interface changed from an integer to a UUID string.',
      },
    ],
  });
  submit('system', 'system', {
    type: 'COLLISION',
    collisionId: 'live-user-id',
    tier: 'SEMANTIC',
    symbols: [USER_ID],
    writerSession: 'auth',
    affectedSessions: ['profile'],
    detail: 'Auth changed user_id to UUID while Profile still expects a number.',
    confidence: 0.96,
  });
  submit('system', 'system', {
    type: 'PROPOSAL',
    collisionId: 'live-user-id',
    contract: {
      symbol: 'src/user.ts#User.user_id',
      kind: 'type',
      before: 'number',
      after: 'string',
      constraint: 'UUID v4',
      migration: 'Update Profile before Auth releases the interface migration.',
    },
  });
  console.log('[live] Conflict detected: Auth now uses UUID; Profile still uses number.');
}

function onProfileChange(): void {
  if (!authConflictRaised || !hasUuid(profileFile) || profileResolved) return;
  profileResolved = true;
  submit('profile', 'watcher', { type: 'FILE_WRITE', path: 'src/profile.ts', worktree: profileRoot });
  submit('profile', 'mcp', { type: 'ACCEPT', collisionId: 'live-user-id' });
  submit('system', 'system', {
    type: 'CONTRACT_COMPILED',
    contractId: 'live-user-id-v1',
    collisionId: 'live-user-id',
    checkFiles: [
      {
        path: '.agentsync/contracts/user-id-v1.md',
        content: 'All profile callers receive UUID user_id values.',
      },
    ],
  });
  submit('system', 'system', {
    type: 'CONTRACT_RESULT',
    contractId: 'live-user-id-v1',
    status: 'pass',
    detail: 'Profile now accepts UUID user_id values.',
  });
  submit('system', 'system', { type: 'RUN_VERIFIED', runId: 'live-contract-check', sessionId: 'profile', durationMs: 40 });
  console.log('[live] Profile accepted UUID. Contract compiled and verified.');
}

watch(authFile, { persistent: true }, onAuthChange);
watch(profileFile, { persistent: true }, onProfileChange);
console.log('[live] Watching real edits. Run `pnpm live:setup` to print the two folders again.');

for (const signal of ['SIGINT', 'SIGTERM'] as const) {
  process.on(signal, () => void coordinator.close().then(() => process.exit(0)));
}
