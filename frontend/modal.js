/**
 * Verity Themed Modal Dialog Component
 * Replaces native browser alert() and confirm() with sleek, dark-themed glassmorphic dialogs.
 */
(function () {
  // Inject required styles for animations if not present
  if (!document.getElementById('verity-modal-styles')) {
    const styleEl = document.createElement('style');
    styleEl.id = 'verity-modal-styles';
    styleEl.textContent = `
      @keyframes verityModalFadeIn {
        from { opacity: 0; transform: scale(0.96) translateY(6px); }
        to { opacity: 1; transform: scale(1) translateY(0); }
      }
      @keyframes verityBackdropFadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
      }
      .verity-modal-backdrop {
        animation: verityBackdropFadeIn 0.2s cubic-bezier(0.16, 1, 0.3, 1) forwards;
      }
      .verity-modal-card {
        animation: verityModalFadeIn 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards;
      }
    `;
    document.head.appendChild(styleEl);
  }

  /**
   * Shows a themed alert modal
   * @param {Object} options
   * @param {string} options.title
   * @param {string} options.message
   * @param {'info'|'success'|'error'|'warning'} [options.type='info']
   * @param {string} [options.confirmText='ACKNOWLEDGE']
   * @returns {Promise<void>}
   */
  function showModalAlert(options) {
    let title = 'SYSTEM NOTIFICATION';
    let message = '';
    let type = 'info';
    let confirmText = 'ACKNOWLEDGE';

    if (typeof options === 'string') {
      message = options;
    } else if (options && typeof options === 'object') {
      title = options.title || title;
      message = options.message || '';
      type = options.type || 'info';
      confirmText = options.confirmText || confirmText;
    }

    return new Promise((resolve) => {
      createModalDOM({
        title,
        message,
        type,
        confirmText,
        showCancel: false,
        onConfirm: () => resolve(),
        onCancel: () => resolve()
      });
    });
  }

  /**
   * Shows a themed confirmation modal
   * @param {Object} options
   * @param {string} options.title
   * @param {string} options.message
   * @param {'info'|'success'|'error'|'warning'} [options.type='warning']
   * @param {string} [options.confirmText='CONFIRM']
   * @param {string} [options.cancelText='CANCEL']
   * @param {boolean} [options.danger=false]
   * @returns {Promise<boolean>}
   */
  function showModalConfirm(options) {
    let title = 'CONFIRM ACTION';
    let message = '';
    let type = 'warning';
    let confirmText = 'CONFIRM';
    let cancelText = 'CANCEL';
    let danger = false;

    if (typeof options === 'string') {
      message = options;
    } else if (options && typeof options === 'object') {
      title = options.title || title;
      message = options.message || '';
      type = options.type || (options.danger ? 'error' : 'warning');
      confirmText = options.confirmText || confirmText;
      cancelText = options.cancelText || cancelText;
      danger = !!options.danger;
    }

    return new Promise((resolve) => {
      createModalDOM({
        title,
        message,
        type,
        confirmText,
        cancelText,
        danger,
        showCancel: true,
        onConfirm: () => resolve(true),
        onCancel: () => resolve(false)
      });
    });
  }

  function escapeHTML(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function createModalDOM(config) {
    // Remove any existing active modal
    const existing = document.getElementById('verity-active-modal');
    if (existing) existing.remove();

    const backdrop = document.createElement('div');
    backdrop.id = 'verity-active-modal';
    backdrop.className = 'fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-[#0a0c12]/80 backdrop-blur-md verity-modal-backdrop';

    // Type styling configurations
    let iconName = 'info';
    let badgeClass = 'bg-secondary/15 text-secondary border-secondary/30';
    let tagText = '// SYSTEM TELEMETRY';
    let borderClass = 'border-secondary/30';

    if (config.type === 'success') {
      iconName = 'verified';
      badgeClass = 'bg-tertiary/15 text-tertiary border-tertiary/30';
      tagText = '// AUDIT SUCCESSFUL';
      borderClass = 'border-tertiary/40';
    } else if (config.type === 'error' || config.danger) {
      iconName = 'warning';
      badgeClass = 'bg-error/20 text-error border-error/40';
      tagText = '// WARNING & ACTION';
      borderClass = 'border-error/40';
    } else if (config.type === 'warning') {
      iconName = 'help_outline';
      badgeClass = 'bg-amber-400/15 text-amber-300 border-amber-400/30';
      tagText = '// USER CONFIRMATION';
      borderClass = 'border-amber-400/40';
    }

    let confirmBtnClass = 'bg-primary text-on-primary hover:brightness-110 shadow-sm';
    if (config.danger) {
      confirmBtnClass = 'bg-error/20 text-error border border-error/50 hover:bg-error hover:text-[#2d0006] shadow-sm';
    } else if (config.type === 'success') {
      confirmBtnClass = 'bg-tertiary text-on-tertiary hover:brightness-110 font-bold';
    }

    const cancelBtnHTML = config.showCancel
      ? `<button id="verity-modal-cancel-btn" type="button" class="px-4 py-2 font-mono text-xs font-bold uppercase tracking-wider text-outline hover:text-on-surface hover:bg-surface-container-high border border-white/10 transition-all cursor-pointer">
          ${escapeHTML(config.cancelText || 'CANCEL')}
         </button>`
      : '';

    backdrop.innerHTML = `
      <div class="verity-modal-card w-full max-w-lg bg-surface-container border ${borderClass} shadow-[0_20px_50px_rgba(0,0,0,0.85)] flex flex-col overflow-hidden text-on-surface">
        <!-- Modal Top Bar -->
        <div class="px-5 py-3.5 bg-surface-container-high/90 border-b border-white/5 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full ${config.danger ? 'bg-error animate-pulse' : 'bg-secondary animate-pulse'}"></span>
            <span class="font-mono text-[11px] uppercase tracking-widest text-outline">${tagText}</span>
          </div>
          <button id="verity-modal-x-btn" class="text-outline hover:text-on-surface transition-colors cursor-pointer flex items-center justify-center p-1 rounded hover:bg-white/5" title="Dismiss">
            <span class="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>

        <!-- Modal Body Content -->
        <div class="p-6 flex items-start gap-4">
          <div class="w-11 h-11 shrink-0 flex items-center justify-center border ${badgeClass}">
            <span class="material-symbols-outlined text-[24px]">${iconName}</span>
          </div>
          <div class="flex-1 min-w-0 pt-0.5">
            <h3 class="font-headline text-base font-bold text-on-surface tracking-tight mb-2">
              ${escapeHTML(config.title)}
            </h3>
            <div class="font-body text-sm text-outline-variant leading-relaxed whitespace-pre-line break-words">
              ${escapeHTML(config.message)}
            </div>
          </div>
        </div>

        <!-- Modal Footer Actions -->
        <div class="px-6 py-4 bg-surface-container-low/70 border-t border-white/5 flex items-center justify-end gap-3">
          ${cancelBtnHTML}
          <button id="verity-modal-confirm-btn" type="button" class="px-5 py-2 font-mono text-xs font-bold uppercase tracking-wider ${confirmBtnClass} transition-all cursor-pointer flex items-center gap-1.5">
            <span>${escapeHTML(config.confirmText)}</span>
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(backdrop);

    const confirmBtn = document.getElementById('verity-modal-confirm-btn');
    const cancelBtn = document.getElementById('verity-modal-cancel-btn');
    const xBtn = document.getElementById('verity-modal-x-btn');

    function cleanup() {
      document.removeEventListener('keydown', keyHandler);
      backdrop.remove();
    }

    function doConfirm() {
      cleanup();
      if (config.onConfirm) config.onConfirm();
    }

    function doCancel() {
      cleanup();
      if (config.onCancel) config.onCancel();
    }

    function keyHandler(e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        doCancel();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        doConfirm();
      }
    }

    confirmBtn.addEventListener('click', doConfirm);
    if (cancelBtn) cancelBtn.addEventListener('click', doCancel);
    if (xBtn) xBtn.addEventListener('click', doCancel);

    // Clicking backdrop outside the modal card dismisses
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) {
        doCancel();
      }
    });

    document.addEventListener('keydown', keyHandler);
    confirmBtn.focus();
  }

  // Expose on window
  window.showModalAlert = showModalAlert;
  window.showModalConfirm = showModalConfirm;

  // Intercept standard window.alert so ANY residual alert calls display the Verity themed modal
  const originalAlert = window.alert;
  window.alert = function (msg) {
    console.log('[Verity Modal] Intercepted native alert:', msg);
    return showModalAlert({
      title: 'SYSTEM NOTIFICATION',
      message: String(msg || ''),
      type: 'info'
    });
  };

})();
