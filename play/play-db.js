/**
 * Sanskrit Digital Library - Play Database API Helper
 */

const API_BASE = '/api/v1';

async function getSynonymSets() {
    try {
        const res = await fetch(`${API_BASE}/play/synonym-match/sets`);
        return await res.json();
    } catch (e) {
        console.error("Error fetching synonym sets:", e);
        return { success: false, error: e.message };
    }
}

async function getSynonymSet(id) {
    try {
        const res = await fetch(`${API_BASE}/play/synonym-match/sets/${id}`);
        return await res.json();
    } catch (e) {
        console.error(`Error fetching synonym set ${id}:`, e);
        return { success: false, error: e.message };
    }
}

async function getWordBuilderSets() {
    try {
        const res = await fetch(`${API_BASE}/play/word-builder/sets`);
        return await res.json();
    } catch (e) {
        console.error("Error fetching word builder sets:", e);
        return { success: false, error: e.message };
    }
}

async function getWordBuilderSet(id) {
    try {
        const res = await fetch(`${API_BASE}/play/word-builder/sets/${id}`);
        return await res.json();
    } catch (e) {
        console.error(`Error fetching word builder set ${id}:`, e);
        return { success: false, error: e.message };
    }
}

async function getWordSearchSets() {
    try {
        const res = await fetch(`${API_BASE}/play/word-search/sets`);
        return await res.json();
    } catch (e) {
        console.error("Error fetching word search sets:", e);
        return { success: false, error: e.message };
    }
}

async function getWordSearchSet(id) {
    try {
        const res = await fetch(`${API_BASE}/play/word-search/sets/${id}`);
        return await res.json();
    } catch (e) {
        console.error(`Error fetching word search set ${id}:`, e);
        return { success: false, error: e.message };
    }
}

async function saveGameResult(gameType, setId, setTitle, score, total, percentage, timeTaken) {
    try {
        const res = await fetch(`${API_BASE}/play/results`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                game_type: gameType,
                set_id: parseInt(setId),
                set_title: setTitle,
                score: parseInt(score),
                total: parseInt(total),
                percentage: parseInt(percentage),
                time_taken: timeTaken !== null ? parseInt(timeTaken) : null
            })
        });
        return await res.json();
    } catch (e) {
        console.error("Error saving game result:", e);
        return { success: false, error: e.message };
    }
}
