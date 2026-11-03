/**
 * Samshodhana Mandiram — Mobile Mode Blocker & Desktop Mode Enforcer
 *
 * Enforces Desktop Mode policy across the platform:
 * When accessed from a mobile browser or mobile screen width, displays a full-screen,
 * impenetrable blocking screen notifying the user that the mobile version is still
 * under development and that they must use Desktop Mode (or a desktop computer).
 * No page functionality, navigation, or interaction is permitted while in mobile mode.
 */
(function () {
  'use strict';

  // Prevent duplicate execution
  if (window.__smsdlMobileBlockerLoaded) return;
  window.__smsdlMobileBlockerLoaded = true;

  const MOBILE_MAX_WIDTH = 850;
  const DESKTOP_MODE_MIN_WIDTH = 980;

  /**
   * Determine whether current view is in mobile mode.
   * On mobile browsers (Chrome / Safari / Firefox / Edge), selecting
   * "Desktop site" / "Request Desktop Website" forces a viewport width >= 980px.
   */
  function isMobileMode() {
    const width = window.innerWidth || (document.documentElement && document.documentElement.clientWidth) || 0;
    const ua = navigator.userAgent || '';
    
    // Check mobile user-agent signatures
    const isMobileUA = /Android.*Mobile|iPhone|iPod|BlackBerry|IEMobile|Opera Mini/i.test(ua);

    // Standard phone / small tablet portrait or narrow viewport
    if (width > 0 && width <= MOBILE_MAX_WIDTH) {
      return true;
    }

    // Mobile device in landscape without desktop site enabled
    if (isMobileUA && width > 0 && width < DESKTOP_MODE_MIN_WIDTH) {
      return true;
    }

    return false;
  }

  /**
   * Inject blocker styling directly into document head
   * ensuring zero dependence on external CSS sheets.
   */
  function injectBlockerStyles() {
    if (document.getElementById('smsdl-mobile-blocker-styles')) return;

    const style = document.createElement('style');
    style.id = 'smsdl-mobile-blocker-styles';
    style.textContent = `
      /* Strict page interaction & scroll locking */
      html.smsdl-mobile-locked,
      body.smsdl-mobile-locked {
        overflow: hidden !important;
        height: 100% !important;
        max-height: 100vh !important;
        touch-action: none !important;
        overscroll-behavior: none !important;
        position: relative !important;
      }

      body.smsdl-mobile-locked > *:not(#smsdl-mobile-blocker) {
        pointer-events: none !important;
        user-select: none !important;
        filter: blur(8px) brightness(0.35) !important;
        opacity: 0.2 !important;
        transition: filter 0.3s ease, opacity 0.3s ease !important;
      }

      /* Fullscreen Blocking Overlay */
      #smsdl-mobile-blocker {
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        height: 100dvh !important;
        z-index: 2147483647 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 16px !important;
        box-sizing: border-box !important;
        background: radial-gradient(circle at 50% 15%, rgba(30, 27, 75, 0.98), rgba(15, 17, 26, 0.99)) !important;
        backdrop-filter: blur(24px) !important;
        -webkit-backdrop-filter: blur(24px) !important;
        opacity: 1 !important;
        visibility: visible !important;
        pointer-events: auto !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
        color: #f8fafc !important;
      }

      .smsdl-blocker-card {
        background: linear-gradient(165deg, rgba(28, 30, 46, 0.96) 0%, rgba(16, 18, 28, 0.98) 100%) !important;
        border: 1px solid rgba(212, 175, 55, 0.4) !important;
        box-shadow: 0 25px 60px rgba(0, 0, 0, 0.8), 0 0 35px rgba(212, 175, 55, 0.15) !important;
        border-radius: 24px !important;
        max-width: 440px !important;
        width: 100% !important;
        max-height: 90vh !important;
        max-height: 90dvh !important;
        overflow-y: auto !important;
        -webkit-overflow-scrolling: touch !important;
        padding: 26px 20px !important;
        box-sizing: border-box !important;
        text-align: center !important;
        animation: smsdlPopIn 0.35s cubic-bezier(0.16, 1, 0.3, 1) !important;
        scrollbar-width: thin !important;
      }

      @keyframes smsdlPopIn {
        from {
          opacity: 0;
          transform: scale(0.92) translateY(16px);
        }
        to {
          opacity: 1;
          transform: scale(1) translateY(0);
        }
      }

      @keyframes smsdlShake {
        0%, 100% { transform: translateX(0); }
        20%, 60% { transform: translateX(-8px); }
        40%, 80% { transform: translateX(8px); }
      }

      .smsdl-shake-anim {
        animation: smsdlShake 0.45s ease-in-out !important;
      }

      .smsdl-blocker-badge {
        display: inline-flex !important;
        align-items: center !important;
        gap: 8px !important;
        background: rgba(245, 158, 11, 0.14) !important;
        border: 1px solid rgba(245, 158, 11, 0.45) !important;
        color: #fbbf24 !important;
        padding: 5px 14px !important;
        border-radius: 999px !important;
        font-size: 11.5px !important;
        font-weight: 700 !important;
        letter-spacing: 0.4px !important;
        margin-bottom: 14px !important;
      }

      .smsdl-badge-dot {
        width: 8px !important;
        height: 8px !important;
        background-color: #f59e0b !important;
        border-radius: 50% !important;
        box-shadow: 0 0 10px #f59e0b !important;
        animation: smsdlPulse 1.8s infinite ease-in-out !important;
      }

      @keyframes smsdlPulse {
        0%, 100% { transform: scale(1); opacity: 1; }
        50% { transform: scale(1.35); opacity: 0.55; }
      }

      .smsdl-blocker-icon {
        width: 68px !important;
        height: 68px !important;
        margin: 0 auto 14px auto !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        border-radius: 20px !important;
        background: linear-gradient(135deg, rgba(212, 175, 55, 0.18), rgba(230, 81, 0, 0.22)) !important;
        border: 1px solid rgba(212, 175, 55, 0.4) !important;
        box-shadow: 0 8px 24px rgba(212, 175, 55, 0.2) !important;
      }

      .smsdl-blocker-title {
        font-size: 20px !important;
        font-weight: 800 !important;
        color: #ffffff !important;
        margin: 0 0 4px 0 !important;
        line-height: 1.3 !important;
        letter-spacing: -0.3px !important;
      }

      .smsdl-blocker-subtitle {
        font-size: 13px !important;
        font-weight: 600 !important;
        color: #d4af37 !important;
        margin-bottom: 14px !important;
        letter-spacing: 0.5px !important;
      }

      .smsdl-blocker-desc {
        font-size: 13.5px !important;
        line-height: 1.55 !important;
        color: #cbd5e1 !important;
        margin: 0 0 18px 0 !important;
      }

      .smsdl-blocker-guide {
        background: rgba(255, 255, 255, 0.04) !important;
        border: 1px solid rgba(255, 255, 255, 0.09) !important;
        border-radius: 16px !important;
        padding: 14px !important;
        margin-bottom: 18px !important;
        text-align: left !important;
      }

      .smsdl-guide-title {
        font-size: 12px !important;
        font-weight: 700 !important;
        color: #e2e8f0 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.6px !important;
        margin-bottom: 10px !important;
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
      }

      .smsdl-guide-item {
        display: flex !important;
        align-items: flex-start !important;
        gap: 10px !important;
        margin-bottom: 10px !important;
        font-size: 12.5px !important;
        line-height: 1.45 !important;
        color: #94a3b8 !important;
      }

      .smsdl-guide-item:last-child {
        margin-bottom: 0 !important;
      }

      .smsdl-platform-tag {
        flex-shrink: 0 !important;
        background: rgba(255, 255, 255, 0.1) !important;
        color: #f1f5f9 !important;
        font-weight: 700 !important;
        font-size: 11px !important;
        padding: 2px 7px !important;
        border-radius: 6px !important;
      }

      .smsdl-guide-item strong {
        color: #ffffff !important;
      }

      .smsdl-btn-group {
        display: flex !important;
        flex-direction: column !important;
        gap: 9px !important;
        width: 100% !important;
      }

      .smsdl-btn {
        width: 100% !important;
        border: none !important;
        border-radius: 14px !important;
        padding: 13px 18px !important;
        font-size: 14px !important;
        font-weight: 700 !important;
        cursor: pointer !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 8px !important;
        transition: transform 0.15s ease, filter 0.2s ease, background 0.2s ease !important;
        box-sizing: border-box !important;
        font-family: inherit !important;
        touch-action: manipulation !important;
      }

      .smsdl-btn:active {
        transform: scale(0.97) !important;
      }

      .smsdl-btn-primary {
        background: linear-gradient(135deg, #d4af37 0%, #e65100 100%) !important;
        color: #ffffff !important;
        box-shadow: 0 4px 18px rgba(230, 81, 0, 0.4) !important;
      }

      .smsdl-btn-primary:hover {
        filter: brightness(1.1) !important;
      }

      .smsdl-btn-secondary {
        background: rgba(255, 255, 255, 0.08) !important;
        color: #e2e8f0 !important;
        border: 1px solid rgba(255, 255, 255, 0.14) !important;
      }

      .smsdl-btn-secondary:hover {
        background: rgba(255, 255, 255, 0.13) !important;
      }

      .smsdl-toast {
        margin-top: 10px !important;
        padding: 8px 12px !important;
        border-radius: 10px !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        line-height: 1.4 !important;
        transition: opacity 0.2s ease !important;
      }

      .smsdl-toast-warn {
        background: rgba(239, 68, 68, 0.18) !important;
        border: 1px solid rgba(239, 68, 68, 0.35) !important;
        color: #fca5a5 !important;
      }

      .smsdl-toast-success {
        background: rgba(16, 185, 129, 0.18) !important;
        border: 1px solid rgba(16, 185, 129, 0.35) !important;
        color: #6ee7b7 !important;
      }

      .smsdl-blocker-footer-note {
        font-size: 11px !important;
        color: #64748b !important;
        margin-top: 14px !important;
        letter-spacing: 0.3px !important;
      }
    `;

    (document.head || document.documentElement).appendChild(style);
  }

  /**
   * Create the Blocker DOM element
   */
  function createBlockerDOM() {
    let blocker = document.getElementById('smsdl-mobile-blocker');
    if (blocker) return blocker;

    blocker = document.createElement('div');
    blocker.id = 'smsdl-mobile-blocker';
    blocker.setAttribute('role', 'alertdialog');
    blocker.setAttribute('aria-modal', 'true');
    blocker.setAttribute('aria-labelledby', 'smsdl-blocker-title');

    blocker.innerHTML = `
      <div class="smsdl-blocker-card" id="smsdl-blocker-card">
        <div class="smsdl-blocker-badge">
          <span class="smsdl-badge-dot"></span>
          <span>मोबाईल-संस्करणं निर्माणाधीनम्</span>
        </div>

        <div class="smsdl-blocker-icon">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#d4af37" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
            <line x1="8" y1="21" x2="16" y2="21"></line>
            <line x1="12" y1="17" x2="12" y2="21"></line>
          </svg>
        </div>

        <h1 id="smsdl-blocker-title" class="smsdl-blocker-title">Mobile Mode Under Development</h1>
        <div class="smsdl-blocker-subtitle">संशोधन मन्दिरम् &bull; Samshodhana Mandiram</div>

        <p class="smsdl-blocker-desc">
          Samshodhana Mandiram is currently under development for mobile. <strong>No pages are available in mobile mode.</strong> Please switch your mobile browser to <strong>Desktop Mode</strong> or access from a computer.
        </p>

        <div class="smsdl-blocker-guide">
          <div class="smsdl-guide-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
            How to Enable Desktop Mode:
          </div>

          <div class="smsdl-guide-item">
            <span class="smsdl-platform-tag">Chrome</span>
            <span>Tap <strong>⋮</strong> (menu) in top-right &rarr; Check <strong>"Desktop site"</strong></span>
          </div>

          <div class="smsdl-guide-item">
            <span class="smsdl-platform-tag">Safari</span>
            <span>Tap <strong>aA</strong> in address bar &rarr; Tap <strong>"Request Desktop Website"</strong></span>
          </div>

          <div class="smsdl-guide-item">
            <span class="smsdl-platform-tag">PC / Laptop</span>
            <span>Open this URL on your computer for full access</span>
          </div>
        </div>

        <div class="smsdl-btn-group">
          <button type="button" id="smsdl-check-btn" class="smsdl-btn smsdl-btn-primary">
            <span>🔄</span>
            <span id="smsdl-check-btn-text">Refresh / I Switched to Desktop Site</span>
          </button>

          <button type="button" id="smsdl-copy-btn" class="smsdl-btn smsdl-btn-secondary">
            <span>📋</span>
            <span id="smsdl-copy-btn-text">Copy Link for Computer</span>
          </button>
        </div>

        <div id="smsdl-toast" class="smsdl-toast" style="display: none;"></div>

        <div class="smsdl-blocker-footer-note">
          संशोधनं विजयते &bull; Vedic Digital Library & Sanskrit Research
        </div>
      </div>
    `;

    return blocker;
  }

  function showToast(msg, isSuccess) {
    const toast = document.getElementById('smsdl-toast');
    if (!toast) return;
    toast.textContent = msg;
    toast.className = 'smsdl-toast ' + (isSuccess ? 'smsdl-toast-success' : 'smsdl-toast-warn');
    toast.style.display = 'block';
  }

  let isRefreshing = false;
  let isCurrentlyBlocked = false;

  function triggerDesktopTransition() {
    if (isRefreshing) return;
    isRefreshing = true;

    const checkBtn = document.getElementById('smsdl-check-btn');
    const checkBtnText = document.getElementById('smsdl-check-btn-text');
    if (checkBtn) {
      checkBtn.style.pointerEvents = 'none';
      checkBtn.style.opacity = '0.85';
    }
    if (checkBtnText) {
      checkBtnText.textContent = '✓ Desktop Mode Detected! Opening...';
    }

    showToast('Desktop mode detected. Opening site...', true);

    setTimeout(function () {
      unblockSite();
      try {
        window.location.reload();
      } catch (e) {
        window.location.href = window.location.href;
      }
    }, 2000);
  }

  function attachBlockerEvents(blocker) {
    const checkBtn = blocker.querySelector('#smsdl-check-btn');
    const checkBtnText = blocker.querySelector('#smsdl-check-btn-text');
    const copyBtn = blocker.querySelector('#smsdl-copy-btn');
    const copyBtnText = blocker.querySelector('#smsdl-copy-btn-text');
    const card = blocker.querySelector('#smsdl-blocker-card');

    if (checkBtn) {
      checkBtn.onclick = function (e) {
        e.preventDefault();
        e.stopPropagation();

        if (!isMobileMode()) {
          // Desktop mode successfully detected
          triggerDesktopTransition();
        } else {
          // Still in mobile mode
          if (card) {
            card.classList.remove('smsdl-shake-anim');
            void card.offsetWidth; // Trigger reflow
            card.classList.add('smsdl-shake-anim');
          }
          showToast('Still in mobile view. Please open browser menu (⋮ or aA) and select "Desktop site".', false);
        }
      };
    }

    if (copyBtn) {
      copyBtn.onclick = function (e) {
        e.preventDefault();
        e.stopPropagation();
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(window.location.href).then(onCopied, fallbackCopy);
          } else {
            fallbackCopy();
          }
        } catch (err) {
          fallbackCopy();
        }

        function onCopied() {
          if (copyBtnText) copyBtnText.textContent = '✓ Link Copied!';
          showToast('Link copied to clipboard! Paste it on your computer.', true);
          setTimeout(function () {
            if (copyBtnText) copyBtnText.textContent = 'Copy Link for Computer';
          }, 2500);
        }

        function fallbackCopy() {
          const ta = document.createElement('textarea');
          ta.value = window.location.href;
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.focus();
          ta.select();
          try {
            document.execCommand('copy');
            onCopied();
          } catch (e) {
            showToast('Please copy the URL manually from your address bar.', false);
          }
          document.body.removeChild(ta);
        }
      };
    }
  }

  function pauseBackgroundMedia() {
    document.querySelectorAll('audio, video').forEach(media => {
      try {
        if (!media.paused) media.pause();
      } catch (e) {}
    });
  }

  function blockSite() {
    isCurrentlyBlocked = true;
    injectBlockerStyles();
    document.documentElement.classList.add('smsdl-mobile-locked');
    if (document.body) {
      document.body.classList.add('smsdl-mobile-locked');
      
      let blocker = document.getElementById('smsdl-mobile-blocker');
      if (!blocker) {
        blocker = createBlockerDOM();
        document.body.appendChild(blocker);
        attachBlockerEvents(blocker);
      }
      blocker.style.display = 'flex';
      pauseBackgroundMedia();
    }
  }

  function unblockSite() {
    isCurrentlyBlocked = false;
    document.documentElement.classList.remove('smsdl-mobile-locked');
    if (document.body) {
      document.body.classList.remove('smsdl-mobile-locked');
    }
    const blocker = document.getElementById('smsdl-mobile-blocker');
    if (blocker) {
      blocker.style.display = 'none';
    }
  }

  function enforceMobilePolicy() {
    if (isMobileMode()) {
      blockSite();
    } else {
      if (isCurrentlyBlocked) {
        triggerDesktopTransition();
      } else {
        unblockSite();
      }
    }
  }


  // Handle immediate execution
  injectBlockerStyles();
  if (isMobileMode()) {
    document.documentElement.classList.add('smsdl-mobile-locked');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enforceMobilePolicy);
  } else {
    enforceMobilePolicy();
  }

  // Re-evaluate on viewport changes (rotation, browser desktop site toggle, resizing)
  let resizeTimeout = null;
  function onViewportChange() {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(enforceMobilePolicy, 150);
  }

  window.addEventListener('resize', onViewportChange);
  window.addEventListener('orientationchange', onViewportChange);

  // Prevent background touch events leaking when blocked
  document.addEventListener('touchmove', function (e) {
    if (isMobileMode() && !e.target.closest('#smsdl-blocker-card')) {
      e.preventDefault();
    }
  }, { passive: false });

  // Safety observer: if blocker is removed while in mobile mode, re-render immediately
  if (window.MutationObserver) {
    const observer = new MutationObserver(function () {
      if (isMobileMode() && document.body && !document.getElementById('smsdl-mobile-blocker')) {
        blockSite();
      }
    });

    if (document.body) {
      observer.observe(document.body, { childList: true });
    } else {
      document.addEventListener('DOMContentLoaded', function () {
        observer.observe(document.body, { childList: true });
      });
    }
  }

  // Expose helper on window
  window.__smsdlEnforceMobilePolicy = enforceMobilePolicy;
})();
