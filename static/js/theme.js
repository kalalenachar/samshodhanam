(function () {
  function getSavedTheme() {
    try {
      var t = localStorage.getItem('smsdl-theme');
      if (!t) {
        var match = document.cookie.match(new RegExp('(^| )smsdl-theme=([^;]+)'));
        if (match) t = match[2];
      }
      return t || 'light';
    } catch (e) {
      try {
        var match = document.cookie.match(new RegExp('(^| )smsdl-theme=([^;]+)'));
        if (match) return match[2] || 'light';
      } catch (err) { }
      return 'light';
    }
  }

  function saveTheme(theme) {
    try {
      localStorage.setItem('smsdl-theme', theme);
    } catch (e) { }
    try {
      document.cookie = "smsdl-theme=" + theme + "; path=/; max-age=31536000; SameSite=Lax";
    } catch (e) { }
  }

  // Anti-FOUC (Flash of Unfocused Content) check
  const savedTheme = getSavedTheme();
  document.documentElement.setAttribute('data-theme', savedTheme);

  // ── Theme cycle order ──
  const THEMES = ['dark', 'light', 'sunset', 'nature', 'sepia', 'ocean', 'synthwave'];

  // ── SVG icons for each theme (shown when that theme is ACTIVE) ──
  const THEME_ICONS = {
    dark: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>`,
    light: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>`,
    sunset: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 18a5 5 0 0 0-10 0"></path><line x1="12" y1="2" x2="12" y2="9"></line><line x1="4.22" y1="10.22" x2="5.64" y2="11.64"></line><line x1="1" y1="18" x2="3" y2="18"></line><line x1="21" y1="18" x2="23" y2="18"></line><line x1="18.36" y1="11.64" x2="19.78" y2="10.22"></line><line x1="23" y1="22" x2="1" y2="22"></line><polyline points="8 5 12 9 16 5"></polyline></svg>`,
    nature: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 8c0 6-4.5 10-10.5 11"></path><path d="M7 19c0 0 0-3 2-6"></path><path d="M17 8c.7-1 2.2-2 4-2 0 4.5-2.5 8-7 10"></path><path d="M7 19c-2 0-4-.5-5-2 2.5-2 5.5-3 9-3"></path></svg>`,
    sepia: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path><line x1="8" y1="7" x2="16" y2="7"></line><line x1="8" y1="11" x2="13" y2="11"></line></svg>`,
    ocean: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12c2-2 4-3 6-3s4 1 6 3 4 3 6 3 4-1 6-3"></path><path d="M2 17c2-2 4-3 6-3s4 1 6 3 4 3 6 3 4-1 6-3"></path><path d="M2 7c2-2 4-3 6-3s4 1 6 3 4 3 6 3 4-1 6-3"></path></svg>`,
    synthwave: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>`
  };

  // ── Human-readable labels ──
  const THEME_LABELS = {
    dark: 'Dark',
    light: 'Light',
    sunset: 'Sunset',
    nature: 'Nature',
    sepia: 'Sepia',
    ocean: 'Ocean',
    synthwave: 'Synthwave'
  };

  let labelTimeout = null;

  function getNextTheme(current) {
    const idx = THEMES.indexOf(current);
    return THEMES[(idx + 1) % THEMES.length];
  }

  function showLabel(label, themeName) {
    label.textContent = THEME_LABELS[themeName] || themeName;
    label.classList.add('visible');
    clearTimeout(labelTimeout);
    labelTimeout = setTimeout(() => {
      label.classList.remove('visible');
    }, 1500);
  }

  function initThemeToggle() {
    // Avoid double initialization
    if (document.getElementById('theme-toggle-btn')) return;

    // Do not initialize theme toggle on articles reader page
    if (window.SMSDL_NO_THEME_TOGGLE || window.location.pathname.includes('/articles/reader')) {
      return;
    }

    const btn = document.createElement('button');
    btn.id = 'theme-toggle-btn';
    btn.className = 'theme-toggle-btn';
    btn.setAttribute('aria-label', 'Switch theme');

    // Theme name label element
    const label = document.createElement('div');
    label.className = 'theme-label';
    label.id = 'theme-label';

    // Set initial icon based on current theme
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    btn.innerHTML = THEME_ICONS[currentTheme] || THEME_ICONS.light;

    btn.addEventListener('click', function () {
      const activeTheme = document.documentElement.getAttribute('data-theme') || 'light';
      const newTheme = getNextTheme(activeTheme);

      // Add transition class to enable smooth transition of all components
      document.documentElement.classList.add('theme-transitioning');

      document.documentElement.setAttribute('data-theme', newTheme);
      saveTheme(newTheme);

      // Show theme name label
      showLabel(label, newTheme);

      // Update button icon with transition
      const svg = btn.querySelector('svg');
      if (svg) {
        svg.style.transform = 'rotate(360deg) scale(0)';
      }

      setTimeout(() => {
        btn.innerHTML = THEME_ICONS[newTheme] || THEME_ICONS.light;
        const newSvg = btn.querySelector('svg');
        if (newSvg) {
          newSvg.style.transform = 'rotate(0deg) scale(1)';
        }
      }, 150);

      // Remove transition class after the transition finishes (matching CSS transition duration)
      setTimeout(() => {
        document.documentElement.classList.remove('theme-transitioning');
      }, 350);
    });

    document.body.appendChild(btn);
    document.body.appendChild(label);
  }

  function initGlobalPadacheda() {
    if (document.getElementById('global-padacheda-btn')) return;

    // Inject stylesheet styles
    const style = document.createElement('style');
    style.textContent = `
      @keyframes modalPop {
        from { transform: scale(0.95); opacity: 0; }
        to { transform: scale(1); opacity: 1; }
      }
      .padacheda-word-pill {
        display: inline-block;
        background: rgba(16, 185, 129, 0.1);
        border: 1px solid rgba(16, 185, 129, 0.3);
        color: #10b981;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 15px;
        font-weight: 700;
        margin: 4px;
      }
      .padacheda-rule-row {
        background: rgba(255,255,255,0.02);
        border: 1px solid var(--t-border);
        border-radius: 10px;
        padding: 10px 14px;
        margin-bottom: 8px;
        font-size: 14px;
      }
      #global-padacheda-btn:hover {
        transform: scale(1.05);
        box-shadow: 0 6px 20px rgba(0,0,0,0.4) !important;
      }
    `;
    document.head.appendChild(style);

    // Create selection floating button
    const btn = document.createElement('button');
    btn.id = 'global-padacheda-btn';
    btn.innerHTML = '✂️ Padacheda';
    btn.style.position = 'absolute';
    btn.style.zIndex = '100000';
    btn.style.display = 'none';
    btn.style.background = 'var(--t-accent, #10b981)';
    btn.style.color = 'var(--t-text-on-accent, #0c1a2e)';
    btn.style.border = 'none';
    btn.style.borderRadius = '20px';
    btn.style.padding = '6px 14px';
    btn.style.fontSize = '13px';
    btn.style.fontWeight = '700';
    btn.style.cursor = 'pointer';
    btn.style.boxShadow = '0 4px 15px rgba(0,0,0,0.3)';
    btn.style.transition = 'all 0.2s ease';
    document.body.appendChild(btn);

    // Create selection modal
    const modal = document.createElement('div');
    modal.id = 'global-padacheda-modal';
    modal.style.position = 'fixed';
    modal.style.top = '0';
    modal.style.left = '0';
    modal.style.width = '100%';
    modal.style.height = '100%';
    modal.style.backgroundColor = 'rgba(0,0,0,0.6)';
    modal.style.backdropFilter = 'blur(8px)';
    modal.style.webkitBackdropFilter = 'blur(8px)';
    modal.style.zIndex = '1000000';
    modal.style.display = 'none';
    modal.style.alignItems = 'center';
    modal.style.justifyContent = 'center';
    modal.style.padding = '20px';
    modal.innerHTML = `
      <div class="padacheda-card" style="background: var(--t-bg-overlay, rgba(20,20,20,0.95)); border: 1px solid var(--t-border); border-radius: 20px; max-width: 600px; width: 100%; max-height: 85vh; overflow-y: auto; padding: 25px; box-shadow: 0 20px 50px rgba(0,0,0,0.5); display: flex; flex-direction: column; gap: 20px; animation: modalPop 0.3s cubic-bezier(0.16, 1, 0.3, 1);">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--t-border); padding-bottom: 12px;">
          <h2 style="font-size: 1.25rem; font-weight: 700; color: var(--t-accent); margin: 0; font-family: 'Outfit', sans-serif;">Padacheda (पद-च्छेदः)</h2>
          <button onclick="document.getElementById('global-padacheda-modal').style.display='none'" style="background: none; border: none; color: var(--t-text-secondary); font-size: 24px; cursor: pointer; line-height: 1;">✕</button>
        </div>
        <div id="padacheda-modal-content" style="color: var(--t-text-primary); font-size: 15px; line-height: 1.6; font-family: 'Inter', sans-serif;">
          <!-- Content -->
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    let selectedText = '';

    // Selection change listener
    document.addEventListener('mouseup', handleTextSelection);
    document.addEventListener('touchend', handleTextSelection);

    function handleTextSelection(e) {
      setTimeout(() => {
        const selection = window.getSelection();
        const text = selection.toString().trim();

        if (!text || (e.target.closest && e.target.closest('#global-padacheda-btn')) || (e.target.closest && e.target.closest('#global-padacheda-modal'))) {
          if (!text && e.target !== btn) {
            btn.style.display = 'none';
          }
          return;
        }

        const isSanskrit = /[\u0900-\u097F]/.test(text) || (text.length > 2 && /^[a-zA-Z\s\',.-]+$/.test(text));
        if (!isSanskrit) {
          btn.style.display = 'none';
          return;
        }

        selectedText = text;

        try {
          const range = selection.getRangeAt(0);
          const rect = range.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) {
            btn.style.left = `${rect.left + window.scrollX + (rect.width / 2) - 50}px`;
            btn.style.top = `${rect.top + window.scrollY - 38}px`;
            btn.style.display = 'block';
          }
        } catch (err) {
          btn.style.display = 'none';
        }
      }, 50);
    }

    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      btn.style.display = 'none';

      const content = document.getElementById('padacheda-modal-content');
      content.innerHTML = '<p style="text-align: center; color: var(--t-text-secondary); padding: 20px;">Analyzing sandhi splits and retrieving grammatical rules...</p>';
      modal.style.display = 'flex';

      try {
        const res = await fetch('/apps/api/sandhi/split_explain', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: selectedText })
        });
        const data = await res.json();

        if (data.success) {
          let html = `
            <div style="margin-bottom: 15px;">
              <div style="font-weight: 600; color: var(--t-text-secondary); margin-bottom: 4px; font-size: 13px;">Selected Text:</div>
              <div style="font-size: 1.15rem; font-weight: 700; color: var(--t-accent); font-family: 'Outfit', sans-serif;">"${data.original}"</div>
            </div>
          `;

          const alts = data.alternatives && data.alternatives.length > 0 ? data.alternatives : [data];

          alts.forEach((alt, index) => {
            let joinsHtml = '';
            if (alt.joins && alt.joins.length > 0) {
              joinsHtml = alt.joins.map(j => `
                <div class="padacheda-rule-row">
                  <strong style="color:var(--t-text-primary);">${j.word1} + ${j.word2} ➔ ${j.fused}</strong><br>
                  <span style="color:var(--t-accent); font-weight:600;">Rule:</span> ${j.rule} (${j.type})
                </div>
              `).join('');
            } else {
              joinsHtml = '<p style="font-size:14px; color:var(--t-text-muted); margin: 0;">No sandhi merges detected directly between consecutive words.</p>';
            }

            html += `
              <div style="margin-bottom: 25px; ${alts.length > 1 ? 'border: 1px solid rgba(255,255,255,0.1); padding: 15px; border-radius: 8px; background: rgba(0,0,0,0.2);' : ''}">
                ${alts.length > 1 ? `<h3 style="color: var(--t-accent); font-size: 16px; margin-bottom: 15px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px;">Valid Split Alternative ${index + 1}</h3>` : ''}
                
                <div style="margin-bottom: 15px;">
                  <div style="font-weight: 600; color: var(--t-text-secondary); margin-bottom: 8px; font-size: 13px;">Segmented Words (पदानि):</div>
                  <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--t-border); border-radius: 12px; padding: 12px; display: flex; flex-wrap: wrap; gap: 6px;">
                    ${alt.words.map(w => `<span class="padacheda-word-pill">${w}</span>`).join('')}
                  </div>
                </div>
                
                <div style="margin-bottom: 15px;">
                  <div style="font-weight: 600; color: var(--t-text-secondary); margin-bottom: 8px; font-size: 13px;">Rules Applied:</div>
                  <div>${joinsHtml}</div>
                </div>
              </div>
            `;
          });

          content.innerHTML = html;
        } else {
          content.innerHTML = `<p style="color:#ef4444; font-weight:600; text-align:center; padding:20px;">Error: ${data.error}</p>`;
        }
      } catch (err) {
        console.error(err);
        content.innerHTML = '<p style="color:#ef4444; font-weight:600; text-align:center; padding:20px;">Failed to connect to parser service.</p>';
      }
    });

    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.style.display = 'none';
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      initThemeToggle();
      initGlobalPadacheda();
    });
  } else {
    initThemeToggle();
    initGlobalPadacheda();
  }

  // Ensure Mobile Mode Blocker is loaded across all pages
  try {
    if (typeof window.__smsdlMobileBlockerLoaded === 'undefined') {
      var mobileScript = document.createElement('script');
      mobileScript.src = '/static/js/mobile-android.js?v=200';
      mobileScript.defer = true;
      (document.head || document.documentElement).appendChild(mobileScript);
    }
  } catch (e) {}

  // Ensure GitHub Launch controller is loaded across all pages
  try {
    if (typeof window.__smsdlGithubLaunchLoaded === 'undefined') {
      var ghScript = document.createElement('script');
      ghScript.src = '/static/js/github-launch.js?v=2';
      ghScript.defer = true;
      (document.head || document.documentElement).appendChild(ghScript);
    } else if (typeof window.initGithubLaunch === 'function') {
      window.initGithubLaunch();
    }
  } catch (e) {}
})();

