// Batch bridge for independent Python-vs-browser parity checks; stdin only.
import { Cube } from '../../site/assets/dashboard-core.mjs';
let text = '';
for await (const chunk of process.stdin) text += chunk;
const { payload, requests } = JSON.parse(text);
const cube = new Cube(payload);
process.stdout.write(JSON.stringify(requests.map(({ method, args }) => cube[method](...args))));
