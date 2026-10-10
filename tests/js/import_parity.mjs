import {readFileSync} from 'node:fs';
import {framePgn, parseGame} from '../../site/assets/game-import-core.mjs';
const text = readFileSync(process.argv[2], 'utf8');
const records = [];
for (const frame of framePgn(text)) records.push(await parseGame(frame));
process.stdout.write(JSON.stringify(records));
