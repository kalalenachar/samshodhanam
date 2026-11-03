// db.js - Client-Side Database & Business Logic for QuizMaster
// Questions are stored in SQLite on the server, fetched via API.

const API_BASE = '/api/v1';

// Get all questions from the server API
async function getQuestions(subject = '', level = '', isAdmin = false) {
  if (typeof subject === 'boolean') {
    isAdmin = subject;
    subject = '';
    level = '';
  }

  try {
    let url = `${API_BASE}/quiz/questions`;
    const params = [];
    if (subject) params.push(`subject=${encodeURIComponent(subject)}`);
    if (level) params.push(`level=${encodeURIComponent(level)}`);
    if (params.length > 0) {
      url += '?' + params.join('&');
    }

    const res = await fetch(url);
    if (!res.ok) throw new Error('API request failed');
    const data = await res.json();
    if (data.success && data.questions) {
      const questions = data.questions;
      // Store in sessionStorage for the active exam session (candidate scoring)
      if (!isAdmin) {
        sessionStorage.setItem('quiz_candidate_questions', JSON.stringify(questions));
      }
      return questions;
    }
    throw new Error(data.error || 'Unknown API error');
  } catch (err) {
    console.error('Error fetching questions from API:', err);
    return [];
  }
}

// Calculate unique subjects, levels and count maps
function getSubjectsAndLevels(questions) {
  const map = {};
  for (const q of questions) {
    const s = q.subject || 'General';
    const l = q.level || 'Default';
    if (!map[s]) {
      map[s] = new Set();
    }
    map[s].add(l);
  }
  
  const subjects = Object.keys(map).sort();
  const levels = {};
  for (const s of subjects) {
    levels[s] = Array.from(map[s]).sort();
  }
  
  const counts = {};
  for (const q of questions) {
    const key = `${q.subject || 'General'}|||${q.level || 'Default'}`;
    counts[key] = (counts[key] || 0) + 1;
  }
  
  return { subjects, levels, counts };
}

// Localize helper to extract language-specific fields or fall back gracefully
function loc(field, lang) {
  if (!field) return '';
  if (typeof field === 'string') return field;
  return field[lang] || field['en'] || Object.values(field)[0] || '';
}

// Randomize array elements (Fisher-Yates shuffle)
function shuffleArray(a) {
  const s = [...a];
  for (let i = s.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [s[i], s[j]] = [s[j], s[i]];
  }
  return s;
}

// Score and compile quiz results client-side
function calculateResults(name, answers, subject, level, lang) {
  const chosenLang = lang || 'en';
  
  // Try to retrieve the exact subset of questions presented to the candidate
  const activeQsRaw = sessionStorage.getItem('active_quiz_questions');
  let filtered = [];
  if (activeQsRaw) {
    filtered = JSON.parse(activeQsRaw);
  } else {
    // Retrieve the exact questions the candidate fetched on load
    const rawQs = sessionStorage.getItem('quiz_candidate_questions') || '[]';
    const allQs = JSON.parse(rawQs);
    
    // Filter questions by subject and level
    filtered = allQs;
    if (subject) {
      filtered = filtered.filter(q => (q.subject || 'General') === subject);
    }
    if (level) {
      filtered = filtered.filter(q => (q.level || 'Default') === level);
    }
  }
  
  let score = 0;
  const results = [];
  
  for (const q of filtered) {
    const userIdx = answers[q.id]; // User's answer index (0-3) or null
    const isCorrect = userIdx !== null && userIdx !== undefined && parseInt(userIdx) === q.answerIndex;
    if (isCorrect) {
      score++;
    }
    
    // Extract strings localized for the candidate
    const qText = loc(q.question, chosenLang);
    const opts = Array.isArray(q.options) ? q.options : (q.options[chosenLang] || q.options['en'] || []);
    const expl = loc(q.explanation, chosenLang);
    
    const isSkipped = userIdx === null || userIdx === undefined;
    results.push({
      id: q.id,
      question: qText,
      options: opts,
      correctAnswer: opts[q.answerIndex] || '',
      userAnswer: !isSkipped ? opts[parseInt(userIdx)] : null,
      isCorrect,
      isSkipped,
      explanation: expl
    });
  }
  
  return {
    name,
    subject: subject || 'General',
    level: level || 'Default',
    score,
    total: filtered.length,
    percentage: filtered.length > 0 ? Math.round((score / filtered.length) * 100) : 0,
    results
  };
}
