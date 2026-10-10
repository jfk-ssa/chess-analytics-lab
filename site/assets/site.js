'use strict';
function textNode(tag,text){const node=document.createElement(tag);node.textContent=text;return node;}
document.querySelectorAll('pre').forEach(pre=>{const b=textNode('button','Copy text');b.className='copy';b.type='button';b.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(pre.textContent);b.textContent='Copied';}catch{b.textContent='Select the text to copy';}setTimeout(()=>b.textContent='Copy text',2200);});pre.after(b);});
document.querySelectorAll('table').forEach(table=>{if(!table.parentElement.classList.contains('scroll')){const div=document.createElement('div');div.className='scroll';table.replaceWith(div);div.append(table);}});
document.querySelectorAll('a[href^="#stage-"]').forEach(a=>a.addEventListener('click',()=>{const d=document.getElementById(a.hash.slice(1));if(d)d.open=true;}));
const search=document.getElementById('definition-search');
if(search){search.addEventListener('input',()=>{let shown=0;const query=search.value.toLowerCase().trim();document.querySelectorAll('[data-definition]').forEach(card=>{card.hidden=!card.textContent.toLowerCase().includes(query);if(!card.hidden)shown++;});document.getElementById('search-status').textContent=`${shown} definitions or schemas shown`;});}
const missing=document.getElementById('missing-moves');
if(missing){function update(){const n=Number(missing.value);document.getElementById('missing-value').textContent=n;document.getElementById('proxy-rate').textContent='3 / 6 = 50.0%';document.getElementById('coverage-rate').textContent=`6 / ${6+n} = ${(600/(6+n)).toFixed(1)}%`;};missing.addEventListener('input',update);update();}
const raw=document.getElementById('routing-data');
if(raw){const data=JSON.parse(raw.textContent),cohort=document.getElementById('cohort'),threshold=document.getElementById('threshold');function update(){const rows=data[cohort.value],t=Number(threshold.value),body=document.getElementById('routing-rows');body.replaceChildren();let accepted=0,errors=0;rows.forEach(row=>{const take=row.probability>=t&&row.decisions!=='fallback';if(take){accepted++;if(row.decisions!==row.expected)errors++;}const tr=document.createElement('tr');[row.id,row.question,row.expected,row.rules,row.jev1||'Not measured',row.jev2||'Not measured',row.decisions,row.probability.toFixed(3),take?'Accept route':'Fallback'].forEach((v,i)=>{const td=textNode('td',v);if(i>=3&&i<=6&&v!=='Not measured')td.className=v===row.expected?'hit':'miss';tr.append(td);});body.append(tr);});document.getElementById('routing-status').textContent=`At ${t.toFixed(2)}: ${accepted}/${rows.length} routes accepted (${(100*accepted/rows.length).toFixed(1)}% coverage), ${errors} accepted routing errors, ${rows.length-accepted} fallbacks.`;};cohort.addEventListener('change',update);threshold.addEventListener('change',update);update();}

document.querySelectorAll("td").forEach(cell=>{if(/^\$?\d[\d.,%/]*(?:\s*\([\d.,%]+\))?$/.test(cell.textContent.trim()))cell.classList.add("number");});

const openingRaw = document.getElementById('opening-data');
if (openingRaw) {
  const example = JSON.parse(openingRaw.textContent);
  const route = document.getElementById('opening-route');
  const ply = document.getElementById('opening-ply');
  const previous = document.getElementById('opening-back');
  const next = document.getElementById('opening-next');
  function updateOpening() {
    const routeIndex = Number(route.value);
    const step = Number(ply.value);
    const chosen = example.routes[routeIndex];
    const state = chosen.states[step];
    const matches = example.routes[0].states[step].position_key ===
      example.routes[1].states[step].position_key;
    // SVG comes exclusively from the builder's fixed, legally replayed examples.
    document.getElementById('opening-board').innerHTML = state.svg;
    document.getElementById('opening-board').setAttribute('aria-label',
      `Opening board, ${chosen.name}, ${step} half-moves played, ${state.to_move} to move`);
    document.getElementById('opening-ply-value').textContent = `${step} / 6`;
    document.getElementById('opening-board-status').textContent =
      `${chosen.name} · ${step === 0 ? 'Initial position' : `Last move: ${state.san}`} · ${state.to_move} to move.`;
    document.getElementById('opening-match-title').textContent = step === 6 ?
      'Shared opening position' : matches ? 'Shared starting route' : 'Different positions so far';
    document.getElementById('opening-match-note').textContent = step === 6 ?
      'Both routes arrive at the same opening position. Candidate moves and plans can be studied together; full draw counters remain separate.' :
      matches ? 'These routes still share their initial position or first move. Continue to see the move orders diverge and converge.' :
      'The intermediate positions differ. Earlier opponent deviations and tactical checks need their own attention.';
    document.querySelectorAll('.route-card').forEach((card, index) => {
      card.toggleAttribute('data-active', index === routeIndex);
    });
    previous.disabled = step === 0;
    next.disabled = step === 6;
    ply.setAttribute('aria-valuetext', `${step} half-moves played, ${state.to_move} to move`);
  }
  route.addEventListener('change', updateOpening);
  ply.addEventListener('input', updateOpening);
  previous.addEventListener('click', () => {
    ply.value = Math.max(0, Number(ply.value) - 1);
    updateOpening();
  });
  next.addEventListener('click', () => {
    ply.value = Math.min(6, Number(ply.value) + 1);
    updateOpening();
  });
  updateOpening();
}
