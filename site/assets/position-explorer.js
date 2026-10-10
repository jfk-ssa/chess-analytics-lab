'use strict';

async function initializePositions() {
  const root = document.getElementById('position-explorer');
  if (!root) return;
  const el = id => document.getElementById(`position-${id}`);
  const number = n => n.toLocaleString('en-US');
  const percent = n => `${(100 * n).toFixed(2)}%`;
  const node = (tag, text, className) => {
    const result = document.createElement(tag);
    if (text !== undefined) result.textContent = text;
    if (className) result.className = className;
    return result;
  };
  function table(headers, rows) {
    const result = node('table');
    const head = node('thead');
    const heading = node('tr');
    headers.forEach(title => {
      const cell = node('th', title);
      cell.scope = 'col';
      heading.append(cell);
    });
    head.append(heading);
    const body = node('tbody');
    rows.forEach(values => {
      const row = node('tr');
      values.forEach((value, index) => row.append(node('td', value, index ? 'number' : '')));
      body.append(row);
    });
    result.append(head, body);
    const wrap = node('div', undefined, 'scroll position-inventory-table');
    wrap.tabIndex = 0;
    wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', headers.join(', '));
    wrap.append(result);
    return wrap;
  }
  try {
    const response = await fetch('assets/opening-positions.json');
    if (!response.ok) throw new Error('Rankings could not be loaded');
    const data = await response.json();
    const cohortSelect = el('cohort');
    const familySelect = el('family');
    const kindSelect = el('kind');
    let view;
    let selectedId;
    function selectPosition(id) {
      selectedId = id;
      const position = view.positions[id];
      const routes = position.routes;
      const moveNumber = routes.length ? routes[0].uci.split(' ').length / 2 : null;
      el('selected-title').textContent = `Position ${view.rankings[kindSelect.value].ids.indexOf(id) + 1} · White to move`;
      el('image').src = `assets/opening-positions/${id}.svg`;
      el('image').alt = `White decision position ${id}; common arrival after Black's move ${moveNumber}`;
      el('selected-note').textContent = `${number(position.games)} games · ${percent(position.frequency)} of this view · ${number(position.acyclic_routes)} distinct move orders without loops.`;
      const content = el('selected-content');
      content.replaceChildren(node('h4', 'Common arrival routes'));
      const list = node('ol', undefined, 'position-routes');
      routes.forEach(route => {
        const item = node('li');
        item.append(node('code', route.san), node('small', `${number(route.games)} games · ${percent(route.share)} of position games`));
        list.append(item);
      });
      if (!routes.length) list.append(node('li', 'All observed arrival prefixes contain a repeated position.'));
      content.append(list, node('p', `Showing up to three routes. ${number(position.loop_prefix_games)} games have a repeated-position arrival prefix; those prefixes do not add move orders.`, 'source-note'));
      content.append(node('h4', 'Observed White continuations'));
      content.append(table(['Move', 'Games', 'Share of position games'], position.continuations.map(move => [move.san, number(move.games), percent(move.share_of_position_games)])));
      content.append(node('p', `Showing up to five moves. ${number(position.next_move_games)} of ${number(position.games)} games have a recorded next move. Frequency describes choices, not move quality.`, 'source-note'));
      content.append(node('h4', 'Recorded opening labels'));
      const labels = node('ul');
      position.opening_labels.forEach(label => labels.append(node('li', `${label.family} · ${label.eco || 'ECO unknown'} · ${number(label.games)} games`)));
      content.append(labels, node('p', 'Top five family/ECO labels in this view. Several labels can reach one exact board.', 'source-note'));
      const key = node('details');
      key.append(node('summary', 'Exact position key'), node('code', position.position_key));
      content.append(key);
      root.querySelectorAll('[data-position]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.position === id)));
    }
    function updateView() {
      const cohort = data.cohorts[cohortSelect.value];
      view = cohort.views[familySelect.value];
      const ranking = view.rankings[kindSelect.value];
      const denominator = view.denominator_games;
      const cohortName = cohortSelect.value === 'elite_reference' ? 'Elite reference' : 'Public 1000+';
      const scope = familySelect.value === 'all' ? 'all openings' : familySelect.value;
      const title = kindSelect.value === 'transposing' ? 'transposing' : 'recurring';
      el('caption').textContent = `Top ${ranking.ids.length} ${title} positions · ${cohortName} · ${scope}`;
      el('status').textContent = `${number(denominator)} eligible games in this view. Top 10 reach ${number(ranking.top_10_game_coverage)} (${percent(ranking.top_10_game_coverage / denominator)}); top 20 reach ${number(ranking.top_20_game_coverage)} (${percent(ranking.top_20_game_coverage / denominator)}). Coverage counts each game once across the selected set.`;
      el('scope').textContent = `${number(view.distinct_positions)} distinct boards, ${number(view.recurring_positions)} recurring, ${number(view.transposing_positions)} with multiple move orders. Every table frequency uses ${number(denominator)} ${scope === 'all openings' ? 'cohort' : 'recorded-family'} games. Opening labels describe games; the exact board defines a position.`;
      const body = el('rows');
      body.replaceChildren();
      ranking.ids.forEach((id, index) => {
        const position = view.positions[id];
        const row = node('tr');
        const arrival = node('td');
        const route = position.routes[0];
        const button = node('button', route ? `After Black's move ${route.uci.split(' ').length / 2}` : 'Inspect board');
        button.type = 'button';
        button.dataset.position = id;
        button.setAttribute('aria-label', `Inspect position ${index + 1}, ${number(position.games)} games`);
        button.setAttribute('aria-controls', 'position-detail');
        button.addEventListener('click', () => {
          selectPosition(id);
          if (window.matchMedia('(max-width:900px)').matches) {
            el('detail').focus({preventScroll: true});
            el('detail').scrollIntoView({block: 'start'});
          }
        });
        arrival.append(button, node('small', position.opening_labels[0]?.family || 'Unknown opening', 'position-label'));
        row.append(node('td', String(index + 1)), arrival, node('td', number(position.games), 'number'), node('td', percent(position.frequency), 'number'), node('td', number(position.acyclic_routes), 'number'));
        body.append(row);
      });
      if (ranking.ids.length) {
        el('detail').hidden = false;
        selectPosition(ranking.ids.includes(selectedId) ? selectedId : ranking.ids[0]);
      } else {
        el('detail').hidden = true;
        const row = node('tr');
        const cell = node('td', 'No eligible positions in this view.');
        cell.colSpan = 5;
        row.append(cell);
        body.append(row);
      }
      el('inventory').replaceChildren(node('h3', `${cohortName} · all recorded families`), table(['Family', 'Games', 'Cohort share'], cohort.opening_families.map(family => [family.family, number(family.games), percent(family.share)])));
      el('compression').replaceChildren(node('h3', `${cohortName} · convergence by depth across all openings`), table(['After Black move', 'Distinct routes', 'Distinct positions', 'Endpoint compression'], cohort.compression_by_ply.map(row => [String(row.ply / 2), number(row.distinct_routes), number(row.distinct_positions), percent(row.endpoint_compression)])));
    }
    function updateCohort() {
      const family = familySelect.value;
      familySelect.replaceChildren();
      Object.entries(data.cohorts[cohortSelect.value].views).forEach(([name, details]) => {
        const option = node('option', name === 'all' ? 'All openings' : `${name} · ${number(details.denominator_games)}`);
        option.value = name;
        familySelect.append(option);
      });
      familySelect.value = data.cohorts[cohortSelect.value].views[family] ? family : 'all';
      selectedId = null;
      updateView();
    }
    cohortSelect.addEventListener('change', updateCohort);
    familySelect.addEventListener('change', updateView);
    kindSelect.addEventListener('change', updateView);
    updateCohort();
    el('controls').hidden = false;
    el('load-note').textContent = 'Select a row to inspect its board, arrival routes and observed continuations.';
  } catch (error) {
    el('load-note').textContent = 'Interactive rankings could not load. The static Elite summary and JSON download remain available.';
    console.error(error);
  }
}

initializePositions();
