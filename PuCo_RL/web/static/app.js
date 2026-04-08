const goodsMap = {0: "☕ Coffee", 1: "🚬 Tobacco", 2: "🌽 Corn", 3: "🪵 Sugar", 4: "🫐 Indigo", 5: "None"};
const iconMap = {0: "☕", 1: "🚬", 2: "🌽", 3: "🪵", 4: "🫐", 5: "🪨", 6: "⬜"};
const tileMap = {0: "Coffee", 1: "Tobacco", 2: "Corn", 3: "Sugar", 4: "Indigo", 5: "Quarry", 6: "Empty"};
const phaseMap = {0: "SETTLER", 1: "MAYOR", 2: "BUILDER", 3: "CRAFTSMAN", 4: "TRADER", 5: "CAPTAIN", 6: "CAPTAIN_STORE", 7: "PROSPECTOR", 8: "END_ROUND", 9: "INIT"};
const buildingMap = [
    "Sm Indigo", "Sm Sugar", "Indigo Plant", "Sugar Mill", 
    "Tobacco Storage", "Coffee Roaster", "Sm Market", "Hacienda", 
    "Const. Hut", "Sm Warehouse", "Hospice", "Office", 
    "Lg Market", "Lg Warehouse", "Factory", "University", 
    "Harbor", "Wharf", "Guildhall", "Residence", "Fortress", 
    "Customs House", "City Hall", "Empty", "Occupied Space"
];

let polling = false;
let actionLock = false;

document.getElementById('start-btn').addEventListener('click', async () => {
    if (actionLock) return;
    actionLock = true;
    
    const s0 = document.getElementById('seat0').value;
    const s1 = document.getElementById('seat1').value;
    const s2 = document.getElementById('seat2').value;
    
    document.getElementById('start-btn').innerText = "Initializing...";
    
    try {
        const res = await fetch('/api/start', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({seat_0: s0, seat_1: s1, seat_2: s2})
        });
        
        if (res.ok) {
            document.getElementById('setup-screen').classList.add('hidden');
            document.getElementById('board-screen').classList.remove('hidden');
            document.getElementById('error-banner').classList.add('hidden');
            actionLock = false;
            pollState();
        } else {
            alert("Failed to start server");
            document.getElementById('start-btn').innerText = "Initialize Simulation";
            actionLock = false;
        }
    } catch(e) {
        alert("Server connection failed.");
        document.getElementById('start-btn').innerText = "Initialize Simulation";
        actionLock = false;
    }
});

async function pollState() {
    if (polling) return;
    polling = true;
    try {
        const res = await fetch('/api/state');
        const data = await res.json();
        if (data.started) {
            renderState(data);
        }
    } catch (e) {
        console.error(e);
    }
    polling = false;
    // Don't poll aggressively if game is over
    if (document.getElementById('error-banner').classList.contains('hidden')) {
        setTimeout(pollState, 800);
    }
}

async function sendAction(actionId) {
    if (actionLock) return;
    actionLock = true;
    
    document.getElementById('action-buttons').innerHTML = `
        <button class="action-btn" disabled style="text-align:center; color: var(--text-muted);">
            ⏳ Executing action...
        </button>
    `;
    
    try {
        await fetch('/api/step', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: actionId})
        });
    } catch (e) {
        console.error("Action error:", e);
    }
    actionLock = false;
}

function renderState(data) {
    // Check Error
    if (data.is_game_over && data.error_msg) {
        const errBanner = document.getElementById('error-banner');
        errBanner.innerHTML = `⚠️ <strong>CRITICAL FAULT:</strong> Engine terminated the environment.<br><span style="font-size:0.9rem; font-family:monospace; margin-top:5px; display:block;">Trace: ${data.error_msg}</span>`;
        errBanner.classList.remove('hidden');
    }

    // Phase & Top Info
    const g = data.global_state;
    document.getElementById('current-phase-label').innerText = phaseMap[g.current_phase];
    document.getElementById('current-round-label').innerText = `Round: ${data.round_number}`;
    
    document.getElementById('current-player-label').innerHTML = `🧑‍🚀 ${data.current_player.replace('_',' ')} (${data.seat_map[data.current_player]})`;
    document.getElementById('governor-label').innerHTML = `👑 ${data.governor.replace('_',' ')}`;
    
    // Global
    document.getElementById('g-vp').innerText = g.vp_chips;
    document.getElementById('g-col').innerText = `${g.colonists_supply} / ${g.colonists_ship}`;
    
    // Ships
    const shipsArr = [];
    for (let i = 0; i < 3; i++) {
        const goodId = g.cargo_ships_good[i];
        const load = g.cargo_ships_load[i];
        if (goodId === 5 || load === 0) {
            shipsArr.push(`🚢 Empty`);
        } else {
            shipsArr.push(`🚢 ${load}x ${iconMap[goodId]}`);
        }
    }
    document.getElementById('g-ships').innerHTML = shipsArr.join(' &nbsp;|&nbsp; ');

    const tradeHouse = g.trading_house.filter(x => x !== 5).map(x => goodsMap[x]).join(", ") || "Empty";
    document.getElementById('g-trade').innerText = tradeHouse;
    
    const faceUp = g.face_up_plantations.filter(x => x !== 6).map(x => `${iconMap[x]} ${tileMap[x]}`).join(", ") || "None";
    document.getElementById('g-plant').innerText = faceUp;
    
    // Players
    const container = document.getElementById('players-container');
    container.innerHTML = '';
    
    for (let i = 0; i < 3; i++) {
        const pKey = `player_${i}`;
        const pState = data.players[pKey];
        const isCurrent = (pKey === data.current_player);
        const name = `${pKey.replace('_',' ')} <span style="font-size:0.8rem; color:var(--text-muted); font-weight:normal;">[${data.seat_map[pKey]}]</span>`;
        
        let islandHtml = pState.island_tiles.map((t, idx) => {
            if (t === 6) return '';
            const occupied = pState.island_occupied[idx] === 1;
            return `<div class="item-chip ${occupied ? 'occupied' : ''}">
                        ${iconMap[t]} ${tileMap[t]} ${occupied ? '👨' : ''}
                    </div>`;
        }).join('');
        
        let cityHtml = pState.city_buildings.map((b, idx) => {
            if (b >= 23) return ''; 
            const cols = pState.city_colonists[idx];
            return `<div class="item-chip ${cols > 0 ? 'occupied' : ''}">
                        🏗️ ${buildingMap[b]} ${cols > 0 ? `(${cols}👨)` : ''}
                    </div>`;
        }).join('');
        
        const goodCounts = [];
        for (let gIdx=0; gIdx<5; gIdx++) {
            if (pState.goods[gIdx] > 0) goodCounts.push(`${pState.goods[gIdx]}x ${iconMap[gIdx]}`);
        }
        
        const html = `
            <div class="player-board ${isCurrent && !data.is_game_over ? 'active-player' : ''}">
                <div class="player-name">${name}</div>
                <div class="player-resources">
                    <div class="badge">💰 ${pState.doubloons}</div>
                    <div class="badge">🎖️ ${pState.vp_chips}</div>
                    <div class="badge">👨 U: ${pState.unplaced_colonists}</div>
                </div>
                <div style="font-size:0.9rem; margin-bottom: 8px;">
                    <strong>Inventory:</strong> ${goodCounts.join(', ') || '<span style="color:var(--text-muted)">Empty</span>'}
                </div>
                
                <div class="grid-area">
                    <div class="grid-title">Island Board</div>
                    <div class="items-flex">${islandHtml || '<span style="color:var(--text-muted); font-size:0.85rem;">Empty</span>'}</div>
                </div>
                
                <div class="grid-area">
                    <div class="grid-title">City Board</div>
                    <div class="items-flex">${cityHtml || '<span style="color:var(--text-muted); font-size:0.85rem;">Empty</span>'}</div>
                </div>
            </div>
        `;
        container.innerHTML += html;
    }
    
    // Action panel
    const btnContainer = document.getElementById('action-buttons');
    if (data.is_game_over) {
        if (!data.error_msg) {
             btnContainer.innerHTML = '<div style="color: var(--success); font-weight: bold; text-align:center; padding:10px;">🎉 Game Finished Naturally!</div>';
        } else {
             btnContainer.innerHTML = '<div style="color: var(--danger); font-weight: bold; text-align:center; padding:10px;">🛑 Halted due to Error</div>';
        }
    } else if (data.is_human_turn) {
        if (!actionLock) {
            btnContainer.innerHTML = '';
            data.human_actions.forEach(a => {
                const btn = document.createElement('button');
                btn.className = 'action-btn';
                btn.innerText = `👉 ${a.text}`;
                btn.onclick = () => sendAction(a.id);
                btnContainer.appendChild(btn);
            });
        }
    } else {
        btnContainer.innerHTML = `<div style="text-align:center; padding:10px; color: var(--text-muted);">
            ⏳ Waiting for ${data.current_player} (${data.seat_map[data.current_player]})...
        </div>`;
    }
    
    // PPO Insights
    document.getElementById('ppo-value').innerText = `Value Approx: ${data.ppo_insights.value}`;
    const probsBody = document.getElementById('ppo-probs-body');
    probsBody.innerHTML = '';
    
    if (data.ppo_insights.probabilities.length === 0) {
        probsBody.innerHTML = '<div style="font-size: 0.85rem; color: var(--text-muted);">Awaiting PPO inference...</div>';
    } else {
        data.ppo_insights.probabilities.slice(0, 5).forEach(p => {
            const pctText = (p.prob * 100).toFixed(1) + '%';
            const pctHtml = `
            <div style="margin-bottom: 6px;">
                <div style="display:flex; justify-content:space-between; margin-bottom: 2px; font-size:0.8rem; color: #cbd5e1;">
                    <span>${p.text}</span>
                    <span>${pctText}</span>
                </div>
                <div class="insight-bar-container">
                    <div class="insight-bar-fill" style="width: ${p.prob * 100}%"></div>
                </div>
            </div>`;
            probsBody.innerHTML += pctHtml;
        });
    }
    
    // Log
    const logList = document.getElementById('log-list');
    logList.innerHTML = '';
    data.action_log.slice().reverse().forEach(log => {
        const li = document.createElement('li');
        li.innerText = log;
        logList.appendChild(li);
    });
}
