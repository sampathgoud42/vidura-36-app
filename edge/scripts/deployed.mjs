// Which build of the web app the edge is serving, for tools/appctl.py: once
// this record exists, `start` keeps the edge on the current build by itself.
//
//   node scripts/deployed.mjs record        after `npm run deploy`
//   node scripts/deployed.mjs clear         after `npm run delete`
//   node scripts/deployed.mjs fingerprint   print the current build's, only
//
// The fingerprint must match appctl's build_fingerprint() byte for byte --
// sha256 over frontend/dist-v2, file by file in path order: the relative
// path, a NUL, the bytes, a NUL. Change the two together.
import { createHash } from 'node:crypto';
import { mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const dist = join(root, 'frontend', 'dist-v2');
const record = join(root, 'var', 'edge.deployed');

function files(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = join(dir, e.name);
    if (e.isDirectory()) return files(p);
    return e.isFile() ? [p] : [];
  });
}

function fingerprint() {
  const h = createHash('sha256');
  files(dist)
    .map((p) => [relative(dist, p).split(sep).join('/'), p])
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .forEach(([rel, p]) => {
      h.update(Buffer.from(`${rel}\0`, 'utf8'));
      h.update(readFileSync(p));
      h.update(Buffer.from('\0', 'utf8'));
    });
  return h.digest('hex');
}

const mode = process.argv[2];
if (mode === 'record') {
  mkdirSync(dirname(record), { recursive: true });
  writeFileSync(record, `${JSON.stringify({
    build: fingerprint(),
    deployed_at: new Date().toISOString().replace(/\.\d{3}Z$/, '+00:00'),
  })}\n`);
  console.log('edge: this build is recorded as deployed - start keeps the edge on '
    + 'the current build from now on');
} else if (mode === 'clear') {
  rmSync(record, { force: true });
  console.log('edge: record cleared - start leaves the edge alone');
} else if (mode === 'fingerprint') {
  console.log(fingerprint());
} else {
  console.error('usage: node scripts/deployed.mjs record|clear|fingerprint');
  process.exit(2);
}
