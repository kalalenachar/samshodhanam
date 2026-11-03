// Keyman Engine Transliteration Logic (self-hosted keyboard)
(function () {
    let keymanReady = false;
    let oskVisibleState = false; // State of the visual On-Screen Keyboard (hidden by default)
    const KBD_ID = 'Keyboard_itrans_devanagari_sanskrit_vedic';
    const STORAGE_KEY = 'itrans_enabled';

    function getSavedItransState() {
        try {
            const saved = sessionStorage.getItem(STORAGE_KEY);
            return saved !== null ? saved === 'true' : true; // Default to true
        } catch (e) { return true; }
    }

    function saveItransState(enabled) {
        try {
            sessionStorage.setItem(STORAGE_KEY, enabled);
        } catch (e) { }
    }

    function syncAllToggles(enabled) {
        const toggles = document.querySelectorAll('input[type="checkbox"][id$="Sanskrit"]');
        toggles.forEach(t => t.checked = enabled);
    }

    // Apply saved state immediately as script loads (elements are already in DOM)
    syncAllToggles(getSavedItransState());

    function refreshAllInputs() {
        if (!keymanReady) return;
        const inputs = document.querySelectorAll('.sanskrit-enabled');
        inputs.forEach(input => {
            const toggleId = input.getAttribute('data-sanskrit-id');
            const toggle = document.getElementById(toggleId);
            if (toggle) {
                if (toggle.checked) {
                    keyman.attachToControl(input);
                    keyman.setActiveKeyboard(KBD_ID, 'sa');
                } else {
                    keyman.detachFromControl(input);
                }
            }
        });
    }

    // Synchronize visual styling of all keyboard buttons based on OSK active state
    function updateOSKVisualState() {
        const buttons = document.querySelectorAll('button[id^="osk-btn-"]');
        buttons.forEach(btn => {
            if (oskVisibleState) {
                btn.style.background = 'var(--t-accent)'; // Use theme accent instead of purple
                btn.style.borderColor = 'var(--t-accent)';
                btn.style.color = '#ffffff';
            } else {
                btn.style.background = 'var(--t-accent-alpha-15)';
                btn.style.borderColor = 'var(--t-border)';
                btn.style.color = 'var(--t-accent)';
            }
        });

        if (oskVisibleState) {
            document.body.classList.add('osk-visible');
            const activeEl = document.activeElement;
            if (activeEl && activeEl.classList.contains('sanskrit-enabled')) {
                document.body.classList.add('osk-active');
                // Hide OSK first and show after transition completes
                keyman.osk.show(false);
                setTimeout(() => {
                    if (oskVisibleState && document.activeElement === activeEl) {
                        keyman.osk.show(true);
                    }
                }, 300);
            } else {
                keyman.osk.show(true);
            }
        } else {
            keyman.osk.show(false);
            document.body.classList.remove('osk-visible');
            document.body.classList.remove('osk-active');
        }
    }

    // Show/hide keyboard buttons dynamically based on whether "Type in Sanskrit" toggle is enabled
    function syncOSKButtonsVisibility() {
        const toggles = document.querySelectorAll('input[type="checkbox"][id$="Sanskrit"]');
        toggles.forEach(toggle => {
            const btn = document.getElementById(`osk-btn-${toggle.id}`);
            if (btn) {
                btn.style.display = toggle.checked ? 'inline-block' : 'none';
            }
        });
    }

    // Function to dynamically inject small keyboard icon button beside the Type in Sanskrit toggle switch
    function injectOSKButtons() {
        const toggles = document.querySelectorAll('input[type="checkbox"][id$="Sanskrit"]');
        toggles.forEach(toggle => {
            const btnId = `osk-btn-${toggle.id}`;
            if (!document.getElementById(btnId)) {
                // Create small visual button
                const oskBtn = document.createElement('button');
                oskBtn.type = 'button';
                oskBtn.id = btnId;
                oskBtn.innerHTML = '⌨️';
                oskBtn.title = "Toggle On-Screen Keyboard";
                oskBtn.style.background = 'var(--t-accent-alpha-15)';
                oskBtn.style.border = '1px solid var(--t-border)';
                oskBtn.style.color = 'var(--t-accent)';
                oskBtn.style.borderRadius = '6px';
                oskBtn.style.padding = '4px 8px';
                oskBtn.style.fontSize = '14px';
                oskBtn.style.cursor = 'pointer';
                oskBtn.style.marginLeft = '10px';
                oskBtn.style.display = toggle.checked ? 'inline-block' : 'none';
                oskBtn.style.transition = 'all 0.2s ease';
                oskBtn.style.verticalAlign = 'middle';

                // Add Hover Effects
                oskBtn.addEventListener('mouseenter', () => {
                    if (!oskVisibleState) {
                        oskBtn.style.background = 'var(--t-accent-alpha-25)';
                        oskBtn.style.borderColor = 'var(--t-border-hover)';
                    }
                });
                oskBtn.addEventListener('mouseleave', () => {
                    if (!oskVisibleState) {
                        oskBtn.style.background = 'var(--t-accent-alpha-15)';
                        oskBtn.style.borderColor = 'var(--t-border)';
                    }
                });

                // Toggle click handler
                oskBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    if (!keymanReady) return;

                    oskVisibleState = !oskVisibleState;
                    updateOSKVisualState();
                });

                // Find parent container (append directly to ITRANS toggle wrapper div to place beside it)
                const container = toggle.closest('.sanskrit-toggle-container, .sanskrit-keyboard-toggle-wrapper') ? (toggle.parentElement.parentElement) : toggle.parentElement;
                if (container) {
                    container.appendChild(oskBtn);
                }
            }
        });
    }

    async function initKeyman() {
        if (typeof keyman === 'undefined') {
            console.warn("Keyman Engine not loaded — Sanskrit input unavailable.");
            return;
        }

        try {
            await keyman.init({ attachType: 'manual' });

            // Inject CSS to hide Keyman close button (only allow minimizing)
            const style = document.createElement('style');
            style.textContent = `
                #kmw-close-button, .kmw-close-button, .kmw-osk-close {
                    display: none !important;
                }
            `;
            document.head.appendChild(style);

            // Load keyboard locally
            await keyman.addKeyboards({
                id: 'itrans_devanagari_sanskrit_vedic',
                name: 'Vedic Sanskrit Devanagari Phonetic (ITRANS)',
                languages: {
                    id: 'sa',
                    name: 'Sanskrit'
                },
                filename: '/sdl/static/itrans_devanagari_sanskrit_vedic.js'
            });
            keymanReady = true;

            // Strict OSK Focus Control: force hide visual OSK on input focus unless explicitly toggled by keyboard button
            keyman.addEventListener('controlfocused', function (e) {
                if (!oskVisibleState) {
                    keyman.osk.show(false);
                } else {
                    keyman.osk.show(false);
                    setTimeout(() => {
                        const activeEl = document.activeElement;
                        if (oskVisibleState && activeEl && activeEl.classList.contains('sanskrit-enabled')) {
                            keyman.osk.show(true);
                        }
                    }, 300);
                }
            });

            // Inject the small keyboard icon buttons
            injectOSKButtons();

            const inputs = document.querySelectorAll('.sanskrit-enabled');
            const processedToggles = new Set();

            inputs.forEach(input => {
                // Focus/blur listeners to show/hide keyboard spacing dynamically
                input.addEventListener('focus', () => {
                    if (oskVisibleState) {
                        document.body.classList.add('osk-active');
                    }
                });
                input.addEventListener('blur', () => {
                    document.body.classList.remove('osk-active');
                });

                const toggleId = input.getAttribute('data-sanskrit-id');
                const toggle = document.getElementById(toggleId);

                // Attach change listener only once per unique toggle switch
                if (toggle && !processedToggles.has(toggleId)) {
                    processedToggles.add(toggleId);

                    toggle.addEventListener('change', () => {
                        const isEnabled = toggle.checked;
                        saveItransState(isEnabled);
                        syncAllToggles(isEnabled);
                        refreshAllInputs();

                        // Sync button visibility (only show when Type in Sanskrit toggle is ON)
                        syncOSKButtonsVisibility();

                        // If Type in Sanskrit is disabled, turn off OSK visual too
                        if (!isEnabled && oskVisibleState) {
                            oskVisibleState = false;
                            updateOSKVisualState();
                        }

                        const active = document.activeElement;
                        if (active && active.classList.contains('sanskrit-enabled')) {
                            active.blur();
                            setTimeout(() => active.focus(), 50);
                        }
                    });
                }
            });

            // Initial refresh
            refreshAllInputs();
            syncOSKButtonsVisibility();
        } catch (err) {
            console.warn("Keyman init failed. Sanskrit input disabled.", err);
            keymanReady = false;
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initKeyman);
    } else {
        initKeyman();
    }
})();
