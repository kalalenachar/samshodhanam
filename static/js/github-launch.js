/**
 * ═══════════════════════════════════════════════════════════════════════════
 * SAMSHODHANA MANDIRAM — GITHUB OPEN SOURCE LAUNCH & COUNTDOWN CONTROLLER
 * AIOC 2026 (All India Oriental Conference) Presentation & Unveiling
 * ═══════════════════════════════════════════════════════════════════════════
 * 
 * Target Launch: October 31, 2026 00:00:00 IST
 * Extended Window: 48 Hours Presentation Grace Period
 * 
 * NOTE: For academic & security protocol, no external repository URL is
 * exposed on the client before the official conference presentation.
 */

(function () {
  'use strict';

  // Prevent multiple initializations
  if (window.__smsdlGithubLaunchLoaded) return;
  window.__smsdlGithubLaunchLoaded = true;

  // ── Launch Timeline Constants ───────────────────────────────────────────
  // October 31, 2026 00:00:00 Indian Standard Time (UTC+05:30)
  const TARGET_LAUNCH_ISO = '2026-10-31T00:00:00+05:30';
  const TARGET_TIMESTAMP = new Date(TARGET_LAUNCH_ISO).getTime();
  const EXTENDED_WINDOW_HOURS = 48;
  const EXTENDED_WINDOW_MS = EXTENDED_WINDOW_HOURS * 60 * 60 * 1000;

  // SVG GitHub Octocat
  const GITHUB_SVG = `
    <svg class="github-octocat-svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
    </svg>
  `;

  let timerInterval = null;

  // ── Calculate State & Values ────────────────────────────────────────────
  function getLaunchStatus() {
    const now = Date.now();
    const diffToTarget = TARGET_TIMESTAMP - now;

    if (diffToTarget > 0) {
      // Phase 1: Countdown to Launch Date (Oct 31, 2026)
      return {
        phase: 'COUNTDOWN',
        msRemaining: diffToTarget,
        badgeText: 'Countdown to Launch',
        targetNote: 'Official Unveiling at AIOC: <strong>October 31, 2026</strong>',
        headline: 'Open Source Launch at AIOC 2026'
      };
    }

    const diffToExtended = (TARGET_TIMESTAMP + EXTENDED_WINDOW_MS) - now;
    if (diffToExtended > 0) {
      // Phase 2: Conference Day & 48-Hour Extended Presentation Window
      return {
        phase: 'EXTENDED_48H',
        msRemaining: diffToExtended,
        badgeText: 'AIOC Presentation in Progress',
        targetNote: '48-Hour Presentation Grace Period: <strong>Repository Unfreeze Active</strong>',
        headline: 'AIOC 2026 Presentation Underway'
      };
    }

    // Phase 3: Launch Window Concluded
    return {
      phase: 'CONCLUDED',
      msRemaining: 0,
      badgeText: 'Launch Window Reached',
      targetNote: 'Presentation Concluded: <strong>Public Release Finalization</strong>',
      headline: 'AIOC 2026 Presentation Concluded'
    };
  }

  // ── Live Countdown Calculation & DOM Update ─────────────────────────────
  function updateCountdownUI() {
    const status = getLaunchStatus();
    const ms = Math.max(0, status.msRemaining);

    const secondsTotal = Math.floor(ms / 1000);
    const days = Math.floor(secondsTotal / (3600 * 24));
    const hours = Math.floor((secondsTotal % (3600 * 24)) / 3600);
    const mins = Math.floor((secondsTotal % 3600) / 60);
    const secs = secondsTotal % 60;

    const elDays = document.getElementById('gh-val-days');
    const elHours = document.getElementById('gh-val-hours');
    const elMins = document.getElementById('gh-val-mins');
    const elSecs = document.getElementById('gh-val-secs');
    const elBadge = document.getElementById('gh-status-badge-text');
    const elNote = document.getElementById('gh-target-note');
    const elTitle = document.getElementById('gh-modal-main-title');

    const pad = (n) => String(n).padStart(2, '0');

    if (elDays) elDays.textContent = status.phase === 'EXTENDED_48H' ? '00' : String(days);
    if (elHours) elHours.textContent = status.phase === 'EXTENDED_48H' ? pad(Math.floor(secondsTotal / 3600)) : pad(hours);
    if (elMins) elMins.textContent = pad(mins);
    if (elSecs) elSecs.textContent = pad(secs);

    if (elBadge) elBadge.textContent = status.badgeText;
    if (elNote) elNote.innerHTML = status.targetNote;
    if (elTitle && status.headline) elTitle.textContent = status.headline;
  }

  // ── Create Modal Structure ──────────────────────────────────────────────
  function createLaunchModal() {
    if (document.getElementById('github-launch-backdrop')) return;

    const backdrop = document.createElement('div');
    backdrop.id = 'github-launch-backdrop';
    backdrop.className = 'github-launch-backdrop';
    backdrop.setAttribute('role', 'dialog');
    backdrop.setAttribute('aria-modal', 'true');
    backdrop.setAttribute('aria-labelledby', 'gh-modal-main-title');

    backdrop.innerHTML = `
      <div class="github-launch-modal" id="github-launch-card">
        <button type="button" class="github-modal-close-btn" id="gh-modal-close-btn" aria-label="Close dialog">✕</button>

        <div class="github-modal-header">
          <div class="github-header-main">
            <div class="github-badge-icon-wrap">
              ${GITHUB_SVG}
            </div>
            <div class="github-header-titles">
              <div class="github-modal-sanskrit-title">मुक्तस्रोत-प्रक्षेपणम्</div>
              <h2 class="github-modal-title" id="gh-modal-main-title">Open Source Launch at AIOC 2026</h2>
            </div>
          </div>
          <div class="github-conference-pill">
            <span class="pill-dot"></span>
            <span>All India Oriental Conference • 52nd Session</span>
          </div>
        </div>

        <div class="github-countdown-box">
          <div class="github-countdown-status-badge">
            <span class="status-light"></span>
            <span id="gh-status-badge-text">Countdown to Launch</span>
          </div>

          <div class="github-countdown-grid">
            <div class="github-timer-card">
              <span class="timer-value" id="gh-val-days">00</span>
              <span class="timer-label">Days</span>
            </div>
            <div class="github-timer-card">
              <span class="timer-value" id="gh-val-hours">00</span>
              <span class="timer-label">Hours</span>
            </div>
            <div class="github-timer-card">
              <span class="timer-value" id="gh-val-mins">00</span>
              <span class="timer-label">Minutes</span>
            </div>
            <div class="github-timer-card">
              <span class="timer-value" id="gh-val-secs">00</span>
              <span class="timer-label">Seconds</span>
            </div>
          </div>

          <div class="github-countdown-target-note" id="gh-target-note">
            Official Presentation at AIOC: <strong>October 31, 2026</strong>
          </div>
        </div>

        <div class="github-launch-details">
          <p class="github-summary-text">
            Sanskrit computational linguistic tools, OCR models, and digital library repositories will be unveiled and open-sourced at AIOC 2026.
          </p>
          <div class="github-security-note">
            <span class="note-icon">🔒</span>
            <span>Repository access unlocks upon official conference presentation.</span>
          </div>
        </div>

        <div class="github-modal-actions">
          <button type="button" class="github-btn-secondary" id="gh-copy-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            <span>Share</span>
          </button>

          <button type="button" class="github-btn-secondary" id="gh-calendar-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
              <line x1="16" y1="2" x2="16" y2="6"></line>
              <line x1="8" y1="2" x2="8" y2="6"></line>
              <line x1="3" y1="10" x2="21" y2="10"></line>
            </svg>
            <span>Calendar</span>
          </button>

          <button type="button" class="github-btn-primary" id="gh-done-btn">
            Close
          </button>
        </div>

        <div class="github-copy-toast" id="gh-copy-toast">
          ✓ Announcement copied to clipboard!
        </div>
      </div>
    `;

    document.body.appendChild(backdrop);

    // Event Listeners for Closing
    const closeBtn = document.getElementById('gh-modal-close-btn');
    const doneBtn = document.getElementById('gh-done-btn');

    if (closeBtn) closeBtn.addEventListener('click', closeLaunchModal);
    if (doneBtn) doneBtn.addEventListener('click', closeLaunchModal);

    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) {
        closeLaunchModal();
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && backdrop.classList.contains('open')) {
        closeLaunchModal();
      }
    });

    // Calendar .ics download
    const calBtn = document.getElementById('gh-calendar-btn');
    if (calBtn) {
      calBtn.addEventListener('click', downloadCalendarEvent);
    }

    // Share Announcement copy
    const copyBtn = document.getElementById('gh-copy-btn');
    if (copyBtn) {
      copyBtn.addEventListener('click', copyAnnouncement);
    }
  }

  // ── Open & Close Functions ──────────────────────────────────────────────
  function openLaunchModal(e) {
    if (e && e.preventDefault) e.preventDefault();
    createLaunchModal();

    const backdrop = document.getElementById('github-launch-backdrop');
    if (!backdrop) return;

    updateCountdownUI();
    backdrop.classList.add('open');
    document.body.style.overflow = 'hidden';

    // Start live interval while open
    if (!timerInterval) {
      timerInterval = setInterval(updateCountdownUI, 1000);
    }
  }

  function closeLaunchModal() {
    const backdrop = document.getElementById('github-launch-backdrop');
    if (!backdrop) return;

    backdrop.classList.remove('open');
    document.body.style.overflow = '';
  }

  // ── Share Announcement Helper ───────────────────────────────────────────
  function copyAnnouncement() {
    const text = 
`🏛️ Samshodhana Mandiram — Open Source Launch Countdown!
We are presenting our research paper and unveiling our open-source Sanskrit computational tools & digital library repositories at the All India Oriental Conference (AIOC) on October 31, 2026.
Stay tuned for the official release!
https://trayeevidya.org/`;

    navigator.clipboard.writeText(text).then(() => {
      const toast = document.getElementById('gh-copy-toast');
      if (toast) {
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 2400);
      }
    }).catch(() => {
      alert("Samshodhana Mandiram Open Source Launch at AIOC on October 31, 2026!");
    });
  }

  // ── Calendar (.ics) Generator Helper ────────────────────────────────────
  function downloadCalendarEvent() {
    const icsContent = 
`BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Samshodhana Mandiram//AIOC 2026 Launch//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
UID:smsdl-aioc-launch-20261031@trayeevidya.org
DTSTAMP:20261007T000000Z
DTSTART;TZID=Asia/Kolkata:20261031T090000
DTEND;TZID=Asia/Kolkata:20261031T180000
SUMMARY:Samshodhana Mandiram — Open Source Launch at AIOC 2026
DESCRIPTION:Presentation of Sanskrit Digital Library & Computational Research at the 52nd All India Oriental Conference (AIOC), followed by the official open-source repository unveiling.
LOCATION:All India Oriental Conference (AIOC)
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR`;

    const blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.setAttribute('download', 'Samshodhana_Mandiram_AIOC_Launch.ics');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  // ── Header Slot Detection & Button Injection ────────────────────────────
  function injectHeaderButton() {
    // Avoid duplicate buttons
    if (document.getElementById('github-launch-btn')) {
      const existing = document.getElementById('github-launch-btn');
      existing.onclick = openLaunchModal;
      return;
    }

    const btn = document.createElement('button');
    btn.id = 'github-launch-btn';
    btn.type = 'button';
    btn.className = 'github-header-btn';
    btn.setAttribute('aria-label', 'Open Source Launch Countdown — AIOC 2026');
    btn.setAttribute('title', 'Samshodhana Mandiram — Open Source Launch Countdown (AIOC 2026)');

    btn.innerHTML = `
      ${GITHUB_SVG}
      <span class="github-btn-text">Open Source</span>
      <span class="github-pulse-dot" title="Launch Countdown Active"></span>
    `;

    btn.addEventListener('click', openLaunchModal);

    // Look for header element
    const header = document.querySelector('header, nav.navbar, nav.topbar, .header, .topbar, .admin-header, .reader-header');

    if (header) {
      // Look for preferred container within the header
      const actions = header.querySelector(
        '.header-actions, .nav-actions, .navbar-links, .nav-right, .header-right, .topbar-actions, .admin-header-actions'
      );

      if (actions) {
        // Prefer placing right before desktop-nav or login so it sits neatly in line with Login / Avatar
        const desktopNav = actions.querySelector('.desktop-nav, #navlist');
        if (desktopNav) {
          actions.insertBefore(btn, desktopNav);
          return;
        }

        // If mobile toggle or avatar exists, place button right before it
        const mobileToggle = actions.querySelector('.mobile-toggle, #mobileNavToggle, .drawer-toggle, .hamburger');
        if (mobileToggle) {
          actions.insertBefore(btn, mobileToggle);
          return;
        }
        actions.appendChild(btn);
        return;
      }

      // If desktop nav exists
      const desktopNav = header.querySelector('.desktop-nav, nav, .nav-menu, #navlist');
      if (desktopNav) {
        const navList = desktopNav.querySelector('ul') || desktopNav;
        navList.appendChild(btn);
        return;
      }

      // Fallback inside header directly
      header.appendChild(btn);
      return;
    }

    // Fallback if page has no header: elegant top-right floating badge
    btn.classList.add('github-btn-floating');
    document.body.appendChild(btn);
  }

  // ── Mobile Drawer Link Injection ────────────────────────────────────────
  function injectDrawerLink() {
    const drawerContent = document.querySelector('.mobile-drawer .drawer-content, .drawer-content');
    if (!drawerContent || document.getElementById('drawer-github-launch-link')) return;

    const link = document.createElement('a');
    link.id = 'drawer-github-launch-link';
    link.href = '#';
    link.className = 'drawer-link';
    link.innerHTML = `
      <span class="drawer-icon">🐙</span> Open Source Launch
      <span class="drawer-badge" style="background: var(--t-accent-alpha-18, rgba(212,175,55,0.18)); color: var(--t-accent, #d4af37);">AIOC '26</span>
    `;
    link.addEventListener('click', (e) => {
      e.preventDefault();
      if (typeof window.closeNav === 'function') window.closeNav();
      openLaunchModal();
    });

    const accountTitle = Array.from(drawerContent.querySelectorAll('.drawer-section-title')).find(el => (el.textContent || '').includes('Account'));
    if (accountTitle) {
      drawerContent.insertBefore(link, accountTitle);
    } else {
      drawerContent.appendChild(link);
    }
  }

  // ── Initialization Routine ──────────────────────────────────────────────
  function init() {
    injectHeaderButton();
    injectDrawerLink();
    createLaunchModal();
    updateCountdownUI();

    // Start background ticker
    if (!timerInterval) {
      timerInterval = setInterval(updateCountdownUI, 1000);
    }

    // Secondary check for dynamically rendered headers or single page components
    setTimeout(() => {
      injectHeaderButton();
      injectDrawerLink();
    }, 350);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose global methods
  window.openGithubLaunchModal = openLaunchModal;
  window.closeGithubLaunchModal = closeLaunchModal;
  window.initGithubLaunch = init;
})();
