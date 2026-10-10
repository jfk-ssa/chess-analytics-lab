const el = (id) => document.getElementById(`import-${id}`);
const number = (n) => n.toLocaleString('en-US');
const percent = (n) => (n === null ? 'Unavailable' : `${(n * 100).toFixed(2)}%`);
const providerNames = { chesscom: 'Chess.com', lichess: 'Lichess', pgn: 'Generic PGN' };
function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  if (className) result.className = className;
  return result;
}
function table(headers, rows) {
  const result = node('table');
  const head = node('thead');
  const heading = node('tr');
  headers.forEach((label) => {
    const cell = node('th', label);
    cell.scope = 'col';
    heading.append(cell);
  });
  head.append(heading);
  const body = node('tbody');
  rows.forEach((values) => {
    const row = node('tr');
    values.forEach((value) => {
      row.append(value instanceof Node ? value : node('td', value));
    });
    body.append(row);
  });
  result.append(head, body);
  const wrapper = node('div', undefined, 'scroll import-table');
  wrapper.tabIndex = 0;
  wrapper.setAttribute('role', 'region');
  wrapper.setAttribute('aria-label', headers.join(', '));
  wrapper.append(result);
  return wrapper;
}
const referenceData = JSON.parse(el('reference-data').textContent);
const example = JSON.parse(el('example-data').textContent);
let worker = null;
let timer = null;
let loaded = null;
let report = null;
let busy = false;
let demo = false;
let downloadUrl = null;
function status(text) {
  el('status').textContent = text;
}
function available() {
  const selected = [...el('players').querySelectorAll('select')].some((select) => select.value);
  el('analyze').disabled = busy || !loaded || !selected;
  el('download').disabled = busy || !report;
  el('cancel').hidden = !busy;
  el('files').disabled = busy;
  el('example').disabled = busy;
  el('clear').disabled = !worker && !loaded && !report;
  el('filters').disabled = busy;
}
function clearSession(message = 'Session cleared. Choose PGN files or try the authored example.') {
  if (worker) worker.terminate();
  worker = null;
  clearTimeout(timer);
  timer = null;
  loaded = null;
  report = null;
  busy = false;
  demo = false;
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  downloadUrl = null;
  el('files').value = '';
  el('since').value = '';
  el('until').value = '';
  el('rated').value = 'all';
  el('minimum20').checked = false;
  el('players').replaceChildren();
  el('summary').replaceChildren();
  el('results').replaceChildren();
  el('selection').hidden = true;
  status(message);
  available();
}
function startWorker(isDemo) {
  clearSession('Reading files on this device…');
  demo = isDemo;
  busy = true;
  worker = new Worker('assets/game-import-worker.mjs', { type: 'module' });
  const activeWorker = worker;
  worker.onmessage = (event) => {
    if (worker === activeWorker) onMessage(event);
  };
  worker.onerror = () => {
    if (worker === activeWorker)
      clearSession(
        'The local import worker could not run. Check browser support and reload the page.',
      );
  };
  timer = setTimeout(
    () =>
      clearSession(
        'Processing reached the 60-second limit. Try a smaller export; no partial analysis was kept.',
      ),
    60000,
  );
  available();
}
function onMessage(event) {
  const message = event.data;
  if (message.type === 'progress') {
    status(`Legally replayed ${number(message.processed)} of ${number(message.total)} records…`);
    return;
  }
  busy = false;
  clearTimeout(timer);
  timer = null;
  if (message.type === 'error') {
    clearSession(message.message);
    return;
  }
  if (message.type === 'loaded') {
    loaded = message;
    const s = loaded.stats;
    el('summary').replaceChildren(
      node(
        'p',
        `${number(s.seen)} framed records · ${number(s.accepted)} accepted games · ${number(s.duplicates)} duplicate copies · ${number(s.conflicts)} conflicting copies withheld · ${number(s.rejected)} rejected records · ${number(s.failed_files)} failed files.`,
        'stats',
      ),
    );
    if (demo)
      el('summary').prepend(
        node('p', 'Authored example games — synthetic fixtures, not account history.', 'badge'),
      );
    const reasons = new Map();
    loaded.rejected.forEach((item) => {
      reasons.set(item.reason, (reasons.get(item.reason) || 0) + 1);
    });
    const detail = node('details');
    detail.append(node('summary', 'Import dispositions and file checks'));
    if (reasons.size)
      detail.append(
        table(
          ['Reason', 'Records'],
          [...reasons].map(([reason, count]) => [reason.replaceAll('_', ' '), number(count)]),
        ),
      );
    loaded.failures.forEach((item) => {
      detail.append(node('p', `${item.file}: ${item.reason}`));
    });
    if (loaded.failures.length)
      detail.append(
        node(
          'p',
          'Failed files contribute no accepted games. Their unframed records are outside the framed-record count.',
        ),
      );
    loaded.sources.forEach((source) => {
      detail.append(node('p', `${source.name} · SHA-256 ${source.sha256}`, 'source-note'));
    });
    el('summary').append(detail);
    el('players').replaceChildren();
    Object.entries(loaded.players).forEach(([provider, players]) => {
      const group = node('div');
      const label = node('label', `${providerNames[provider]} player`);
      label.htmlFor = `import-player-${provider}`;
      const select = node('select');
      select.id = label.htmlFor;
      select.dataset.provider = provider;
      const empty = node('option', 'Choose a player / exclude this provider');
      empty.value = '';
      select.append(empty);
      players.forEach((player) => {
        const option = node(
          'option',
          `${player.name} · ${number(player.white)} White / ${number(player.black)} Black`,
        );
        option.value = player.key;
        select.append(option);
      });
      if (demo && players.some((p) => p.key === 'examplewhite')) select.value = 'examplewhite';
      select.addEventListener('change', () => {
        invalidate();
        available();
      });
      group.append(label, select);
      el('players').append(group);
    });
    el('time-control').replaceChildren();
    const all = node('option', 'All time controls');
    all.value = 'all';
    el('time-control').append(all);
    loaded.timeControls.forEach((value) => {
      const option = node('option', value === 'unknown' ? 'Unknown time control' : value);
      option.value = value;
      el('time-control').append(option);
    });
    el('selection').hidden = !s.accepted;
    status(
      s.accepted
        ? 'Choose your player separately for each provider, then analyze the selected White games.'
        : 'No supported completed games were imported. Review the dispositions and try another file.',
    );
    available();
    if (demo && s.accepted) analyze();
  } else if (message.type === 'analysis') {
    report = {
      kind: 'local_user_opening_analysis',
      contract_version: message.result.contract_version,
      source_mode: demo ? 'authored_fixture' : 'local_pgn_files',
      import_stats: loaded.stats,
      sources: loaded.sources,
      reference: currentReference().identity,
      selection: selection(),
      analysis: message.result,
    };
    render(message.result);
    status(
      `${number(message.result.denominator_games)} selected White games analyzed locally. Your PGNs have not been sent to a server.`,
    );
    available();
  }
}
function invalidate() {
  report = null;
  el('results').replaceChildren();
  el('download').disabled = true;
}
function selection() {
  const aliases = Object.fromEntries(
    [...el('players').querySelectorAll('select')]
      .filter((select) => select.value)
      .map((select) => [select.dataset.provider, select.value]),
  );
  return {
    aliases,
    options: {
      since: el('since').value,
      until: el('until').value,
      time_control: el('time-control').value,
      rated: el('rated').value,
      minimum20: el('minimum20').checked,
    },
  };
}
function currentReference() {
  const cohort = referenceData.cohorts[el('cohort').value];
  const view = cohort.views[el('view').value];
  const ids = view.rankings[el('kind').value].slice(0, Number(el('n').value));
  return {
    ids,
    positions: view.positions,
    identity: {
      corpus_snapshot_id: referenceData.corpus_snapshot_id,
      cohort: el('cohort').value,
      view: el('view').value,
      ranking: el('kind').value,
      position_ids: ids,
      scope: 'Selected published study positions and up to three route examples per position',
    },
  };
}
function updateReferenceViews() {
  const previous = el('view').value;
  el('view').replaceChildren();
  Object.entries(referenceData.cohorts[el('cohort').value].views).forEach(([name, view]) => {
    const option = node('option', view.label);
    option.value = name;
    el('view').append(option);
  });
  el('view').value = referenceData.cohorts[el('cohort').value].views[previous] ? previous : 'all';
  invalidate();
}
function analyze() {
  if (!loaded || busy) return;
  const selected = selection();
  if (!Object.keys(selected.aliases).length) {
    status('Choose at least one player first.');
    return;
  }
  busy = true;
  invalidate();
  available();
  status('Comparing selected White games with the chosen reference set…');
  timer = setTimeout(
    () => clearSession('Analysis reached its 60-second limit. Try a smaller export.'),
    60000,
  );
  worker.postMessage({ type: 'analyze', ...selected, reference: currentReference() });
}
function board(key) {
  const result = node('div', undefined, 'import-board');
  result.setAttribute('role', 'img');
  result.setAttribute('aria-label', `White to move; canonical board ${key}`);
  key
    .split(' ')[0]
    .split('/')
    .forEach((rank, row) => {
      let column = 0;
      for (const char of rank) {
        const count = /[1-8]/.test(char) ? Number(char) : 1;
        for (let i = 0; i < count; i++, column++) {
          const square = node(
            'div',
            undefined,
            (row + column) % 2 ? 'import-square dark' : 'import-square light',
          );
          if (!/[1-8]/.test(char)) {
            const piece = node('img');
            piece.alt = '';
            piece.width = 45;
            piece.height = 45;
            piece.src = `assets/pieces/${char === char.toUpperCase() ? 'w' : 'b'}${char.toUpperCase()}.svg`;
            square.append(piece);
          }
          result.append(square);
        }
      }
    });
  return result;
}
function render(result) {
  const output = el('results');
  output.replaceChildren();
  output.append(node('h2', 'Your selected opening positions'));
  output.append(
    node(
      'p',
      `${number(result.denominator_games)} White games in the denominator · ${number(result.games_reaching_window)} reach ply 6 · ${number(result.games_shorter_than_window)} are shorter · ${number(result.distinct_positions)} distinct opening boards · ${number(result.recurring_positions)} occur in two or more games.`,
      'stats',
    ),
  );
  const exclusions = Object.entries(result.excluded).map(([key, count]) => [
    key.replaceAll('_', ' '),
    number(count),
  ]);
  const excluded = node('details');
  excluded.append(node('summary', 'Selection exclusions'), table(['Reason', 'Games'], exclusions));
  output.append(excluded);
  output.append(node('h3', 'Coverage of the selected public study set'));
  output.append(
    node(
      'p',
      `${number(result.covered_games)} games reach at least one selected board (${percent(result.coverage_share)}). A game counts once even if it reaches several. Short White games stay in the denominator unless the comparison filter is selected.`,
    ),
  );
  const chart = node('div', undefined, 'scroll');
  chart.tabIndex = 0;
  chart.setAttribute('role', 'region');
  chart.setAttribute('aria-label', 'Personal study-set coverage chart');
  chart.append(
    PositionCharts.line(
      [
        {
          name: 'Selected White games',
          points: result.coverage.map((p) => ({ x: p.n, y: p.share || 0 })),
        },
      ],
      'Coverage of selected published study positions in imported White games',
      'Number of reference positions',
    ),
  );
  if (result.denominator_games) output.append(chart);
  output.append(
    table(
      ['Reference positions', 'Covered games', 'Coverage', 'Additional games'],
      result.coverage.map((p) => [
        String(p.n),
        number(p.games),
        percent(p.share),
        number(p.additional_games),
      ]),
    ),
  );
  output.append(node('h3', 'Selected route examples and later convergence'));
  output.append(
    node(
      'p',
      `${number(result.leaves_selected_routes_games)} games leave the selected route examples within 20 plies; ${number(result.reenters_reference_games)} later reach a selected reference board. This bounded set contains only published routes, not every known opening line. A departure is not a mistake or an engine assessment.`,
    ),
  );
  if (result.first_departures.length)
    output.append(
      table(
        ['First departure ply', 'Games'],
        result.first_departures.map((p) => [String(p.ply), number(p.games)]),
      ),
    );
  output.append(node('h3', 'Most frequent boards in your selected games'));
  if (!result.positions.length) {
    output.append(node('p', 'No selected games reach the White decision window.'));
    return;
  }
  const detail = node('div', undefined, 'import-position-detail');
  detail.id = 'import-position-detail';
  detail.tabIndex = -1;
  function selectPosition(position) {
    const title = node(
      'h4',
      `${number(position.games)} games · ${percent(position.frequency)} of selected White games`,
    );
    detail.replaceChildren(title, board(position.position_key));
    detail.append(
      node(
        'p',
        `${number(position.acyclic_routes)} acyclic routes; ${percent(position.alternative_route_share)} alternative-route share; ${number(position.loops)} repetition-prefix arrivals. ${position.in_reference ? 'In the selected public study set.' : 'Not in this selected set; broader reference coverage has not been checked.'}`,
      ),
    );
    const list = node('ol');
    position.routes.forEach((route) => {
      const item = node('li');
      item.append(
        node('code', route.san),
        node('small', `${number(route.games)} games · ${percent(route.share)} of position games`),
      );
      list.append(item);
    });
    detail.append(list, node('code', position.position_key));
  }
  const rows = result.positions.map((position, i) => {
    const cell = node('td');
    const button = node('button', `Inspect board ${i + 1}`);
    button.type = 'button';
    button.setAttribute('aria-controls', detail.id);
    button.addEventListener('click', () => {
      selectPosition(position);
      detail.focus({ preventScroll: true });
      detail.scrollIntoView({ block: 'start' });
    });
    cell.append(button);
    return [
      cell,
      number(position.games),
      percent(position.frequency),
      number(position.acyclic_routes),
      position.in_reference ? 'Yes' : 'Not in selected set',
    ];
  });
  output.append(table(['Board', 'Games', 'Frequency', 'Routes', 'Reference match'], rows), detail);
  selectPosition(result.positions[0]);
}

el('files').addEventListener('change', (event) => {
  const files = [...event.target.files];
  if (!files.length) return;
  startWorker(false);
  worker.postMessage({ type: 'import', files });
});
el('example').addEventListener('click', () => {
  startWorker(true);
  worker.postMessage({ type: 'example', file: example });
});
el('cancel').addEventListener('click', () =>
  clearSession('Import canceled. No partial analysis was kept.'),
);
el('clear').addEventListener('click', () => clearSession());
el('analyze').addEventListener('click', analyze);
el('cohort').addEventListener('change', updateReferenceViews);
['view', 'kind', 'n', 'since', 'until', 'rated', 'time-control', 'minimum20'].forEach((id) => {
  el(id).addEventListener('change', () => {
    invalidate();
    available();
  });
});
el('download').addEventListener('click', () => {
  if (!report) return;
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  downloadUrl = URL.createObjectURL(
    new Blob([`${JSON.stringify(report, null, 2)}\n`], { type: 'application/json' }),
  );
  const link = node('a');
  link.href = downloadUrl;
  link.download = 'my-opening-analysis.json';
  link.click();
});
window.addEventListener('pagehide', () => {
  if (worker) worker.terminate();
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
});
updateReferenceViews();
available();
