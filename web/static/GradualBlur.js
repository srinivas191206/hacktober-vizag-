// ============================================================================
// Component added by Ansh - github.com/ansh-dhanani
// GradualBlur - Advanced Progressive Backdrop Blur & Gradient Masking
// ============================================================================

const DEFAULT_GRADUAL_BLUR_CONFIG = {
  position: 'bottom',
  height: '6rem',
  strength: 2,
  layers: 8,
  curve: 'linear',
  exponential: true,
  tint: 'rgba(18, 15, 23, 0.6)',
  autoHide: true,
  target: 'parent',
  opacity: 1,
  saturation: 1,
  hoverIntensity: 1,
  zIndex: 850
};

class GradualBlur {
  constructor(container, options = {}) {
    this.container = typeof container === 'string' ? document.querySelector(container) : container;
    if (!this.container) return;

    this.config = Object.assign({}, DEFAULT_GRADUAL_BLUR_CONFIG, options);
    this.element = null;
    this.layerElements = [];
    this.tintElement = null;
    this.scrollTarget = null;
    this.isHovered = false;

    this.init();
  }

  init() {
    this.buildDOM();
    this.setupScrollTarget();
    this.setupEvents();
    this.checkScrollVisibility();
  }

  getGradientDirection(pos) {
    const map = {
      bottom: 'to bottom',
      top: 'to top',
      left: 'to left',
      right: 'to right'
    };
    return map[pos] || 'to bottom';
  }

  getBlurValue(i, layers, curve, exponential, strength) {
    let progress = i / layers;
    if (curve === 'bezier') {
      progress = progress * progress * (3 - 2 * progress);
    } else if (curve === 'ease-out') {
      progress = 1 - Math.pow(1 - progress, 2);
    }
    // Exponential curve (Ansh Dhanani algorithm)
    if (exponential) {
      return Math.pow(2, progress * 4) * 0.0625 * strength;
    }
    return 0.0625 * (progress * layers + 1) * strength;
  }

  buildDOM() {
    // Outer GradualBlur wrapper
    this.element = document.createElement('div');
    this.element.className = 'gradual-blur-wrapper gradual-blur-' + this.config.position;
    this.element.setAttribute('data-target', this.config.target);
    this.element.setAttribute('aria-hidden', 'true');

    const isFixed = this.config.target === 'page';

    this.element.style.cssText = `
      position: ${isFixed ? 'fixed' : 'absolute'};
      ${this.config.position}: 0;
      left: 0;
      right: 0;
      height: ${this.config.height};
      pointer-events: none;
      z-index: ${this.config.zIndex};
      overflow: hidden;
      opacity: 1;
      transition: opacity 0.35s cubic-bezier(0.16, 1, 0.3, 1);
    `;

    // Inner layers host
    const inner = document.createElement('div');
    inner.className = 'gradual-blur-layers';
    inner.style.cssText = 'position: relative; width: 100%; height: 100%; pointer-events: none;';

    const layers = this.config.layers || 8;
    const increment = 100 / layers;
    const direction = this.getGradientDirection(this.config.position);

    this.layerElements = [];

    for (let i = 1; i <= layers; i++) {
      const p1 = Math.round((increment * i - increment) * 10) / 10;
      const p2 = Math.round((increment * i) * 10) / 10;
      const p3 = Math.round((increment * i + increment) * 10) / 10;
      const p4 = Math.round((increment * i + increment * 2) * 10) / 10;

      let maskGrad = `transparent ${p1}%, black ${p2}%`;
      if (p3 <= 100) maskGrad += `, black ${p3}%`;
      if (p4 <= 100) maskGrad += `, transparent ${p4}%`;

      const blurVal = this.getBlurValue(i, layers, this.config.curve, this.config.exponential, this.config.strength);

      const layer = document.createElement('div');
      layer.className = `gradual-blur-layer gradual-blur-step-${i}`;
      layer.dataset.baseBlur = blurVal.toFixed(3);

      layer.style.cssText = `
        position: absolute;
        inset: 0;
        mask-image: linear-gradient(${direction}, ${maskGrad});
        -webkit-mask-image: linear-gradient(${direction}, ${maskGrad});
        backdrop-filter: blur(${blurVal.toFixed(3)}rem) saturate(${this.config.saturation});
        -webkit-backdrop-filter: blur(${blurVal.toFixed(3)}rem) saturate(${this.config.saturation});
        opacity: ${this.config.opacity};
        pointer-events: none;
        transition: backdrop-filter 0.3s ease, -webkit-backdrop-filter 0.3s ease;
      `;

      this.layerElements.push(layer);
      inner.appendChild(layer);
    }

    // Tint gradient overlay
    if (this.config.tint && this.config.tint !== 'transparent') {
      this.tintElement = document.createElement('div');
      this.tintElement.className = 'gradual-blur-tint';
      this.tintElement.style.cssText = `
        position: absolute;
        inset: 0;
        background: linear-gradient(${direction}, transparent 0%, ${this.config.tint} 100%);
        pointer-events: none;
        z-index: 10;
      `;
      inner.appendChild(this.tintElement);
    }

    this.element.appendChild(inner);

    // Make sure parent is positioned relative so absolute positioning aligns
    if (!isFixed) {
      const computedPos = window.getComputedStyle(this.container).position;
      if (computedPos === 'static') {
        this.container.style.position = 'relative';
      }
    }

    this.container.appendChild(this.element);
  }

  setupScrollTarget() {
    if (!this.config.autoHide) return;

    if (this.config.target === 'parent') {
      const computedOverflow = window.getComputedStyle(this.container).overflowY;
      if (computedOverflow === 'auto' || computedOverflow === 'scroll') {
        this.scrollTarget = this.container;
      } else {
        // Fallback to window or closest scrollable ancestor
        let parent = this.container.parentElement;
        while (parent && parent !== document.body) {
          const style = window.getComputedStyle(parent);
          if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
            this.scrollTarget = parent;
            break;
          }
          parent = parent.parentElement;
        }
        if (!this.scrollTarget) this.scrollTarget = window;
      }
    } else {
      this.scrollTarget = window;
    }
  }

  checkScrollVisibility() {
    if (!this.config.autoHide || !this.element) return;

    // If the element's parent is currently hidden (e.g. inactive tab/view), don't show it
    if (this.container && this.container.classList.contains('hidden')) {
      this.element.style.opacity = '0';
      return;
    }

    if (this.scrollTarget === window || this.scrollTarget === document.documentElement || this.scrollTarget === document.body) {
      const scrollY = window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
      const windowH = window.innerHeight;
      const docH = Math.max(
        document.documentElement.scrollHeight,
        document.body.scrollHeight,
        document.documentElement.offsetHeight
      );

      // Auto-hide if reached the absolute bottom of page (within 20px threshold)
      const isAtBottom = (scrollY + windowH) >= (docH - 20);
      // Auto-hide if page does not have scrollable content
      const hasOverflow = docH > (windowH + 30);

      this.element.style.opacity = (hasOverflow && !isAtBottom) ? '1' : '0';
    } else if (this.scrollTarget) {
      const scrollTop = this.scrollTarget.scrollTop;
      const clientH = this.scrollTarget.clientHeight;
      const scrollH = this.scrollTarget.scrollHeight;

      const isAtBottom = (scrollTop + clientH) >= (scrollH - 20);
      const hasOverflow = scrollH > (clientH + 10);

      this.element.style.opacity = (hasOverflow && !isAtBottom) ? '1' : '0';
    }
  }

  setupEvents() {
    // Scroll listener for autoHide
    if (this.config.autoHide) {
      const onScroll = () => {
        this.checkScrollVisibility();
      };
      window.addEventListener('scroll', onScroll, { passive: true });
      document.addEventListener('scroll', onScroll, { passive: true });
      window.addEventListener('resize', onScroll, { passive: true });

      if (this.scrollTarget && this.scrollTarget !== window && this.scrollTarget !== document.documentElement) {
        this.scrollTarget.addEventListener('scroll', onScroll, { passive: true });
      }
    }

    // Hover intensity magnification
    if (this.config.hoverIntensity && this.element && this.config.hoverIntensity > 1) {
      this.element.style.pointerEvents = 'auto';
      this.element.addEventListener('pointerenter', () => {
        this.isHovered = true;
        this.updateHoverStrength(this.config.hoverIntensity);
      });

      this.element.addEventListener('pointerleave', () => {
        this.isHovered = false;
        this.updateHoverStrength(1);
      });
    }
  }

  updateHoverStrength(multiplier) {
    const layers = this.config.layers || 8;
    this.layerElements.forEach((layer, idx) => {
      const i = idx + 1;
      const baseBlur = this.getBlurValue(i, layers, this.config.curve, this.config.exponential, this.config.strength * multiplier);
      layer.style.backdropFilter = `blur(${baseBlur.toFixed(3)}rem) saturate(${this.config.saturation})`;
      layer.style.webkitBackdropFilter = `blur(${baseBlur.toFixed(3)}rem) saturate(${this.config.saturation})`;
    });
  }

  updateTint(newTint) {
    if (this.tintElement) {
      const direction = this.getGradientDirection(this.config.position);
      this.tintElement.style.background = `linear-gradient(${direction}, transparent 0%, ${newTint} 100%)`;
    }
  }

  destroy() {
    if (this.element && this.element.parentNode) {
      this.element.parentNode.removeChild(this.element);
    }
  }
}

// Global Registry & Page Initializer
const gradualBlurInstances = [];

function initWebsiteGradualBlurs() {
  // Clear any existing instances
  gradualBlurInstances.forEach(inst => inst.destroy());
  gradualBlurInstances.length = 0;

  // 1. Page views: attach to all main panels of the website
  const pagePanels = [
    '#view-overview',
    '#view-delivery-studio',
    '#view-spell-insights',
    '#view-sessions'
  ];

  pagePanels.forEach(selector => {
    const el = document.querySelector(selector);
    if (el) {
      const gb = new GradualBlur(el, {
        position: 'bottom',
        height: '6rem',
        strength: 2,
        layers: 8,
        curve: 'linear',
        exponential: true,
        tint: 'rgba(18, 15, 23, 0.6)',
        autoHide: true,
        target: 'parent',
        opacity: 1,
        saturation: 1,
        hoverIntensity: 1
      });
      gradualBlurInstances.push(gb);
    }
  });

  // Check visibility on init
  setTimeout(() => {
    refreshWebsiteGradualBlurs();
  }, 100);
}

function refreshWebsiteGradualBlurs() {
  gradualBlurInstances.forEach(inst => {
    if (inst && typeof inst.checkScrollVisibility === 'function') {
      inst.checkScrollVisibility();
    }
  });
}

// Attach to window and export
if (typeof window !== 'undefined') {
  window.GradualBlur = GradualBlur;
  window.initWebsiteGradualBlurs = initWebsiteGradualBlurs;
  window.refreshWebsiteGradualBlurs = refreshWebsiteGradualBlurs;
  window.gradualBlurInstances = gradualBlurInstances;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { GradualBlur, initWebsiteGradualBlurs, refreshWebsiteGradualBlurs };
}
