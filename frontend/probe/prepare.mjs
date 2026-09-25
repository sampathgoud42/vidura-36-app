// Regenerate the probe's copy of BotStationSite from the REAL source.
//
// A snapshot would rot: the probe would keep passing against a copy nobody
// edits while the file it is meant to protect drifts away from it. So the copy
// is rebuilt on every run and differs from the original in exactly two
// mechanical ways -- one added `export`, and import paths rewritten for the
// probe's directory. Nothing else is touched, so a render error in the copy is
// a render error in the file.
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const SRC = join(here, '..', 'src', 'sites', 'botstation', 'BotStationSite.jsx');
const OUT = join(here, '_console_copy.jsx');

let code = readFileSync(SRC, 'utf8');

const before = code;
code = code.replace('function BotConsole({', 'export function BotConsole({');
if (code === before) {
  console.error('probe: BotConsole not found in BotStationSite.jsx — '
    + 'the probe cannot reach the component it is meant to render.');
  process.exit(2);
}

// '../../x' resolves from src/sites/botstation; from probe/ it must be '../src/x'.
code = code.replaceAll("from '../../", "from '../src/");
code = code.replaceAll("import '../../", "import '../src/");
code = code.replaceAll("from './botstation.css'", "from '../src/sites/botstation/botstation.css'");
code = code.replaceAll("import './botstation.css'", "import '../src/sites/botstation/botstation.css'");

writeFileSync(OUT, code);
console.log('probe: copy regenerated from source');
