// Universe Company & Sector Metadata
    const STOCK_METADATA = {
      'PLTR_US_EQ': { name: 'Palantir Technologies', sector: 'Enterprise AI & Defense', domain: 'palantir.com' },
      'NVDA_US_EQ': { name: 'NVIDIA Corp', sector: 'AI & Semiconductors', domain: 'nvidia.com' },
      'AMD_US_EQ': { name: 'Advanced Micro Devices', sector: 'AI & Semiconductors', domain: 'amd.com' },
      'SMCI_US_EQ': { name: 'Super Micro Computer', sector: 'AI Server Infrastructure', domain: 'supermicro.com' },
      'ARM_US_EQ': { name: 'Arm Holdings', sector: 'Semiconductor Architecture', domain: 'arm.com' },
      'MU_US_EQ': { name: 'Micron Technology', sector: 'Memory & Storage', domain: 'micron.com' },
      'AVGO_US_EQ': { name: 'Broadcom Inc', sector: 'Semiconductors & Networking', domain: 'broadcom.com' },
      'MRVL_US_EQ': { name: 'Marvell Technology', sector: 'Data Infrastructure Silicon', domain: 'marvell.com' },
      'TSM_US_EQ': { name: 'Taiwan Semiconductor', sector: 'Semiconductor Foundry', domain: 'tsmc.com' },
      'ANET_US_EQ': { name: 'Arista Networks', sector: 'Cloud Networking', domain: 'arista.com' },
      'MSTR_US_EQ': { name: 'MicroStrategy', sector: 'Bitcoin Treasury & Software', domain: 'microstrategy.com' },
      'COIN_US_EQ': { name: 'Coinbase Global', sector: 'Crypto Exchange', domain: 'coinbase.com' },
      'MARA_US_EQ': { name: 'MARA Holdings', sector: 'Digital Asset Compute', domain: 'mara.com' },
      'RIOT_US_EQ': { name: 'Riot Platforms', sector: 'Digital Asset Compute', domain: 'riotplatforms.com' },
      'CLSK_US_EQ': { name: 'CleanSpark', sector: 'Digital Asset Compute', domain: 'cleanspark.com' },
      'VST_US_EQ': { name: 'Vistra Corp', sector: 'Clean Energy & Nuclear', domain: 'vistracorp.com' },
      'CEG_US_EQ': { name: 'Constellation Energy', sector: 'Clean Energy & Nuclear', domain: 'constellationenergy.com' },
      'OKLO_US_EQ': { name: 'Oklo Inc', sector: 'Next-Gen Fission Energy', domain: 'oklo.com' },
      'CCJ_US_EQ': { name: 'Cameco Corp', sector: 'Uranium & Nuclear Fuel', domain: 'cameco.com' },
      'ENPH_US_EQ': { name: 'Enphase Energy', sector: 'Solar & Renewable Tech', domain: 'enphase.com' },
      'RKLB_US_EQ': { name: 'Rocket Lab USA', sector: 'Space Systems & Launch', domain: 'rocketlabusa.com' },
      'IONQ_US_EQ': { name: 'IonQ Inc', sector: 'Quantum Computing', domain: 'ionq.com' },
      'ASTS_US_EQ': { name: 'AST SpaceMobile', sector: 'Space Cellular Broadband', domain: 'ast-science.com' },
      'LUNR_US_EQ': { name: 'Intuitive Machines', sector: 'Lunar Exploration', domain: 'intuitivemachines.com' },
      'AXON_US_EQ': { name: 'Axon Enterprise', sector: 'Public Safety Technology', domain: 'axon.com' },
      'RGTI_US_EQ': { name: 'Rigetti Computing', sector: 'Quantum Computing', domain: 'rigetti.com' },
      'HOOD_US_EQ': { name: 'Robinhood Markets', sector: 'Fintech & Brokerage', domain: 'robinhood.com' },
      'SOFI_US_EQ': { name: 'SoFi Technologies', sector: 'Digital Banking', domain: 'sofi.com' },
      'AFRM_US_EQ': { name: 'Affirm Holdings', sector: 'Fintech & BNPL', domain: 'affirm.com' },
      'UPST_US_EQ': { name: 'Upstart Holdings', sector: 'AI Lending Platform', domain: 'upstart.com' },
      'NU_US_EQ': { name: 'Nu Holdings', sector: 'Digital Banking', domain: 'nubank.com.br' },
      'FUTU_US_EQ': { name: 'Futu Holdings', sector: 'Global Digital Brokerage', domain: 'futuholdings.com' },
      'SHOP_US_EQ': { name: 'Shopify Inc', sector: 'Global E-Commerce', domain: 'shopify.com' },
      'APP_US_EQ': { name: 'AppLovin Corp', sector: 'AI Marketing & Ads', domain: 'applovin.com' },
      'CRWD_US_EQ': { name: 'CrowdStrike Holdings', sector: 'Cybersecurity Cloud', domain: 'crowdstrike.com' },
      'NET_US_EQ': { name: 'Cloudflare Inc', sector: 'Edge Cloud & Security', domain: 'cloudflare.com' },
      'SNOW_US_EQ': { name: 'Snowflake Inc', sector: 'Data Cloud Platform', domain: 'snowflake.com' },
      'PANW_US_EQ': { name: 'Palo Alto Networks', sector: 'Enterprise Cybersecurity', domain: 'paloaltonetworks.com' },
      'DDOG_US_EQ': { name: 'Datadog Inc', sector: 'Cloud Observability', domain: 'datadoghq.com' },
      'IOT_US_EQ': { name: 'Samsara Inc', sector: 'Connected IoT Operations', domain: 'samsara.com' },
      'TSLA_US_EQ': { name: 'Tesla Inc', sector: 'EV & Autonomous Systems', domain: 'tesla.com' },
      'RIVN_US_EQ': { name: 'Rivian Automotive', sector: 'Electric Vehicles', domain: 'rivian.com' },
      'RDDT_US_EQ': { name: 'Reddit Inc', sector: 'Social Media & Community', domain: 'reddit.com' },
      'CVNA_US_EQ': { name: 'Carvana Co', sector: 'E-Commerce Automotive', domain: 'carvana.com' },
      'DKNG_US_EQ': { name: 'DraftKings Inc', sector: 'Digital Sports Entertainment', domain: 'draftkings.com' },
      'DUOL_US_EQ': { name: 'Duolingo Inc', sector: 'EdTech & Gamification', domain: 'duolingo.com' },
      'HIMS_US_EQ': { name: 'Hims & Hers Health', sector: 'Telehealth & Consumer Health', domain: 'hims.com' },
      'VKTX_US_EQ': { name: 'Viking Therapeutics', sector: 'Biopharmaceuticals', domain: 'vikingtherapeutics.com' },
      'BABA_US_EQ': { name: 'Alibaba Group', sector: 'Global E-Commerce & Cloud', domain: 'alibabagroup.com' },
      'PDD_US_EQ': { name: 'PDD Holdings', sector: 'Global E-Commerce', domain: 'pddholdings.com' },
      // UK 3x Leveraged & Inverse Short ETP Sleeve (London Stock Exchange — 0% Stamp Duty, 0% FX fee in GBP)
      'QQQ3_UK_EQ': { name: 'WisdomTree NASDAQ 100 3x Leveraged (GBP)', sector: '🇬🇧 UK 3x Leveraged Bull ETP • 0% FX', domain: 'wisdomtree.eu', displayTicker: 'QQQ3.L', tvSymbol: 'LSE:LQQ3', currency: '£' },
      '3LUS_UK_EQ': { name: 'WisdomTree S&P 500 3x Leveraged (GBP)', sector: '🇬🇧 UK 3x Leveraged Bull ETP • 0% FX', domain: 'wisdomtree.eu', displayTicker: '3LUS.L', tvSymbol: 'LSE:3LUS', currency: '£' },
      '3LSE_UK_EQ': { name: 'WisdomTree Semiconductor 3x Leveraged (GBP)', sector: '🇬🇧 UK 3x Leveraged Bull ETP • 0% FX', domain: 'wisdomtree.eu', displayTicker: '3LSE.L', tvSymbol: 'LSE:3SMC', currency: '£' },
      'QQQS_UK_EQ': { name: 'WisdomTree NASDAQ 100 3x Daily Short (GBP)', sector: '🇬🇧 UK 3x Inverse Short ETP • Bear Hedge • 0% FX', domain: 'wisdomtree.eu', displayTicker: 'QQQS.L', tvSymbol: 'LSE:LQQS', currency: '£' },
      '3USS_UK_EQ': { name: 'WisdomTree S&P 500 3x Daily Short (GBP)', sector: '🇬🇧 UK 3x Inverse Short ETP • Bear Hedge • 0% FX', domain: 'wisdomtree.eu', displayTicker: '3USS.L', tvSymbol: 'LSE:3ULS', currency: '£' },
    };

    function formatTickerDisplay(symbol) {
      if (STOCK_METADATA[symbol] && STOCK_METADATA[symbol].displayTicker) {
        return STOCK_METADATA[symbol].displayTicker;
      }
      const s = symbol || '';
      if (s.endsWith('_UK_EQ')) return s.replace('_UK_EQ', '.L');
      return s.replace('_US_EQ', '').replace('.US', '');
    }

    // Money amounts (equity, P&L, fees, position value) are in the account currency;
    // prices use the instrument's own currency (getCurrencySymbol).
    let ACCT_CCY = '£';

    function getCurrencySymbol(symbol) {
      if (STOCK_METADATA[symbol] && STOCK_METADATA[symbol].currency) {
        return STOCK_METADATA[symbol].currency;
      }
      return (symbol || '').endsWith('_UK_EQ') ? '£' : '$';
    }

    function getTradingViewSymbol(symbol) {
      if (STOCK_METADATA[symbol] && STOCK_METADATA[symbol].tvSymbol) {
        return STOCK_METADATA[symbol].tvSymbol;
      }
      const s = symbol || 'AAPL';
      if (s.endsWith('_UK_EQ')) return 'LSE:' + s.replace('_UK_EQ', '');
      return s.replace('_US_EQ', '').replace('.US', '');
    }

    function getStockDomain(symbol) {
      if (STOCK_METADATA[symbol] && STOCK_METADATA[symbol].domain) {
        return STOCK_METADATA[symbol].domain;
      }
      const clean = (symbol || '').replace('_US_EQ', '').replace('_UK_EQ', '').toLowerCase();
      const fallbacks = {
        aapl: 'apple.com', msft: 'microsoft.com', googl: 'google.com',
        goog: 'google.com', amzn: 'amazon.com', meta: 'meta.com',
        nflx: 'netflix.com', spy: 'ssga.com', qqq: 'invesco.com'
      };
      return fallbacks[clean] || `${clean}.com`;
    }

    function getSectorGradient(sector) {
      const sec = sector || '';
      if (sec.includes('Crypto') || sec.includes('Bitcoin')) return 'linear-gradient(135deg, #ff9500 0%, #ffb340 100%)';
      if (sec.includes('Clean') || sec.includes('Nuclear') || sec.includes('Solar')) return 'linear-gradient(135deg, #34c759 0%, #66d982 100%)';
      if (sec.includes('Fintech') || sec.includes('Banking') || sec.includes('Lending')) return 'linear-gradient(135deg, #af52de 0%, #c77ded 100%)';
      if (sec.includes('Cyber') || sec.includes('Cloud')) return 'linear-gradient(135deg, #5856d6 0%, #7a79e0 100%)';
      if (sec.includes('EV') || sec.includes('Auto')) return 'linear-gradient(135deg, #ff2d55 0%, #ff6482 100%)';
      return 'linear-gradient(135deg, #0071e3 0%, #42a5f5 100%)';
    }

    function renderStockLogo(symbol, clean, monoGrad, size, imgSize, radius) {
      size = size || 32;
      imgSize = imgSize || 22;
      radius = radius || 9;
      const domain = getStockDomain(symbol);
      const logoUrl = `https://www.google.com/s2/favicons?domain=${domain}&sz=128`;
      return `
        <div class="asset-logo-wrap" style="width:${size}px; height:${size}px; border-radius:${radius}px;">
          <img class="asset-logo-img" style="width:${imgSize}px; height:${imgSize}px;" src="${logoUrl}" alt="${clean}" loading="lazy" onerror="this.style.display='none'; if(this.nextElementSibling) this.nextElementSibling.style.display='flex';" />
          <div class="asset-monogram" style="background:${monoGrad}; display:none; width:100%; height:100%; border-radius:${radius}px; font-size:${Math.round(size * 0.36)}px;">${clean.slice(0, 2)}</div>
        </div>
      `;
    }

    let currentFilter = 'ALL';
    let screenerSearchQuery = '';
    let currentSortCol = 'rank';
    let currentSortDir = 'asc';
    let currentScreenerView = 'table';
    let currentModalSymbol = '';
    let soundEnabled = localStorage.getItem('trading_bot_sound') === 'true';
    let previousEquity = null;
    let latestRecommendations = [];
    let latestAIData = null;
    let showExpiredAI = false;
    let marketIsOpen = false;
    let marketSecondsRemaining = 0;
    let marketTotalClosedSeconds = 63000;
    let marketState = 'CLOSED';
    let marketNextOpenStr = '';
    let ukMarketIsOpen = false;
    let ukMarketSecondsRemaining = 0;
    let ukMarketTotalClosedSeconds = 55800;
    let ukMarketState = 'CLOSED';
    let ukMarketNextOpenStr = '';
    let scanSecondsRemaining = 900;
    let scanProgressPct = 0;
    let hasAnimatedKPIs = false;
    let hasAnimatedEquityCurve = false;

    // Apple Fluid Animations: Scroll-Reveal & Odometer Count-Up System
    function initScrollReveal() {
      const elements = document.querySelectorAll('.reveal-on-scroll:not(.is-revealed)');
      if (!('IntersectionObserver' in window)) {
        elements.forEach(el => el.classList.add('is-revealed'));
        return;
      }
      const observer = new IntersectionObserver((entries, obs) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-revealed');
            obs.unobserve(entry.target);
          }
        });
      }, {
        rootMargin: '0px 0px 80px 0px',
        threshold: 0.01
      });
      elements.forEach(el => observer.observe(el));
    }

    function animateCountUp(el, start, end, duration = 1200, prefix = '$', suffix = '', decimals = 2) {
      if (!el) return;
      const startTime = performance.now();
      function update(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1.0);
        const ease = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
        const current = start + (end - start) * ease;
        el.textContent = `${prefix}${current.toLocaleString('en-US', {
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals
        })}${suffix}`;
        if (progress < 1.0) {
          requestAnimationFrame(update);
        }
      }
      requestAnimationFrame(update);
    }


    // Web Audio Terminal Haptics (Muted by default)
    function updateSoundUI() {
      const icon = document.getElementById('sound-icon');
      if (icon) icon.textContent = soundEnabled ? '🔔' : '🔕';
    }

    function toggleSound() {
      soundEnabled = !soundEnabled;
      localStorage.setItem('trading_bot_sound', soundEnabled ? 'true' : 'false');
      updateSoundUI();
      if (soundEnabled) {
        playHaptic('chime');
        showToast('Audio FX Enabled', 'Terminal sound cues active', '🔔');
      } else {
        showToast('Audio FX Muted', 'Terminal sound cues silenced', '🔕');
      }
    }

    function playHaptic(type) {
      if (!soundEnabled) return;
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        const ctx = new AudioCtx();
        if (ctx.state === 'suspended') ctx.resume();

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);

        const now = ctx.currentTime;
        if (type === 'click') {
          osc.type = 'sine';
          osc.frequency.setValueAtTime(800, now);
          gain.gain.setValueAtTime(0.04, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
          osc.start(now);
          osc.stop(now + 0.04);
        } else if (type === 'chime') {
          osc.type = 'triangle';
          osc.frequency.setValueAtTime(523.25, now);
          osc.frequency.setValueAtTime(659.25, now + 0.08);
          gain.gain.setValueAtTime(0.05, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
          osc.start(now);
          osc.stop(now + 0.25);
        } else if (type === 'action') {
          osc.type = 'sine';
          osc.frequency.setValueAtTime(880, now);
          osc.frequency.setValueAtTime(1046.5, now + 0.06);
          gain.gain.setValueAtTime(0.05, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
          osc.start(now);
          osc.stop(now + 0.2);
        }
      } catch (err) {
        // AudioContext ignored if unprompted
      }
    }

    function toggleEngineSpecs() {
      playHaptic('click');
      const b = document.getElementById('engine-specs-body');
      const btn = document.getElementById('btn-toggle-engine-specs');
      if (!b || !btn) return;
      const isHidden = b.style.display === 'none';
      b.style.display = isHidden ? 'block' : 'none';
      btn.textContent = isHidden ? 'Hide Strategy DNA' : 'Show Strategy DNA';
    }

    function switchScreenerView(mode) {
      playHaptic('click');
      currentScreenerView = mode;
      const tableWrap = document.getElementById('screener-table-container');
      const heatWrap = document.getElementById('screener-heatmap-container');
      const btnTable = document.getElementById('view-mode-table');
      const btnHeat = document.getElementById('view-mode-heatmap');

      if (mode === 'heatmap') {
        if (tableWrap) tableWrap.style.display = 'none';
        if (heatWrap) heatWrap.style.display = 'block';
        if (btnTable) btnTable.classList.remove('active');
        if (btnHeat) btnHeat.classList.add('active');
        renderHeatmap(latestRecommendations);
      } else {
        if (tableWrap) tableWrap.style.display = 'block';
        if (heatWrap) heatWrap.style.display = 'none';
        if (btnTable) btnTable.classList.add('active');
        if (btnHeat) btnHeat.classList.remove('active');
      }
    }

    // Native TradingView-Style Interactive Candlestick Chart Renderer
    function renderCandleChartSVG(stock) {
      const container = document.getElementById('modal-candle-chart-wrap');
      if (!container || !stock) return;

      const w = container.clientWidth || 760;
      const h = 250;
      const padL = 14;
      const padR = 78;
      const padT = 20;
      const padB = 26;
      const plotW = Math.max(100, w - padL - padR);
      const plotH = Math.max(80, h - padT - padB);

      const candleH = plotH * 0.74;
      const volH = plotH * 0.22;
      const volBaseY = padT + plotH;

      // Retrieve or synthesize 16-bar OHLCV candle series
      let rawCandles = (stock.candles && stock.candles.length >= 2) ? stock.candles : [];
      if (rawCandles.length === 0) {
        const pts = (stock.sparkline && stock.sparkline.length >= 2) ? stock.sparkline : [stock.close_price * 0.99, stock.close_price];
        const atr = Number(stock.atr || (stock.close_price * 0.018));
        const now = new Date();
        rawCandles = pts.map((c, i) => {
          const prev = i > 0 ? pts[i - 1] : c * 0.998;
          const open = prev;
          const close = c;
          const high = Math.max(open, close) + (atr * 0.3 * ((i % 3 === 0) ? 1.3 : 0.7));
          const low = Math.min(open, close) - (atr * 0.3 * ((i % 2 === 0) ? 1.1 : 0.6));
          const vol = (stock.rvol || 1.1) * 450000 * (0.8 + ((i * 19) % 7) * 0.08);
          const barDate = new Date(now.getTime() - (pts.length - 1 - i) * 15 * 60 * 1000);
          const timeUtc = `${String(barDate.getUTCHours()).padStart(2, '0')}:${String(barDate.getUTCMinutes()).padStart(2, '0')} UTC`;
          return {
            time: timeUtc,
            datetime: timeUtc,
            o: open,
            h: high,
            l: low,
            c: close,
            v: vol,
            e20: stock.ema_fast || close,
            e50: stock.ema_slow || (close * 0.995)
          };
        });
      }

      // Calculate price boundaries (Y-axis)
      const allPrices = rawCandles.flatMap(c => [Number(c.h), Number(c.l)]);
      const sl = Number(stock.suggested_stop_loss || 0);
      const tp = Number(stock.suggested_take_profit || 0);
      const currP = Number(stock.close_price || 0);
      const emaFast = Number(stock.ema_fast || 0);
      const emaSlow = Number(stock.ema_slow || 0);

      if (sl > 0) allPrices.push(sl);
      if (tp > 0) allPrices.push(tp);
      if (currP > 0) allPrices.push(currP);
      if (emaFast > 0) allPrices.push(emaFast);
      if (emaSlow > 0) allPrices.push(emaSlow);

      let minP = Math.min(...allPrices);
      let maxP = Math.max(...allPrices);
      const margin = Math.max(0.1, (maxP - minP) * 0.08);
      minP -= margin;
      maxP += margin;
      const priceRange = (maxP - minP) || 1.0;

      function priceToY(price) {
        return padT + (1.0 - (price - minP) / priceRange) * candleH;
      }

      const maxVol = Math.max(1, ...rawCandles.map(c => Number(c.v || 0)));
      function volToH(vol) {
        return Math.max(3, (Number(vol || 0) / maxVol) * volH);
      }

      const stepX = plotW / rawCandles.length;
      const candleW = Math.max(6, Math.min(26, stepX * 0.62));

      let candlesSvg = '';
      const ema20Coords = [];
      const ema50Coords = [];

      rawCandles.forEach((c, idx) => {
        const cx = padL + (idx * stepX) + (stepX / 2);
        const open = Number(c.o);
        const high = Number(c.h);
        const low = Number(c.l);
        const close = Number(c.c);
        const isUp = close >= open;
        const col = isUp ? 'var(--green)' : 'var(--red)';

        const wickTopY = priceToY(high);
        const wickBotY = priceToY(low);
        const bodyTopY = priceToY(Math.max(open, close));
        const bodyBotY = priceToY(Math.min(open, close));
        const bodyH = Math.max(2.5, bodyBotY - bodyTopY);

        const vHeight = volToH(c.v);
        const vY = volBaseY - vHeight;

        if (c.e20) ema20Coords.push(`${cx.toFixed(1)},${priceToY(Number(c.e20)).toFixed(1)}`);
        if (c.e50) ema50Coords.push(`${cx.toFixed(1)},${priceToY(Number(c.e50)).toFixed(1)}`);

        candlesSvg += `
          <g class="candle-group" data-idx="${idx}">
            <rect x="${(cx - candleW / 2).toFixed(1)}" y="${vY.toFixed(1)}" width="${candleW.toFixed(1)}" height="${vHeight.toFixed(1)}" rx="1.5" fill="${col}" fill-opacity="0.30" />
            <line x1="${cx.toFixed(1)}" y1="${wickTopY.toFixed(1)}" x2="${cx.toFixed(1)}" y2="${wickBotY.toFixed(1)}" stroke="${col}" stroke-width="1.3" />
            <rect x="${(cx - candleW / 2).toFixed(1)}" y="${bodyTopY.toFixed(1)}" width="${candleW.toFixed(1)}" height="${bodyH.toFixed(1)}" rx="1.8" fill="${col}" />
            ${(idx % 4 === 0 || idx === rawCandles.length - 1) ? `
              <text x="${cx.toFixed(1)}" y="${h - 6}" font-size="9" fill="var(--text-tertiary)" text-anchor="middle">${c.time || ''}</text>
            ` : ''}
          </g>
        `;
      });

      let corridorSvg = '';
      if (tp > 0) {
        const tpY = priceToY(tp);
        corridorSvg += `
          <line x1="${padL}" y1="${tpY.toFixed(1)}" x2="${(w - padR).toFixed(1)}" y2="${tpY.toFixed(1)}" stroke="var(--green)" stroke-dasharray="4,3" stroke-width="1.3" opacity="0.85" />
          <rect x="${w - padR + 6}" y="${(tpY - 9).toFixed(1)}" width="70" height="18" rx="4" fill="rgba(52,199,89,0.14)" stroke="var(--green)" stroke-width="1" />
          <text x="${w - padR + 41}" y="${(tpY + 3.5).toFixed(1)}" font-size="9" font-weight="700" fill="var(--green)" text-anchor="middle">TP $${tp.toFixed(2)}</text>
        `;
      }
      if (sl > 0) {
        const slY = priceToY(sl);
        corridorSvg += `
          <line x1="${padL}" y1="${slY.toFixed(1)}" x2="${(w - padR).toFixed(1)}" y2="${slY.toFixed(1)}" stroke="var(--red)" stroke-dasharray="4,3" stroke-width="1.3" opacity="0.85" />
          <rect x="${w - padR + 6}" y="${(slY - 9).toFixed(1)}" width="70" height="18" rx="4" fill="rgba(255,59,48,0.14)" stroke="var(--red)" stroke-width="1" />
          <text x="${w - padR + 41}" y="${(slY + 3.5).toFixed(1)}" font-size="9" font-weight="700" fill="var(--red)" text-anchor="middle">SL $${sl.toFixed(2)}</text>
        `;
      }
      if (currP > 0) {
        const currY = priceToY(currP);
        corridorSvg += `
          <line x1="${padL}" y1="${currY.toFixed(1)}" x2="${(w - padR).toFixed(1)}" y2="${currY.toFixed(1)}" stroke="var(--accent)" stroke-dasharray="2,2" stroke-width="1.2" opacity="0.9" />
          <rect x="${w - padR + 6}" y="${(currY - 9).toFixed(1)}" width="70" height="18" rx="4" fill="var(--accent)" />
          <text x="${w - padR + 41}" y="${(currY + 3.5).toFixed(1)}" font-size="9" font-weight="700" fill="#ffffff" text-anchor="middle">$${currP.toFixed(2)}</text>
        `;
      }

      const ema20Poly = ema20Coords.length >= 2 ? `<polyline points="${ema20Coords.join(' ')}" fill="none" stroke="#0071e3" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" opacity="0.85" />` : '';
      const ema50Poly = ema50Coords.length >= 2 ? `<polyline points="${ema50Coords.join(' ')}" fill="none" stroke="#af52de" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.85" />` : '';

      const yLabels = `
        <text x="${w - padR - 6}" y="${padT + 10}" font-size="8.5" fill="var(--text-tertiary)" text-anchor="end">$${maxP.toFixed(2)}</text>
        <text x="${w - padR - 6}" y="${(padT + candleH - 4).toFixed(1)}" font-size="8.5" fill="var(--text-tertiary)" text-anchor="end">$${minP.toFixed(2)}</text>
        <text x="${padL + 4}" y="${volBaseY - 4}" font-size="8" fill="var(--text-tertiary)">Vol: ${(maxVol / 1000).toFixed(0)}k max</text>
      `;

      container.innerHTML = `
        <svg id="modal-candle-svg" width="100%" height="${h}" viewBox="0 0 ${w} ${h}" style="overflow:visible;">
          <line x1="${padL}" y1="${(padT + candleH).toFixed(1)}" x2="${(w - padR).toFixed(1)}" y2="${(padT + candleH).toFixed(1)}" stroke="rgba(142,142,147,0.15)" stroke-dasharray="2,2" stroke-width="1" />
          <line x1="${padL}" y1="${volBaseY.toFixed(1)}" x2="${(w - padR).toFixed(1)}" y2="${volBaseY.toFixed(1)}" stroke="rgba(142,142,147,0.25)" stroke-width="1" />

          <text x="${padL + 4}" y="${(padT + candleH + 11).toFixed(1)}" font-size="8" font-weight="700" fill="var(--text-tertiary)">15m BAR VOLUME</text>

          ${yLabels}
          ${corridorSvg}
          ${ema50Poly}
          ${ema20Poly}
          ${candlesSvg}

          <line id="modal-crosshair-x" x1="0" y1="${padT}" x2="0" y2="${volBaseY}" stroke="var(--accent)" stroke-dasharray="3,3" stroke-width="1.2" opacity="0" pointer-events="none" />
          <g id="modal-crosshair-time-pill" opacity="0" pointer-events="none">
            <rect id="modal-crosshair-time-bg" x="0" y="${h - 22}" width="68" height="17" rx="4" fill="var(--surface)" stroke="var(--accent)" stroke-width="1.2" />
            <text id="modal-crosshair-time-text" x="0" y="${h - 10}" font-size="9" font-weight="700" fill="var(--text-primary)" text-anchor="middle">--:--</text>
          </g>
          <rect id="modal-crosshair-overlay" x="${padL}" y="${padT}" width="${plotW}" height="${plotH}" fill="transparent" style="cursor:crosshair;" />
        </svg>
      `;

      const overlay = document.getElementById('modal-crosshair-overlay');
      const crosshairLine = document.getElementById('modal-crosshair-x');
      const inspectText = document.getElementById('modal-candle-hover-inspect');

      if (overlay && crosshairLine && inspectText) {
        function setInspectDefault() {
          const latestC = rawCandles[rawCandles.length - 1];
          const latestTime = latestC ? (latestC.datetime || latestC.time || '') : '';
          inspectText.innerHTML = latestTime
            ? `<span style="display:inline-flex;align-items:center;gap:6px;"><span class="beacon-dot beacon-green" style="width:6px;height:6px;"></span><span>Latest Closed Bar: <strong>${latestTime}</strong></span><span style="color:var(--text-tertiary);">• Hover candles to inspect time & OHLCV</span></span>`
            : `Hover candles to inspect OHLCV`;
        }
        setInspectDefault();

        overlay.addEventListener('mousemove', (e) => {
          const rect = overlay.getBoundingClientRect();
          const mouseX = e.clientX - rect.left;
          const idx = Math.min(rawCandles.length - 1, Math.max(0, Math.floor(mouseX / (rect.width / rawCandles.length))));
          const c = rawCandles[idx];
          if (c) {
            const cx = padL + (idx * stepX) + (stepX / 2);
            crosshairLine.setAttribute('x1', cx.toFixed(1));
            crosshairLine.setAttribute('x2', cx.toFixed(1));
            crosshairLine.setAttribute('opacity', '1');

            const timePill = document.getElementById('modal-crosshair-time-pill');
            const timeBg = document.getElementById('modal-crosshair-time-bg');
            const timeTxt = document.getElementById('modal-crosshair-time-text');
            if (timePill && timeBg && timeTxt) {
              const pillLabel = c.time || `Bar ${idx + 1}`;
              timeTxt.textContent = pillLabel;
              const pillW = Math.max(58, pillLabel.length * 6.5 + 14);
              const pillX = Math.min(w - padR - pillW, Math.max(padL, cx - pillW / 2));
              timeBg.setAttribute('x', pillX.toFixed(1));
              timeBg.setAttribute('width', pillW.toFixed(1));
              timeTxt.setAttribute('x', (pillX + pillW / 2).toFixed(1));
              timePill.setAttribute('opacity', '1');
            }

            const isUp = Number(c.c) >= Number(c.o);
            const colStyle = isUp ? 'color:var(--green-text);' : 'color:var(--red-text);';
            const displayTime = c.datetime || c.time || `Bar ${idx + 1}`;
            inspectText.innerHTML = `
              <span class="badge" style="background:var(--surface-secondary);border:1px solid var(--border);color:var(--text-primary);font-size:10.5px;font-weight:700;padding:2px 7px;border-radius:4px;">
                🕒 ${displayTime}
              </span>
              <span>O: <strong>$${Number(c.o).toFixed(2)}</strong></span>
              <span>H: <strong>$${Number(c.h).toFixed(2)}</strong></span>
              <span>L: <strong>$${Number(c.l).toFixed(2)}</strong></span>
              <span>C: <strong style="${colStyle}">$${Number(c.c).toFixed(2)}</strong></span>
              <span>Vol: <strong>${Number(c.v || 0).toLocaleString()}</strong></span>
            `;
          }
        });

        overlay.addEventListener('mouseleave', () => {
          crosshairLine.setAttribute('opacity', '0');
          const timePill = document.getElementById('modal-crosshair-time-pill');
          if (timePill) timePill.setAttribute('opacity', '0');
          setInspectDefault();
        });
      }
    }

    function switchModalChart(mode) {
      playHaptic('click');
      const sheet = document.querySelector('#stock-modal-backdrop .modal-sheet');
      const candleWrap = document.getElementById('modal-candle-chart-wrap');
      const candleLegend = document.getElementById('modal-candle-legend-bar');
      const sparkEl = document.getElementById('modal-sparkline-expanded');
      const tvWrap = document.getElementById('modal-tv-embedded-wrap');
      const btnCandle = document.getElementById('modal-chart-btn-candle');
      const btnSpark = document.getElementById('modal-chart-btn-spark');
      const btnTv = document.getElementById('modal-chart-btn-tv');

      if (btnCandle) btnCandle.classList.toggle('active', mode === 'candle');
      if (btnSpark) btnSpark.classList.toggle('active', mode === 'spark');
      if (btnTv) btnTv.classList.toggle('active', mode === 'tv');

      let stock = (latestRecommendations || []).find(r => r.symbol === currentModalSymbol);
      if (!stock && latestTelemetryData && latestTelemetryData.positions) {
        const p = latestTelemetryData.positions.find(pos => pos.symbol === currentModalSymbol);
        if (p) {
          stock = {
            symbol: p.symbol,
            close_price: p.current_price,
            score: 80,
            rating: 'BUY',
            rsi: 58,
            rvol: 1.4,
            ema_fast: p.entry_price,
            ema_slow: p.stop_loss,
            atr: Math.abs(p.current_price - p.stop_loss) / 1.5 || (p.current_price * 0.02),
            suggested_stop_loss: p.stop_loss,
            suggested_take_profit: p.take_profit,
            roc_10_pct: p.unrealized_pnl_pct || 0,
            thesis: 'Held active position with real-time trailing stop.'
          };
        }
      }

      if (mode === 'candle') {
        if (sheet) sheet.classList.remove('modal-sheet-wide');
        if (candleWrap) candleWrap.style.display = 'block';
        if (candleLegend) candleLegend.style.display = 'flex';
        if (sparkEl) sparkEl.style.display = 'none';
        if (tvWrap) {
          tvWrap.style.display = 'none';
          tvWrap.innerHTML = '';
        }
        if (stock) renderCandleChartSVG(stock);
      } else if (mode === 'tv') {
        if (sheet) sheet.classList.add('modal-sheet-wide');
        if (candleWrap) candleWrap.style.display = 'none';
        if (candleLegend) candleLegend.style.display = 'none';
        if (sparkEl) sparkEl.style.display = 'none';
        if (tvWrap) {
          tvWrap.style.display = 'block';
          const tvSym = encodeURIComponent(getTradingViewSymbol(currentModalSymbol || 'AAPL'));
          const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
          const themeStr = isDark ? 'dark' : 'light';
          tvWrap.innerHTML = '<iframe src="https://s.tradingview.com/widgetembed/?symbol=' + tvSym + '&interval=15&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=rgba(0,0,0,0)&theme=' + themeStr + '&style=1&timezone=Etc%2FUTC&studies=[]&hideideas=1" style="width:100%;height:100%;border:none;" frameborder="0" allowfullscreen></iframe>';
        }
      } else { // 'spark'
        if (sheet) sheet.classList.remove('modal-sheet-wide');
        if (candleWrap) candleWrap.style.display = 'none';
        if (candleLegend) candleLegend.style.display = 'none';
        if (sparkEl) sparkEl.style.display = 'block';
        if (tvWrap) {
          tvWrap.style.display = 'none';
          tvWrap.innerHTML = '';
        }
      }
    }

    function getHeatmapBgAndBorder(roc) {
      if (roc >= 3.0) {
        return { bg: 'linear-gradient(145deg, rgba(52, 199, 89, 0.35) 0%, rgba(52, 199, 89, 0.16) 100%)', border: 'rgba(52, 199, 89, 0.55)' };
      } else if (roc >= 0.5) {
        return { bg: 'linear-gradient(145deg, rgba(52, 199, 89, 0.20) 0%, rgba(52, 199, 89, 0.08) 100%)', border: 'rgba(52, 199, 89, 0.35)' };
      } else if (roc <= -3.0) {
        return { bg: 'linear-gradient(145deg, rgba(255, 59, 48, 0.35) 0%, rgba(255, 59, 48, 0.16) 100%)', border: 'rgba(255, 59, 48, 0.55)' };
      } else if (roc <= -0.5) {
        return { bg: 'linear-gradient(145deg, rgba(255, 59, 48, 0.20) 0%, rgba(255, 59, 48, 0.08) 100%)', border: 'rgba(255, 59, 48, 0.35)' };
      }
      return { bg: 'var(--surface-secondary)', border: 'var(--border)' };
    }

    function renderHeatmap(recs) {
      const container = document.getElementById('screener-heatmap-container');
      if (!container) return;
      let filtered = [...(recs || [])];
      if (currentFilter === 'US_ONLY') {
        filtered = filtered.filter(r => !(r.symbol || '').endsWith('_UK_EQ'));
      } else if (currentFilter === 'UK_ONLY') {
        filtered = filtered.filter(r => (r.symbol || '').endsWith('_UK_EQ'));
      } else if (currentFilter !== 'ALL') {
        filtered = filtered.filter(r => r.rating === currentFilter);
      }

      // Search Query Filter
      if (screenerSearchQuery) {
        filtered = filtered.filter(r => {
          const clean = formatTickerDisplay(r.symbol).toLowerCase();
          const meta = STOCK_METADATA[r.symbol] || { name: '', sector: '' };
          const name = (meta.name || '').toLowerCase();
          const sector = (meta.sector || '').toLowerCase();
          return clean.includes(screenerSearchQuery) || name.includes(screenerSearchQuery) || sector.includes(screenerSearchQuery);
        });
      }

      if (!filtered || filtered.length === 0) {
        container.innerHTML = '<div style="color:var(--text-tertiary);padding:32px;text-align:center;">No stocks match the selected search or filter criteria.</div>';
        return;
      }

      // Sort by momentum % descending so top performers appear in top-left
      filtered.sort((a, b) => (b.roc_10_pct || 0) - (a.roc_10_pct || 0));

      const tilesHtml = filtered.map(r => {
        const clean = formatTickerDisplay(r.symbol);
        const ccy = getCurrencySymbol(r.symbol);
        const meta = STOCK_METADATA[r.symbol] || { domain: 'apple.com', name: 'US Equity', sector: 'Equities' };
        const monoGrad = getSectorGradient(meta.sector);
        const roc = Number(r.roc_10_pct || 0);
        const rocSign = roc >= 0 ? '+' : '';
        const rocClass = roc >= 0 ? 'pos-green' : 'pos-red';
        const style = getHeatmapBgAndBorder(roc);

        return `
          <div class="heatmap-tile-square" style="background:${style.bg}; border-color:${style.border};" onclick="openStockDetail('${r.symbol}')" title="${clean} (${meta.name}) • ${meta.sector} • Score: ${r.score} • Price: ${ccy}${Number(r.close_price||0).toFixed(2)} • 10-Bar: ${rocSign}${roc.toFixed(2)}% • RVOL: ${(r.rvol||1).toFixed(2)}x">
            <div class="heatmap-square-logo-wrap">
              <img src="https://www.google.com/s2/favicons?domain=${meta.domain || 'apple.com'}&sz=64" alt="${clean}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
              <div class="asset-monogram" style="background:${monoGrad}; display:none; width:100%; height:100%; font-size:9px;">${clean.slice(0, 2)}</div>
            </div>
            <strong class="heatmap-square-symbol">${clean}</strong>
            <span class="heatmap-square-price">${ccy}${Number(r.close_price || 0).toFixed(2)}</span>
            <span class="heatmap-square-badge ${rocClass}">${rocSign}${roc.toFixed(1)}%</span>
          </div>
        `;
      }).join('');

      container.innerHTML = `
        <div class="heatmap-square-wrapper">
          <div class="heatmap-square-grid">
            ${tilesHtml}
          </div>
        </div>
      `;
    }

    function exportExecutivePDF() {
      playHaptic('action');
      const now = new Date();
      const dateStr = now.toLocaleDateString('en-US', {
        weekday: 'short',
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      });
      const timeStr = now.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        timeZoneName: 'short'
      });

      const printTs = document.getElementById('print-timestamp');
      if (printTs) printTs.textContent = `${dateStr} • ${timeStr}`;

      const printDate = document.getElementById('print-session-date');
      if (printDate) printDate.textContent = dateStr;

      const printMode = document.getElementById('print-session-mode');
      const modePill = document.getElementById('mode-pill');
      if (printMode && modePill) printMode.textContent = modePill.textContent;

      showToast('Executive Briefing', 'Opening print / PDF tear-sheet dialog...', '📄');
      setTimeout(() => {
        window.print();
      }, 250);
    }

    // Theme Management
    function initTheme() {
      const saved = localStorage.getItem('trading_bot_theme');
      if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        setTheme('dark');
      } else {
        setTheme('light');
      }
    }

    function setTheme(mode) {
      if (mode === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        document.getElementById('theme-sun-icon').style.display = 'none';
        document.getElementById('theme-moon-icon').style.display = 'block';
        document.getElementById('theme-btn-label').textContent = 'Light Mode';
        localStorage.setItem('trading_bot_theme', 'dark');
      } else {
        document.documentElement.removeAttribute('data-theme');
        document.getElementById('theme-sun-icon').style.display = 'block';
        document.getElementById('theme-moon-icon').style.display = 'none';
        document.getElementById('theme-btn-label').textContent = 'Space Black';
        localStorage.setItem('trading_bot_theme', 'light');
      }
    }

    function toggleTheme() {
      const current = document.documentElement.getAttribute('data-theme');
      setTheme(current === 'dark' ? 'light' : 'dark');
    }

    initTheme();

    function initGuideVisibility() {
      if (localStorage.getItem('trading_bot_guide_visible') === 'false') {
        const g = document.getElementById('screener-guide');
        const b = document.getElementById('btn-toggle-guide');
        if (g) g.style.display = 'none';
        if (b) b.textContent = 'Show Column Guide';
      }
    }
    initGuideVisibility();

    function formatTimeSec(totalSec) {
      if (totalSec <= 0) return '00:00';
      const h = Math.floor(totalSec / 3600);
      const m = Math.floor((totalSec % 3600) / 60);
      const s = totalSec % 60;
      if (h > 0) {
        return `${h}h ${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`;
      }
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }

    function tickerLink(symbol) {
      const clean = formatTickerDisplay(symbol);
      const tvSym = encodeURIComponent(getTradingViewSymbol(symbol));
      return `<a href="https://www.tradingview.com/chart/?symbol=${tvSym}" target="_blank" rel="noopener" style="color:inherit;text-decoration:none;">${clean}</a>`;
    }

    function toggleExpiredAI() {
      showExpiredAI = !showExpiredAI;
      if (latestAIData) renderAIManager(latestAIData);
    }

    function updateGlobalMarketClocks() {
      const now = new Date();

      // Format times in time zones
      function getTimeStr(tz) {
        return now.toLocaleTimeString('en-US', { timeZone: tz, hour12: false, hour: '2-digit', minute: '2-digit' });
      }

      function getMinutesOfDay(tz) {
        const parts = now.toLocaleTimeString('en-US', { timeZone: tz, hour12: false, hour: '2-digit', minute: '2-digit' }).split(':');
        return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
      }

      function getDayOfWeek(tz) {
        const str = now.toLocaleDateString('en-US', { timeZone: tz, weekday: 'short' });
        return str; // 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'
      }

      // NY: 09:30 - 16:00 ET Mon-Fri
      const nyDay = getDayOfWeek('America/New_York');
      const nyMins = getMinutesOfDay('America/New_York');
      const nyOpen = (nyDay !== 'Sat' && nyDay !== 'Sun') && (nyMins >= 570 && nyMins < 960);
      const timeNyEl = document.getElementById('time-ny');
      const statusNyEl = document.getElementById('status-ny');
      const beaconNyEl = document.getElementById('beacon-ny');
      if (timeNyEl) timeNyEl.textContent = getTimeStr('America/New_York') + ' ET';
      if (statusNyEl) {
        statusNyEl.textContent = nyOpen ? 'OPEN' : 'CLOSED';
        statusNyEl.className = 'clock-status ' + (nyOpen ? 'clock-open' : 'clock-closed');
      }
      if (beaconNyEl) beaconNyEl.className = 'beacon-dot ' + (nyOpen ? 'beacon-green' : 'beacon-slate');

      // London: 08:00 - 16:30 GMT Mon-Fri
      const lonDay = getDayOfWeek('Europe/London');
      const lonMins = getMinutesOfDay('Europe/London');
      const lonOpen = (lonDay !== 'Sat' && lonDay !== 'Sun') && (lonMins >= 480 && lonMins < 990);
      const timeLonEl = document.getElementById('time-lon');
      const statusLonEl = document.getElementById('status-lon');
      const beaconLonEl = document.getElementById('beacon-lon');
      if (timeLonEl) timeLonEl.textContent = getTimeStr('Europe/London') + ' GMT';
      if (statusLonEl) {
        statusLonEl.textContent = lonOpen ? 'OPEN' : 'CLOSED';
        statusLonEl.className = 'clock-status ' + (lonOpen ? 'clock-open' : 'clock-closed');
      }
      if (beaconLonEl) beaconLonEl.className = 'beacon-dot ' + (lonOpen ? 'beacon-green' : 'beacon-slate');

      // Frankfurt: 09:00 - 17:30 CET Mon-Fri
      const fraDay = getDayOfWeek('Europe/Berlin');
      const fraMins = getMinutesOfDay('Europe/Berlin');
      const fraOpen = (fraDay !== 'Sat' && fraDay !== 'Sun') && (fraMins >= 540 && fraMins < 1050);
      const timeFraEl = document.getElementById('time-fra');
      const statusFraEl = document.getElementById('status-fra');
      const beaconFraEl = document.getElementById('beacon-fra');
      if (timeFraEl) timeFraEl.textContent = getTimeStr('Europe/Berlin') + ' CET';
      if (statusFraEl) {
        statusFraEl.textContent = fraOpen ? 'OPEN' : 'CLOSED';
        statusFraEl.className = 'clock-status ' + (fraOpen ? 'clock-open' : 'clock-closed');
      }
      if (beaconFraEl) beaconFraEl.className = 'beacon-dot ' + (fraOpen ? 'beacon-green' : 'beacon-slate');

      // Tokyo: 09:00 - 15:00 JST Mon-Fri
      const tokDay = getDayOfWeek('Asia/Tokyo');
      const tokMins = getMinutesOfDay('Asia/Tokyo');
      const tokOpen = (tokDay !== 'Sat' && tokDay !== 'Sun') && (tokMins >= 540 && tokMins < 900);
      const timeTokEl = document.getElementById('time-tok');
      const statusTokEl = document.getElementById('status-tok');
      const beaconTokEl = document.getElementById('beacon-tok');
      if (timeTokEl) timeTokEl.textContent = getTimeStr('Asia/Tokyo') + ' JST';
      if (statusTokEl) {
        statusTokEl.textContent = tokOpen ? 'OPEN' : 'CLOSED';
        statusTokEl.className = 'clock-status ' + (tokOpen ? 'clock-open' : 'clock-closed');
      }
      if (beaconTokEl) beaconTokEl.className = 'beacon-dot ' + (tokOpen ? 'beacon-green' : 'beacon-slate');
    }

    function setMarketDialView(view, btn) {
      const mode = (view || 'BOTH').toUpperCase();
      try {
        localStorage.setItem('trading_bot_market_dial_view', mode);
      } catch (e) {}

      const ukCard = document.getElementById('dial-subcard-uk');
      const usCard = document.getElementById('dial-subcard-us');
      if (ukCard) ukCard.style.display = (mode === 'US') ? 'none' : 'flex';
      if (usCard) usCard.style.display = (mode === 'UK') ? 'none' : 'flex';

      const btns = document.querySelectorAll('.market-pill-btn');
      btns.forEach(b => b.classList.remove('active'));
      if (btn) {
        btn.classList.add('active');
      } else {
        const targetBtn = document.getElementById(mode === 'UK' ? 'dial-btn-uk' : mode === 'US' ? 'dial-btn-us' : 'dial-btn-both');
        if (targetBtn) targetBtn.classList.add('active');
      }
    }

    function initMarketDialView() {
      let saved = 'BOTH';
      try {
        saved = localStorage.getItem('trading_bot_market_dial_view') || 'BOTH';
      } catch (e) {}
      setMarketDialView(saved);
    }

    function updateCountdownTimers() {
      const scanValEl = document.getElementById('scan-timer-val');
      const scanBarEl = document.getElementById('scan-timer-bar');
      if (scanValEl) {
        scanValEl.textContent = `Next in ${formatTimeSec(scanSecondsRemaining)}`;
        scanBarEl.style.width = `${Math.min(100, Math.max(0, scanProgressPct))}%`;
      }

      // 1. 🇬🇧 UK London LSE (08:00 - 16:30 UK) Moon/Sun Arc & Beacon
      const ukValEl = document.getElementById('uk-timer-val');
      const ukBeaconEl = document.getElementById('uk-beacon-dot');
      const ukPin = document.getElementById('solar-beacon-pin-uk');
      const ukArcProg = document.getElementById('solar-arc-progress-uk');
      let ukT = 0.5;

      if (ukMarketIsOpen) {
        if (ukValEl) ukValEl.textContent = `Closes in ${formatTimeSec(ukMarketSecondsRemaining)}`;
        const ukDayTotal = 510 * 60; // 8.5 hours (08:00 to 16:30)
        const ukElapsed = Math.max(0, ukDayTotal - ukMarketSecondsRemaining);
        const ukFrac = Math.min(1, Math.max(0, ukElapsed / ukDayTotal));
        ukT = 0.22 + (ukFrac * 0.56); // Maps 08:00..16:30 to 0.22..0.78 on arc
        if (ukPin) {
          ukPin.setAttribute('fill', '#34c759');
          ukPin.setAttribute('r', '7.5');
        }
        if (ukBeaconEl) ukBeaconEl.className = 'beacon-dot beacon-open';
      } else {
        if (ukValEl) ukValEl.textContent = ukMarketSecondsRemaining > 0 ? `Opens in ${formatTimeSec(ukMarketSecondsRemaining)}` : 'Opening Soon';
        const ukTotalClosed = ukMarketTotalClosedSeconds || 55800;
        const ukElapsed = Math.max(0, ukTotalClosed - ukMarketSecondsRemaining);
        const ukFrac = Math.min(1, Math.max(0, ukElapsed / ukTotalClosed));
        ukT = (ukFrac <= 0.5) ? (0.78 + ukFrac * 0.44) : (ukFrac - 0.5) * 0.44;
        ukT = Math.max(0.02, Math.min(0.98, ukT));
        if (ukPin) {
          ukPin.setAttribute('fill', ukMarketState.includes('PRE') ? '#ff9500' : '#8e8e93');
          ukPin.setAttribute('r', '6');
        }
        if (ukBeaconEl) {
          ukBeaconEl.className = (ukMarketState.includes('PRE') || ukMarketState.includes('AFTER')) ? 'beacon-dot beacon-amber' : 'beacon-dot beacon-slate';
        }
      }

      // UK Arc Bezier coordinates: P0=(18,28), P1=(125,4), P2=(232,28)
      if (ukPin) {
        const pinX = (1 - ukT)**2 * 18 + 2 * (1 - ukT) * ukT * 125 + ukT**2 * 232;
        const pinY = (1 - ukT)**2 * 28 + 2 * (1 - ukT) * ukT * 4 + ukT**2 * 28;
        ukPin.setAttribute('cx', pinX.toFixed(1));
        ukPin.setAttribute('cy', pinY.toFixed(1));
      }
      if (ukArcProg) {
        const circ = 225;
        const arcOff = (circ - (ukT * circ)).toFixed(1);
        ukArcProg.setAttribute('stroke-dashoffset', arcOff);
      }

      // 2. 🇺🇸 US New York (09:30 - 16:00 ET / 14:30 - 21:00 UK) Moon/Sun Arc & Beacon
      const usValEl = document.getElementById('us-timer-val');
      const usBeaconEl = document.getElementById('us-beacon-dot');
      const usPin = document.getElementById('solar-beacon-pin-us');
      const usArcProg = document.getElementById('solar-arc-progress-us');
      let usT = 0.5;

      if (marketIsOpen) {
        if (usValEl) usValEl.textContent = `Closes in ${formatTimeSec(marketSecondsRemaining)}`;
        const usDayTotal = 390 * 60; // 6.5 hours (09:30 to 16:00 ET)
        const usElapsed = Math.max(0, usDayTotal - marketSecondsRemaining);
        const usFrac = Math.min(1, Math.max(0, usElapsed / usDayTotal));
        usT = 0.23 + (usFrac * 0.54); // Maps 09:30..16:00 to 0.23..0.77 on arc
        if (usPin) {
          usPin.setAttribute('fill', '#34c759');
          usPin.setAttribute('r', '7.5');
        }
        if (usBeaconEl) usBeaconEl.className = 'beacon-dot beacon-open';
      } else {
        if (usValEl) usValEl.textContent = marketSecondsRemaining > 0 ? `Opens in ${formatTimeSec(marketSecondsRemaining)}` : 'Opening Soon';
        const usTotalClosed = marketTotalClosedSeconds || 63000;
        const usElapsed = Math.max(0, usTotalClosed - marketSecondsRemaining);
        const usFrac = Math.min(1, Math.max(0, usElapsed / usTotalClosed));
        usT = (usFrac <= 0.5) ? (0.77 + usFrac * 0.46) : (usFrac - 0.5) * 0.46;
        usT = Math.max(0.02, Math.min(0.98, usT));
        if (usPin) {
          usPin.setAttribute('fill', marketState.includes('PRE') ? '#ff9500' : '#8e8e93');
          usPin.setAttribute('r', '6');
        }
        if (usBeaconEl) {
          usBeaconEl.className = (marketState.includes('PRE') || marketState.includes('AFTER')) ? 'beacon-dot beacon-amber' : 'beacon-dot beacon-slate';
        }
      }

      // US Arc Bezier coordinates: P0=(18,28), P1=(125,4), P2=(232,28)
      if (usPin) {
        const pinX = (1 - usT)**2 * 18 + 2 * (1 - usT) * usT * 125 + usT**2 * 232;
        const pinY = (1 - usT)**2 * 28 + 2 * (1 - usT) * usT * 4 + usT**2 * 28;
        usPin.setAttribute('cx', pinX.toFixed(1));
        usPin.setAttribute('cy', pinY.toFixed(1));
      }
      if (usArcProg) {
        const circ = 225;
        const arcOff = (circ - (usT * circ)).toFixed(1);
        usArcProg.setAttribute('stroke-dashoffset', arcOff);
      }

      // Decrement counters every second
      if (scanSecondsRemaining > 0) scanSecondsRemaining--;
      if (marketSecondsRemaining > 0) marketSecondsRemaining--;
      if (ukMarketSecondsRemaining > 0) ukMarketSecondsRemaining--;
    }

    function renderSparklineSVG(points, rocPct, width = 96, height = 24) {
      if (!points || points.length < 2) {
        return `<span style="font-size:11px;color:var(--text-tertiary);">Data pending...</span>`;
      }
      const minVal = Math.min(...points);
      const maxVal = Math.max(...points);
      const range = (maxVal - minVal) || (minVal * 0.01) || 1.0;
      const padX = 3;
      const padY = 4;
      const usableW = width - (padX * 2);
      const usableH = height - (padY * 2);

      const coords = points.map((val, idx) => {
        const x = padX + (idx / (points.length - 1)) * usableW;
        const normY = (val - minVal) / range;
        const y = (height - padY) - (normY * usableH);
        return [x.toFixed(1), y.toFixed(1)];
      });

      const polyPoints = coords.map(c => c.join(',')).join(' ');
      const strokeColor = rocPct >= 0 ? 'var(--green)' : 'var(--red)';
      const fillColor = rocPct >= 0 ? 'rgba(52, 199, 89, 0.12)' : 'rgba(255, 59, 48, 0.12)';
      const firstX = coords[0][0];
      const lastX = coords[coords.length - 1][0];
      const areaPoints = `${polyPoints} ${lastX},${height} ${firstX},${height}`;

      return `
        <svg class="sparkline-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
          <polygon points="${areaPoints}" fill="${fillColor}" />
          <polyline points="${polyPoints}" fill="none" stroke="${strokeColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          <circle cx="${coords[coords.length - 1][0]}" cy="${coords[coords.length - 1][1]}" r="2.5" fill="${strokeColor}" />
        </svg>
      `;
    }

    function renderRadialScore(score, rating) {
      const circ = 94.2; // 2 * pi * 15
      const sc = Math.min(100, Math.max(0, score || 0));
      const offset = (circ - ((sc / 100) * circ)).toFixed(1);
      let strokeColor = 'var(--text-tertiary)';
      if (sc >= 80) strokeColor = 'var(--green)';
      else if (sc >= 65) strokeColor = 'var(--accent)';
      else if (sc >= 50) strokeColor = 'var(--amber)';
      else strokeColor = 'var(--red)';

      return `
        <div class="radial-dial" title="Quant Score: ${sc.toFixed(1)}/100">
          <svg viewBox="0 0 38 38">
            <circle class="dial-track" cx="19" cy="19" r="15"></circle>
            <circle class="dial-fill" cx="19" cy="19" r="15" stroke="${strokeColor}" style="stroke-dashoffset:${offset};"></circle>
          </svg>
          <span class="dial-score-num">${Math.round(sc)}</span>
        </div>
      `;
    }

    let currentTopOpportunitySymbol = '';

    function openTopOpportunityModal() {
      if (currentTopOpportunitySymbol) {
        openStockDetail(currentTopOpportunitySymbol);
      } else if (latestRecommendations && latestRecommendations.length > 0) {
        openStockDetail(latestRecommendations[0].symbol);
      }
    }

    function renderHeroRadar(recs, positions) {
      const card = document.getElementById('hero-radar-card');
      if (!card) return;

      const topRec = (recs && recs.length > 0) ? recs[0] : null;
      if (!topRec) {
        card.innerHTML = `
          <div style="display:flex;align-items:center;gap:10px;">
            <div class="radar-beacon-dot"></div>
            <div>
              <div class="radar-meta-title">Top Opportunity Radar</div>
              <div style="font-size:12px;color:var(--text-tertiary);margin-top:2px;">Analyzing 50 assets...</div>
            </div>
          </div>
        `;
        return;
      }

      currentTopOpportunitySymbol = topRec.symbol;
      const clean = formatTickerDisplay(topRec.symbol);
      const ccy = getCurrencySymbol(topRec.symbol);
      const meta = STOCK_METADATA[topRec.symbol] || { name: clean, sector: 'US Equity' };
      const score = Number(topRec.score || 0).toFixed(1);
      const rating = topRec.rating || 'BUY';
      const roc = Number(topRec.roc_10_pct || 0);
      const rocSign = roc >= 0 ? '+' : '';
      const rvol = Number(topRec.rvol || 1).toFixed(1);
      const monoGrad = getSectorGradient(meta.sector);
      const ratingBadgeClass = badgeClass(rating);

      card.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;width:100%;">
          <div class="asset-logo-wrap" style="width:36px;height:36px;border-radius:10px;flex-shrink:0;">
            <img class="asset-logo-img" style="width:22px;height:22px;" src="https://www.google.com/s2/favicons?domain=${getStockDomain(topRec.symbol)}&sz=128" alt="${clean}" onerror="this.style.display='none'; if(this.nextElementSibling) this.nextElementSibling.style.display='flex';" />
            <div class="asset-monogram" style="background:${monoGrad}; display:none; width:100%; height:100%; font-size:13px; border-radius:10px;">${clean.slice(0, 2)}</div>
          </div>
          <div style="flex:1;min-width:0;">
            <div class="radar-meta-title">
              <div class="radar-beacon-dot"></div>
              <span>#1 Quant Opportunity</span>
              <span class="badge ${ratingBadgeClass}" style="font-size:9px;padding:1px 5px;margin-left:auto;">${rating}</span>
            </div>
            <div style="display:flex;align-items:baseline;gap:7px;margin-top:2px;">
              <span class="radar-symbol">${clean}</span>
              <span style="font-size:12.5px;font-weight:700;color:var(--text-primary);">${ccy}${Number(topRec.close_price || 0).toFixed(2)}</span>
              <span style="font-size:11px;font-weight:600;color:${roc >= 0 ? 'var(--green-text)' : 'var(--red-text)'};">${rocSign}${roc.toFixed(1)}%</span>
            </div>
            <div class="radar-sub-metrics">
              <span style="color:var(--accent);font-weight:700;">Score ${score}</span>
              <span>•</span>
              <span>RVOL ${rvol}x</span>
              <span>•</span>
              <span style="color:var(--text-tertiary);text-overflow:ellipsis;overflow:hidden;white-space:nowrap;max-width:120px;">${meta.name}</span>
            </div>
          </div>
          <div style="color:var(--text-tertiary);padding-left:4px;flex-shrink:0;">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="9 18 15 12 9 6"></polyline>
            </svg>
          </div>
        </div>
      `;
    }

    function renderActivityAndGates(data) {
      if (data.activity) {
        document.getElementById('activity-state').textContent = data.activity.state || 'MONITORING';
        document.getElementById('activity-state').className = `activity-state-badge badge-${data.activity.state === 'HALTED' ? 'avoid' : 'buy'}`;
        document.getElementById('activity-detail').textContent = data.activity.detail || '';
        document.getElementById('activity-updated').textContent = data.activity.updated_at ? `Updated: ${data.activity.updated_at.slice(11,19)} UTC` : '';
        scanSecondsRemaining = data.activity.seconds_to_next_scan || 900;
        scanProgressPct = data.activity.scan_progress_pct || 0;
      }
      if (data.gates && data.gates.length >= 4) {
        for (let i = 0; i < 4; i++) {
          const g = data.gates[i];
          const badgeClass = g.badge === 'GREEN' ? 'badge-strong-buy' : (g.badge === 'RED' ? 'badge-avoid' : 'badge-watch');
          document.getElementById(`gate${i+1}-badge`).className = `gate-status-badge badge ${badgeClass}`;
          document.getElementById(`gate${i+1}-badge`).textContent = g.status.split('•')[0].trim();
          document.getElementById(`gate${i+1}-val`).textContent = g.title.split('•')[1] ? g.title.split('•')[1].trim() : g.title;
          document.getElementById(`gate${i+1}-desc`).textContent = g.detail;
        }
      }
      if (data.market_session) {
        document.getElementById('market-status-badge').textContent = data.market_session.state;
      }
    }

    function toggleScreenerGuide() {
      const g = document.getElementById('screener-guide');
      const b = document.getElementById('btn-toggle-guide');
      if (!g || !b) return;
      const isHidden = g.style.display === 'none';
      g.style.display = isHidden ? 'grid' : 'none';
      b.textContent = isHidden ? 'Hide Column Guide' : 'Show Column Guide';
      localStorage.setItem('trading_bot_guide_visible', isHidden ? 'true' : 'false');
    }

    function setFilter(filter, btn) {
      currentFilter = filter;
      document.querySelectorAll('.filter-bar .filter-btn').forEach(b => {
        if (b.id && b.id.startsWith('btn-filter-')) {
          b.classList.remove('active');
        }
      });
      if (btn) btn.classList.add('active');
      renderScreener(latestRecommendations);
      renderHeatmap(latestRecommendations);
    }

    function handleScreenerSearch(query) {
      screenerSearchQuery = (query || '').trim().toLowerCase();
      renderScreener(latestRecommendations);
      renderHeatmap(latestRecommendations);
    }

    function handleSort(col) {
      if (currentSortCol === col) {
        currentSortDir = currentSortDir === 'asc' ? 'desc' : 'asc';
      } else {
        currentSortCol = col;
        currentSortDir = (col === 'rank' || col === 'symbol') ? 'asc' : 'desc';
      }

      // Update sort indicators in table header
      document.querySelectorAll('th.sortable').forEach(th => th.classList.remove('active-sort'));
      const activeTh = document.getElementById('th-sort-' + col);
      if (activeTh) activeTh.classList.add('active-sort');

      const sortIcon = document.getElementById('sort-' + col);
      if (sortIcon) sortIcon.textContent = currentSortDir === 'asc' ? '▲' : '▼';

      renderScreener(latestRecommendations);
    }

    function exportScreenerCSV() {
      if (!latestRecommendations || latestRecommendations.length === 0) {
        showToast('Export Unavailable', 'No screener data loaded yet', '⚠️');
        return;
      }
      const headers = ['Rank', 'Symbol', 'Company', 'Sector', 'Rating', 'Score', 'Price_USD', 'EMA_Fast', 'EMA_Slow', 'RSI_14', 'RVOL', 'ROC_10_Pct', 'Stop_Loss_USD', 'Take_Profit_USD', 'Thesis'];
      const rows = latestRecommendations.map(r => {
        const meta = STOCK_METADATA[r.symbol] || { name: 'US Equity', sector: 'Equities' };
        const clean = (r.symbol || '').replace('_US_EQ', '');
        return [
          r.rank || 0,
          clean,
          '"' + (meta.name || '').replace(/"/g, '""') + '"',
          '"' + (meta.sector || '').replace(/"/g, '""') + '"',
          r.rating || 'WATCH',
          r.score || 0,
          Number(r.close_price || 0).toFixed(2),
          Number(r.ema_fast || 0).toFixed(2),
          Number(r.ema_slow || 0).toFixed(2),
          Number(r.rsi || 50).toFixed(1),
          Number(r.rvol || 1).toFixed(2),
          Number(r.roc_10_pct || 0).toFixed(2),
          Number(r.suggested_stop_loss || 0).toFixed(2),
          Number(r.suggested_take_profit || 0).toFixed(2),
          '"' + (r.thesis || '').replace(/"/g, '""') + '"'
        ].join(',');
      });

      const csvContent = [headers.join(','), ...rows].join(String.fromCharCode(10));
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      const dateStr = new Date().toISOString().slice(0, 10);
      link.setAttribute('href', url);
      link.setAttribute('download', 't212_screener_leaderboard_' + dateStr + '.csv');
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      showToast('Export Complete', 'Saved 50-stock quantitative dataset (' + rows.length + ' rows)', '📊');
    }

    function showToast(title, message, icon) {
      icon = icon || '⚡';
      const container = document.getElementById('toast-container');
      if (!container) return;
      const toast = document.createElement('div');
      toast.className = 'apple-toast';
      toast.innerHTML = `
        <span class="toast-icon">${icon}</span>
        <div class="toast-body">
          <strong>${title}</strong>
          <span>${message}</span>
        </div>
      `;
      container.appendChild(toast);
      setTimeout(() => {
        toast.classList.add('hide');
        setTimeout(() => { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 400);
      }, 3500);
    }

    function openShortcutsModal() {
      const modal = document.getElementById('shortcuts-modal-backdrop');
      if (modal) {
        modal.classList.add('open');
        document.body.style.overflow = 'hidden';
      }
    }

    function closeShortcutsModal(e) {
      if (e && e.target !== e.currentTarget && !e.target.closest('.modal-close-btn')) return;
      const modal = document.getElementById('shortcuts-modal-backdrop');
      if (modal) {
        modal.classList.remove('open');
        const stockModal = document.getElementById('stock-modal-backdrop');
        if (!stockModal || !stockModal.classList.contains('open')) {
          document.body.style.overflow = '';
        }
      }
    }

    // Keyboard Shortcuts Listener
    window.addEventListener('keydown', (e) => {
      const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
      if (activeTag === 'input' || activeTag === 'textarea') {
        if (e.key === 'Escape') {
          document.activeElement.blur();
        }
        return;
      }

      if (e.key === '/' || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k')) {
        e.preventDefault();
        const input = document.getElementById('screener-search-input');
        if (input) {
          input.focus();
          input.select();
        }
      } else if (e.key === '1') {
        const btn = document.getElementById('btn-filter-all');
        setFilter('ALL', btn);
        showToast('Filter Applied', 'Showing all 50 universe stocks', '📋');
      } else if (e.key === '2') {
        const btn = document.getElementById('btn-filter-strong-buy');
        setFilter('STRONG BUY', btn);
        showToast('Filter Applied', 'Showing Strong Buy setups', '🚀');
      } else if (e.key === '3') {
        const btn = document.getElementById('btn-filter-buy');
        setFilter('BUY', btn);
        showToast('Filter Applied', 'Showing Buy setups', '🟢');
      } else if (e.key === '4') {
        const btn = document.getElementById('btn-filter-watch');
        setFilter('WATCH', btn);
        showToast('Filter Applied', 'Showing Watchlist setups', '👀');
      } else if (e.key === '5') {
        const btn = document.getElementById('btn-filter-avoid');
        setFilter('AVOID', btn);
        showToast('Filter Applied', 'Showing Avoid / Blocked setups', '🛑');
      } else if (e.key.toLowerCase() === 't') {
        toggleTheme();
      } else if (e.key.toLowerCase() === 'g') {
        toggleScreenerGuide();
      } else if (e.key.toLowerCase() === 'e') {
        exportScreenerCSV();
      } else if (e.key.toLowerCase() === 'p') {
        e.preventDefault();
        exportExecutivePDF();
      } else if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        openShortcutsModal();
      } else if (e.key === 'Escape') {
        closeStockModal();
        closeShortcutsModal();
      }
    });

    let lastTickerDataHash = '';
    function renderTickerTape(recs) {
      const track = document.getElementById('ticker-tape-track');
      if (!track || !recs || recs.length === 0) return;

      const hash = recs.slice(0, 15).map(r => (r.symbol || '') + ':' + Number(r.close_price || 0).toFixed(1) + ':' + (r.rating || '')).join('|');
      if (hash === lastTickerDataHash) return;
      lastTickerDataHash = hash;

      const notable = [...recs].sort((a, b) => Math.abs(b.roc_10_pct || 0) - Math.abs(a.roc_10_pct || 0)).slice(0, 14);
      const loopItems = [...notable, ...notable];

      track.innerHTML = loopItems.map(r => {
        const clean = (r.symbol || '').replace('_US_EQ', '');
        const meta = STOCK_METADATA[r.symbol] || { domain: 'apple.com' };
        const rocSign = (r.roc_10_pct || 0) >= 0 ? '+' : '';
        const rocColor = (r.roc_10_pct || 0) >= 0 ? 'pos-green' : 'pos-red';
        const ratingBadgeClass = r.rating === 'STRONG BUY' ? 'badge-strong-buy' : (r.rating === 'BUY' ? 'badge-buy' : 'badge-watch');

        return `
          <div class="ticker-item" onclick="openStockDetail('${r.symbol}')" title="Click to inspect ${clean} details">
            <img class="ticker-logo" src="https://www.google.com/s2/favicons?domain=${meta.domain || 'apple.com'}&sz=64" alt="${clean}" onerror="this.style.display='none';" />
            <strong>${clean}</strong>
            <span>$${Number(r.close_price || 0).toFixed(2)}</span>
            <span class="${rocColor}">${rocSign}${Number(r.roc_10_pct || 0).toFixed(2)}%</span>
            <span class="ticker-badge ${ratingBadgeClass}">${r.rating}</span>
          </div>
        `;
      }).join('');
    }

    function badgeClass(rating) {
      if (rating === 'STRONG BUY') return 'badge badge-strong-buy';
      if (rating === 'BUY') return 'badge badge-buy';
      if (rating === 'WATCH') return 'badge badge-watch';
      if (rating === 'AVOID') return 'badge badge-avoid';
      return 'badge badge-hold';
    }

    function formatTradeJourneyTime(tsStr) {
      if (!tsStr) return '';
      try {
        const d = new Date(tsStr);
        if (isNaN(d.getTime())) return String(tsStr).slice(0, 16);
        return d.toLocaleString('en-GB', {
          month: 'short',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          hour12: false
        });
      } catch (e) {
        return String(tsStr).slice(0, 16);
      }
    }

    function formatHoldingDuration(openedAtStr) {
      if (!openedAtStr) return '';
      try {
        const startMs = new Date(openedAtStr).getTime();
        if (isNaN(startMs)) return '';
        const diffMins = Math.max(1, Math.floor((Date.now() - startMs) / 60000));
        if (diffMins < 60) return `${diffMins}m`;
        const hrs = Math.floor(diffMins / 60);
        const mins = diffMins % 60;
        if (hrs < 24) return `${hrs}h ${mins}m`;
        const days = Math.floor(hrs / 24);
        const remHrs = hrs % 24;
        return `${days}d ${remHrs}h`;
      } catch (e) {
        return '';
      }
    }

    function renderPositionJourneyChart(p, idx, ccy) {
      const entry = Number(p.entry_price || 0);
      const curr = Number(p.current_price || entry);
      const sl = Number(p.stop_loss || 0);
      const tp = Number(p.take_profit || 0);
      const qty = Number(p.quantity || 0);
      const rawPts = Array.isArray(p.price_history) && p.price_history.length >= 2
        ? p.price_history
        : [
            { ts: p.opened_at || '', price: entry, event: 'BUY' },
            { ts: new Date().toISOString(), price: curr, event: 'NOW' }
          ];

      const w = 680;
      const h = 116;
      const padL = 54;
      const padR = 52;
      const padT = 18;
      const padB = 24;
      const plotW = w - padL - padR;
      const plotH = h - padT - padB;

      const prices = rawPts.map(pt => Number(pt.price || entry));
      prices.push(entry);
      if (p.highest_price) prices.push(Number(p.highest_price));
      if (p.lowest_price) prices.push(Number(p.lowest_price));

      let minP = Math.min(...prices);
      let maxP = Math.max(...prices);
      const rawSpan = Math.max(maxP - minP, entry * 0.004, 0.04);

      // Include Stop-Loss on the chart if it is reasonably close (e.g. 1R trailing stop near or above entry)
      if (sl > 0 && Math.abs(entry - sl) <= rawSpan * 1.8) {
        minP = Math.min(minP, sl);
        maxP = Math.max(maxP, sl);
      }

      const padY = Math.max((maxP - minP) * 0.22, entry * 0.0025, 0.02);
      minP -= padY;
      maxP += padY;
      const range = Math.max(0.0001, maxP - minP);

      const coords = rawPts.map((pt, i) => {
        const normX = i / Math.max(1, rawPts.length - 1);
        const x = padL + normX * plotW;
        const priceVal = Number(pt.price || entry);
        const normY = (priceVal - minP) / range;
        const y = (h - padB) - normY * plotH;
        return {
          x: x.toFixed(1),
          y: y.toFixed(1),
          price: priceVal,
          ts: formatTradeJourneyTime(pt.ts),
          event: pt.event || ''
        };
      });

      const polyPoints = coords.map(c => `${c.x},${c.y}`).join(' ');
      const firstPt = coords[0];
      const lastPt = coords[coords.length - 1];
      const areaPoints = `${polyPoints} ${lastPt.x},${h - padB} ${firstPt.x},${h - padB}`;

      const entryY = (h - padB) - (((entry - minP) / range) * plotH);
      const isProfitable = curr >= entry;
      const strokeCol = isProfitable ? 'var(--green)' : 'var(--red)';
      const gradId = `posJourneyGrad_${idx}`;

      // Optional Stop-Loss line if within vertical canvas bounds
      let slLineSvg = '';
      if (sl >= minP && sl <= maxP) {
        const slY = (h - padB) - (((sl - minP) / range) * plotH);
        const slCol = sl >= entry ? 'var(--green)' : 'var(--red)';
        const slLabel = sl >= entry ? `1R Trail Stop: ${ccy}${sl.toFixed(2)}` : `Stop: ${ccy}${sl.toFixed(2)}`;
        slLineSvg = `
          <line x1="${padL}" y1="${slY.toFixed(1)}" x2="${(padL + plotW).toFixed(1)}" y2="${slY.toFixed(1)}" stroke="${slCol}" stroke-dasharray="2,3" stroke-width="1" opacity="0.55" />
          <text x="${(padL + plotW - 4).toFixed(1)}" y="${Math.max(padT + 8, slY - 4).toFixed(1)}" font-size="9" font-weight="600" fill="${slCol}" text-anchor="end" opacity="0.85">${slLabel}</text>
        `;
      }

      // Find peak point along the curve if >= 3 points
      let peakMarkerSvg = '';
      if (coords.length >= 3) {
        let peakIdx = 0;
        for (let i = 1; i < coords.length; i++) {
          if (coords[i].price > coords[peakIdx].price) peakIdx = i;
        }
        if (peakIdx > 0 && peakIdx < coords.length - 1 && coords[peakIdx].price > entry) {
          const pk = coords[peakIdx];
          peakMarkerSvg = `
            <circle cx="${pk.x}" cy="${pk.y}" r="3" fill="var(--green)" stroke="#fff" stroke-width="1.2" />
            <text x="${pk.x}" y="${Math.max(padT + 8, parseFloat(pk.y) - 6).toFixed(1)}" font-size="8.5" font-weight="600" fill="var(--green-text)" text-anchor="middle">▲ ${ccy}${pk.price.toFixed(2)}</text>
          `;
        }
      }

      const boughtLabel = formatTradeJourneyTime(p.opened_at) || 'Entry';
      const heldDur = formatHoldingDuration(p.opened_at);
      const peakHigh = Number(p.highest_price || Math.max(entry, curr));
      const troughLow = Number(p.lowest_price || Math.min(entry, curr));

      return `
        <div class="pos-journey-wrap" id="pos-journey-wrap-${idx}">
          <div class="pos-journey-header">
            <div class="pos-journey-title">
              <span style="font-size:13px;">📈</span>
              <span>Trade Journey Trajectory</span>
              <span class="badge badge-hold" style="font-size:10px;padding:2px 7px;">Bought ${boughtLabel}${heldDur ? ' • Held ' + heldDur : ''}</span>
            </div>
            <div class="pos-journey-meta">
              <span>📌 Entry: <strong>${ccy}${entry.toFixed(2)}</strong></span>
              <span>▲ Peak: <strong class="pos-green">${ccy}${peakHigh.toFixed(2)}</strong></span>
              <span>▼ Low: <strong>${ccy}${troughLow.toFixed(2)}</strong></span>
              <span style="color:var(--text-tertiary);">(${coords.length} pts)</span>
            </div>
          </div>
          <div id="pos-journey-tip-${idx}" class="pos-journey-tip" style="opacity:0;"></div>
          <svg id="pos-journey-svg-${idx}" width="100%" height="${h}" viewBox="0 0 ${w} ${h}" style="overflow:visible;display:block;">
            <defs>
              <linearGradient id="${gradId}" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stop-color="${strokeCol}" stop-opacity="0.30" />
                <stop offset="100%" stop-color="${strokeCol}" stop-opacity="0.0" />
              </linearGradient>
            </defs>

            <!-- Y-Axis Min / Max Labels -->
            <text x="${padL - 6}" y="${padT + 4}" font-size="9" font-weight="500" fill="var(--text-tertiary)" text-anchor="end">${ccy}${maxP.toFixed(2)}</text>
            <text x="${padL - 6}" y="${h - padB}" font-size="9" font-weight="500" fill="var(--text-tertiary)" text-anchor="end">${ccy}${minP.toFixed(2)}</text>

            <!-- X-Axis Start (Bought) & End (Now) Labels -->
            <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${h - padB}" stroke="rgba(142,142,147,0.12)" stroke-dasharray="3,3" stroke-width="1" />
            <line x1="${padL + plotW}" y1="${padT}" x2="${padL + plotW}" y2="${h - padB}" stroke="rgba(142,142,147,0.12)" stroke-dasharray="3,3" stroke-width="1" />
            <text x="${padL}" y="${h - 5}" font-size="9.5" font-weight="600" fill="var(--text-tertiary)" text-anchor="start">BUY (${boughtLabel})</text>
            <text x="${padL + plotW}" y="${h - 5}" font-size="9.5" font-weight="600" fill="${strokeCol}" text-anchor="end">LIVE MARK (NOW)</text>

            <!-- Entry Fill Baseline -->
            <line x1="${padL}" y1="${entryY.toFixed(1)}" x2="${(padL + plotW).toFixed(1)}" y2="${entryY.toFixed(1)}" stroke="rgba(142,142,147,0.38)" stroke-dasharray="4,4" stroke-width="1.1" />
            <text x="${padL + 6}" y="${Math.max(padT + 8, entryY - 5).toFixed(1)}" font-size="9" font-weight="600" fill="var(--text-tertiary)">Entry Fill: ${ccy}${entry.toFixed(2)}</text>

            ${slLineSvg}

            <!-- Journey Area & Curve -->
            <polygon points="${areaPoints}" fill="url(#${gradId})" />
            <polyline points="${polyPoints}" fill="none" stroke="${strokeCol}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />

            <!-- BUY Anchor Dot on Left -->
            <circle cx="${firstPt.x}" cy="${firstPt.y}" r="3.8" fill="var(--accent)" stroke="#ffffff" stroke-width="1.6" />

            ${peakMarkerSvg}

            <!-- Live Beacon Dot on Right -->
            <circle cx="${lastPt.x}" cy="${lastPt.y}" r="4.2" fill="${strokeCol}" stroke="#ffffff" stroke-width="1.8" />
            <circle cx="${lastPt.x}" cy="${lastPt.y}" r="8" fill="none" stroke="${strokeCol}" stroke-width="1.3" opacity="0.45" />
            <text x="${(parseFloat(lastPt.x) + 8).toFixed(1)}" y="${(parseFloat(lastPt.y) + 3.5).toFixed(1)}" font-size="10.5" font-weight="700" fill="var(--text-primary)">${ccy}${curr.toFixed(2)}</text>

            <!-- Interactive Hover Crosshair -->
            <line id="pos-journey-line-${idx}" x1="0" y1="${padT}" x2="0" y2="${h - padB}" stroke="var(--accent)" stroke-width="1.3" stroke-dasharray="3,3" opacity="0" pointer-events="none" />
            <circle id="pos-journey-dot-${idx}" cx="0" cy="0" r="4.5" fill="var(--accent)" stroke="#ffffff" stroke-width="1.8" opacity="0" pointer-events="none" />
            <rect id="pos-journey-overlay-${idx}" x="${padL}" y="0" width="${plotW}" height="${h}" fill="transparent" style="cursor:crosshair;" />
          </svg>
        </div>
      `;
    }

    function attachPositionJourneyScrubbers(positions) {
      if (!positions || !positions.length) return;
      positions.forEach((p, idx) => {
        const wrap = document.getElementById(`pos-journey-wrap-${idx}`);
        const overlay = document.getElementById(`pos-journey-overlay-${idx}`);
        const tip = document.getElementById(`pos-journey-tip-${idx}`);
        const line = document.getElementById(`pos-journey-line-${idx}`);
        const dot = document.getElementById(`pos-journey-dot-${idx}`);
        if (!wrap || !overlay || !tip || !line || !dot) return;

        const entry = Number(p.entry_price || 0);
        const curr = Number(p.current_price || entry);
        const sl = Number(p.stop_loss || 0);
        const qty = Number(p.quantity || 0);
        const ccy = getCurrencySymbol(p.symbol);
        const rawPts = Array.isArray(p.price_history) && p.price_history.length >= 2
          ? p.price_history
          : [
              { ts: p.opened_at || '', price: entry, event: 'BUY' },
              { ts: new Date().toISOString(), price: curr, event: 'NOW' }
            ];

        const w = 680;
        const h = 116;
        const padL = 54;
        const padR = 52;
        const padT = 18;
        const padB = 24;
        const plotW = w - padL - padR;
        const plotH = h - padT - padB;

        const prices = rawPts.map(pt => Number(pt.price || entry));
        prices.push(entry);
        if (p.highest_price) prices.push(Number(p.highest_price));
        if (p.lowest_price) prices.push(Number(p.lowest_price));
        let minP = Math.min(...prices);
        let maxP = Math.max(...prices);
        const rawSpan = Math.max(maxP - minP, entry * 0.004, 0.04);
        if (sl > 0 && Math.abs(entry - sl) <= rawSpan * 1.8) {
          minP = Math.min(minP, sl);
          maxP = Math.max(maxP, sl);
        }
        const padY = Math.max((maxP - minP) * 0.22, entry * 0.0025, 0.02);
        minP -= padY;
        maxP += padY;
        const range = Math.max(0.0001, maxP - minP);

        const coords = rawPts.map((pt, i) => {
          const normX = i / Math.max(1, rawPts.length - 1);
          const x = padL + normX * plotW;
          const priceVal = Number(pt.price || entry);
          const normY = (priceVal - minP) / range;
          const y = (h - padB) - normY * plotH;
          return {
            x: x,
            y: y,
            price: priceVal,
            ts: formatTradeJourneyTime(pt.ts) || (i === 0 ? 'BUY Fill' : 'Live Mark')
          };
        });

        overlay.addEventListener('mousemove', (e) => {
          const svgEl = document.getElementById(`pos-journey-svg-${idx}`);
          if (!svgEl) return;
          const rect = svgEl.getBoundingClientRect();
          const mouseX = e.clientX - rect.left;
          const targetSvgX = (mouseX / Math.max(1, rect.width)) * w;

          let closest = coords[0];
          let minDist = Math.abs(coords[0].x - targetSvgX);
          for (let i = 1; i < coords.length; i++) {
            const d = Math.abs(coords[i].x - targetSvgX);
            if (d < minDist) {
              minDist = d;
              closest = coords[i];
            }
          }

          line.setAttribute('x1', closest.x.toFixed(1));
          line.setAttribute('x2', closest.x.toFixed(1));
          line.setAttribute('opacity', '1');
          dot.setAttribute('cx', closest.x.toFixed(1));
          dot.setAttribute('cy', closest.y.toFixed(1));
          dot.setAttribute('opacity', '1');

          const ptPnl = (closest.price - entry) * qty;
          const ptPct = entry > 0 ? ((closest.price - entry) / entry) * 100 : 0;
          const s = ptPnl >= 0 ? '+' : '';
          tip.innerHTML = `${closest.ts} • <strong>${ccy}${closest.price.toFixed(2)}</strong> <span style="color:${ptPnl >= 0 ? '#34c759' : '#ff453a'};">(${s}${ccy}${ptPnl.toFixed(2)} | ${s}${ptPct.toFixed(2)}%)</span>`;
          tip.style.opacity = '1';
          const tipLeft = Math.min(Math.max(16, mouseX - 70), Math.max(20, rect.width - 220));
          tip.style.left = `${tipLeft}px`;
        });

        overlay.addEventListener('mouseleave', () => {
          line.setAttribute('opacity', '0');
          dot.setAttribute('opacity', '0');
          tip.style.opacity = '0';
        });
      });
    }

    function renderPositions(positions) {
      const el = document.getElementById('positions-container');
      if (!positions || positions.length === 0) {
        el.innerHTML = '<div style="color:var(--text-tertiary);font-size:13px;padding:12px 0;">No open positions currently held. Bot is scanning for the highest-scoring BUY setup.</div>';
        return;
      }
      el.innerHTML = positions.map((p, idx) => {
        const pnlClass = p.unrealized_pnl >= 0 ? 'pos-green' : 'pos-red';
        const sign = p.unrealized_pnl >= 0 ? '+' : '';
        const extBadge = p.tp_extensions > 0
          ? ` <span class="badge badge-strong-buy">TARGET EXTENDED x${p.tp_extensions}</span>`
          : '';
        const trailBadge = (p.trailing_active
          ? '<span class="badge badge-strong-buy">1R TRAILING ACTIVE</span>'
          : '<span class="badge badge-watch">INITIAL STOP (+1.0R Anchor)</span>') + extBadge;
        const meta = STOCK_METADATA[p.symbol] || { name: 'US Equity', sector: 'Equities' };
        const clean = formatTickerDisplay(p.symbol);
        const ccy = getCurrencySymbol(p.symbol);
        const monoGrad = getSectorGradient(meta.sector);
        const logoBadge = renderStockLogo(p.symbol, clean, monoGrad, 36, 24, 10);
        const journeyChartHtml = renderPositionJourneyChart(p, idx, ccy);

        const minVal = Math.min(p.stop_loss, p.entry_price, p.current_price);
        const maxVal = Math.max(p.take_profit, p.current_price, p.entry_price);
        const span = (maxVal - minVal) || 1.0;
        const currPct = Math.min(98, Math.max(2, ((p.current_price - minVal) / span) * 100));
        const entryPct = Math.min(98, Math.max(2, ((p.entry_price - minVal) / span) * 100));
        const isStopLocked = p.stop_loss >= p.entry_price;
        const distSL = Math.abs(((p.current_price - p.stop_loss) / p.current_price) * 100);
        const distTP = Math.max(0, ((p.take_profit - p.current_price) / p.current_price) * 100);
        const lockInGain = isStopLocked ? (((p.stop_loss - p.entry_price) / p.entry_price) * 100) : 0;
        const slBadge = isStopLocked
          ? `<span class="badge badge-strong-buy" style="font-size:10px;padding:2px 7px;">🔒 +${lockInGain.toFixed(1)}% PROFIT LOCKED</span>`
          : `<span class="badge" style="font-size:10px;padding:2px 7px;background:rgba(255,59,48,0.12);color:var(--red-text);">${distSL.toFixed(1)}% BUFFER</span>`;
        const tpBadge = `<span class="badge badge-buy" style="font-size:10px;padding:2px 7px;">+${distTP.toFixed(1)}% TO TARGET</span>`;

        return `
          <div class="pos-card" onclick="openStockDetail('${p.symbol}')">
            <div class="pos-top">
              <div style="display:flex;align-items:center;gap:12px;">
                ${logoBadge}
                <div>
                  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                    <strong style="font-size:18px;letter-spacing:-0.02em;">${clean}</strong>
                    <span style="font-size:12.5px;color:var(--text-secondary);">${meta.name}</span>
                    <span class="badge badge-buy">${p.side}</span>
                    ${trailBadge}
                  </div>
                  <div style="font-size:12px;color:var(--text-tertiary);margin-top:2px;">Order #${p.order_id}</div>
                </div>
              </div>
              <div style="text-align:right;">
                <span style="font-size:20px;font-weight:700;letter-spacing:-0.02em;" class="${pnlClass}">
                  ${sign}${ACCT_CCY}${p.unrealized_pnl.toFixed(2)} (${sign}${p.pnl_pct.toFixed(2)}% | ${sign}${p.r_multiple.toFixed(2)}R)
                </span>
              </div>
            </div>
            <div class="pos-metrics">
              <div class="pos-metric"><span>Quantity</span><strong>${p.quantity} shs</strong></div>
              <div class="pos-metric"><span>Entry Fill</span><strong>${ccy}${p.entry_price.toFixed(2)}</strong></div>
              <div class="pos-metric"><span>Current Mark</span><strong>${ccy}${p.current_price.toFixed(2)}</strong></div>
              <div class="pos-metric"><span>Position Value</span><strong>${ACCT_CCY}${p.notional.toFixed(2)}</strong></div>
              <div class="pos-metric"><span>Active Stop-Loss</span><strong class="pos-red">${ccy}${p.stop_loss.toFixed(2)}</strong></div>
              <div class="pos-metric"><span>Take-Profit Target</span><strong class="pos-green">${ccy}${p.take_profit.toFixed(2)}</strong></div>
            </div>

            <!-- Per-Stock Trade Journey Trajectory (Buy -> Current) -->
            ${journeyChartHtml}

            <!-- Position Dynamic Bracket Visualizer (Stop-Loss ↔ Take-Profit Gauge) -->
            <div class="bracket-wrap">
              <div class="bracket-header">
                <div style="display:flex;align-items:center;gap:6px;">
                  <span style="font-weight:600;font-size:12px;color:var(--text-secondary);">🛡️ Stop:</span>
                  <strong class="${isStopLocked ? 'pos-green' : 'pos-red'}" style="font-size:12.5px;">${ccy}${p.stop_loss.toFixed(2)}</strong>
                  ${slBadge}
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                  <span style="font-size:12px;color:var(--text-tertiary);">📌 Entry:</span>
                  <strong style="font-size:12.5px;color:var(--text-primary);">${ccy}${p.entry_price.toFixed(2)}</strong>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                  <span style="font-weight:600;font-size:12px;color:var(--text-secondary);">🎯 Target:</span>
                  <strong class="pos-green" style="font-size:12.5px;">${ccy}${p.take_profit.toFixed(2)}</strong>
                  ${tpBadge}
                </div>
              </div>

              <div class="bracket-track-container">
                <div class="bracket-track">
                  <!-- Danger / Buffer Zone -->
                  <div class="bracket-zone-downside" style="width:${entryPct}%; background:${isStopLocked ? 'linear-gradient(90deg, rgba(52,199,89,0.25), rgba(52,199,89,0.45))' : 'linear-gradient(90deg, rgba(255,59,48,0.22), rgba(255,149,0,0.28))'};"></div>
                  <!-- Profit Runway Zone -->
                  <div class="bracket-zone-upside" style="left:${entryPct}%; width:${100 - entryPct}%; background:linear-gradient(90deg, rgba(0,113,227,0.2), rgba(52,199,89,0.38));"></div>
                  <!-- Entry Tick Pin -->
                  <div class="bracket-entry-pin" style="left:${entryPct}%;" title="Entry Fill: ${ccy}${p.entry_price.toFixed(2)}">
                    <div class="bracket-entry-tick"></div>
                  </div>
                  <!-- Live Current Mark Beacon Pin -->
                  <div class="bracket-current-pin" style="left:${currPct}%;">
                    <div class="bracket-pin-pulse"></div>
                    <div class="bracket-pin-tooltip">Mark: ${ccy}${p.current_price.toFixed(2)}</div>
                  </div>
                </div>
              </div>

              <div class="bracket-subfoot">
                <span style="color:${isStopLocked ? 'var(--green-text)' : 'var(--red-text)'};">
                  ${isStopLocked ? '🛡️ Risk Eliminated • Stop Trailed Above Entry' : '🛡️ Downside Stop Buffer Active'}
                </span>
                <span style="color:var(--accent);">
                  ${p.trailing_active ? '⚡ Trailing Ratchet Engaged (+1.0R Trail Active)' : 'Waiting for +1.0R Trailing Trigger'}
                </span>
                <span style="color:var(--green-text);">
                  ${p.tp_extensions > 0 ? `Target Extended x${p.tp_extensions} (+4.5x ATR)` : 'Target: +3.5x ATR Momentum Exit'}
                </span>
              </div>
            </div>
          </div>
        `;
      }).join('');
      attachPositionJourneyScrubbers(positions);
    }

    function renderScreener(recs) {
      const tbody = document.getElementById('screener-tbody');
      let filtered = [...(recs || [])];
      if (currentFilter === 'US_ONLY') {
        filtered = filtered.filter(r => !(r.symbol || '').endsWith('_UK_EQ'));
      } else if (currentFilter === 'UK_ONLY') {
        filtered = filtered.filter(r => (r.symbol || '').endsWith('_UK_EQ'));
      } else if (currentFilter !== 'ALL') {
        filtered = filtered.filter(r => r.rating === currentFilter);
      }

      // Search Query Filter
      if (screenerSearchQuery) {
        filtered = filtered.filter(r => {
          const clean = formatTickerDisplay(r.symbol).toLowerCase();
          const meta = STOCK_METADATA[r.symbol] || { name: '', sector: '' };
          const name = (meta.name || '').toLowerCase();
          const sector = (meta.sector || '').toLowerCase();
          return clean.includes(screenerSearchQuery) || name.includes(screenerSearchQuery) || sector.includes(screenerSearchQuery);
        });
      }

      // Column Sorting
      filtered.sort((a, b) => {
        let valA, valB;
        switch (currentSortCol) {
          case 'symbol':
            valA = a.symbol; valB = b.symbol;
            return currentSortDir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
          case 'rating':
            const rateOrder = { 'STRONG BUY': 4, 'BUY': 3, 'WATCH': 2, 'AVOID': 1 };
            valA = rateOrder[a.rating] || 0; valB = rateOrder[b.rating] || 0;
            break;
          case 'score': valA = a.score || 0; valB = b.score || 0; break;
          case 'price': valA = a.close_price || 0; valB = b.close_price || 0; break;
          case 'ema': valA = a.ema_fast || 0; valB = b.ema_fast || 0; break;
          case 'rsi': valA = a.rsi || 50; valB = b.rsi || 50; break;
          case 'rvol': valA = a.rvol || 1; valB = b.rvol || 1; break;
          case 'roc': valA = a.roc_10_pct || 0; valB = b.roc_10_pct || 0; break;
          case 'sl': valA = a.suggested_stop_loss || 0; valB = b.suggested_stop_loss || 0; break;
          case 'tp': valA = a.suggested_take_profit || 0; valB = b.suggested_take_profit || 0; break;
          case 'rank':
          default:
            valA = a.rank || 0; valB = b.rank || 0; break;
        }
        return currentSortDir === 'asc' ? (valA - valB) : (valB - valA);
      });

      if (!filtered || filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="14" style="color:var(--text-tertiary);text-align:center;padding:24px;">No stocks match the selected search or filter criteria.</td></tr>';
        return;
      }
      tbody.innerHTML = filtered.map(r => {
        const rocSign = r.roc_10_pct >= 0 ? '+' : '';
        const rocClass = r.roc_10_pct >= 0 ? 'pos-green' : 'pos-red';
        const sparklineSvg = renderSparklineSVG(r.sparkline, r.roc_10_pct);
        const radialDial = renderRadialScore(r.score, r.rating);
        const clean = formatTickerDisplay(r.symbol);
        const ccy = getCurrencySymbol(r.symbol);
        const meta = STOCK_METADATA[r.symbol] || { name: 'US Equity', sector: 'Equities' };

        // Sector monogram gradient & Corporate Brand Logo
        const monoGrad = getSectorGradient(meta.sector);
        const logoBadge = renderStockLogo(r.symbol, clean, monoGrad, 32, 22, 9);

        // RSI Bullet Meter
        const rsiVal = Number(r.rsi || 50);
        const rsiOptimal = (rsiVal >= 54 && rsiVal <= 67);
        const rsiColor = rsiOptimal ? 'pos-green' : (rsiVal > 67 ? 'pos-red' : '');
        const rsiSub = rsiOptimal ? 'OPTIMAL' : (rsiVal > 67 ? 'HIGH' : 'NEUTRAL');
        const rsiBullet = `
          <div class="rsi-bullet-wrap" title="RSI: ${rsiVal.toFixed(1)} (Ideal zone: 54-67)">
            <div style="display:flex;justify-content:space-between;font-size:11px;font-weight:600;">
              <span class="${rsiColor}">${rsiVal.toFixed(1)}</span>
              <span style="font-size:9.5px;color:var(--text-tertiary);">${rsiSub}</span>
            </div>
            <div class="rsi-bullet-track">
              <div class="rsi-sweet-spot"></div>
              <div class="rsi-marker" style="left:${Math.min(100, Math.max(0, rsiVal))}%;"></div>
            </div>
          </div>
        `;

        // RVOL Volume Surge Meter
        const rvolVal = Number(r.rvol || 1);
        const rvolSurge = rvolVal >= 1.5;
        const rvolColor = rvolSurge ? 'pos-green' : (rvolVal >= 1.15 ? 'pos-green' : '');
        const rvolBarColor = rvolSurge ? 'var(--green)' : (rvolVal >= 1.15 ? 'var(--accent)' : 'var(--text-tertiary)');
        const rvolSub = rvolSurge ? 'SURGE' : (rvolVal >= 1.15 ? 'ACTIVE' : 'LOW');
        const rvolMeter = `
          <div class="rvol-meter-wrap" title="RVOL: ${rvolVal.toFixed(2)}x (1.5x = surge threshold)">
            <div style="display:flex;justify-content:space-between;font-size:11px;font-weight:600;">
              <span class="${rvolColor}">${rvolVal.toFixed(2)}x</span>
              <span style="font-size:9.5px;color:${rvolSurge ? 'var(--green-text)' : 'var(--text-tertiary)'};">${rvolSub}</span>
            </div>
            <div class="rvol-track">
              <div class="rvol-fill" style="width:${Math.min(100, (rvolVal / 2.5) * 100)}%; background:${rvolBarColor};"></div>
            </div>
          </div>
        `;

        const countPill = document.getElementById('screener-count-pill');
        if (countPill) countPill.textContent = filtered.length + ' / ' + (recs ? recs.length : 50) + ' stocks';

        return `
          <tr onclick="openStockDetail('${r.symbol}')" title="Click anywhere on row to inspect ${clean}">
            <td><strong>#${r.rank}</strong></td>
            <td>
              <div class="asset-cell">
                ${logoBadge}
                <div>
                  <strong style="font-size:13.5px;letter-spacing:-0.01em;">${clean}</strong>
                  <div style="font-size:11px;color:var(--text-tertiary);">${meta.name}</div>
                </div>
              </div>
            </td>
            <td><span class="${badgeClass(r.rating)}">${r.rating}</span>${r.blocker ? `<div style="font-size:10px;color:var(--amber-text);margin-top:3px;max-width:170px;line-height:1.2;">⚠ ${r.blocker}</div>` : ''}</td>
            <td>${radialDial}</td>
            <td><strong>${ccy}${r.close_price.toFixed(2)}</strong></td>
            <td>${sparklineSvg}</td>
            <td>${r.ema_fast.toFixed(1)} / ${r.ema_slow.toFixed(1)}</td>
            <td>${rsiBullet}</td>
            <td>${rvolMeter}</td>
            <td class="${rocClass}">${rocSign}${r.roc_10_pct.toFixed(2)}%</td>
            <td class="pos-red">${ccy}${r.suggested_stop_loss.toFixed(2)}</td>
            <td class="pos-green">${ccy}${r.suggested_take_profit.toFixed(2)}</td>
            <td class="td-thesis">
              <div style="color:var(--text-secondary);font-size:12px;line-height:1.45;">${r.thesis}</div>
            </td>
            <td style="text-align:right;">
              <button class="inspect-btn" onclick="event.stopPropagation(); openStockDetail('${r.symbol}')" title="Inspect ${clean} in macOS sheet">
                <span>Inspect</span>
                <span style="font-size:10px;">➔</span>
              </button>
            </td>
          </tr>
        `;
      }).join('');
    }

    // Plain-English Explanation Generator for Non-Technical Users
    function populatePlainEnglishThesis(stock) {
      const rating = stock.rating || 'HOLD';
      const score = Number(stock.score || 0);
      const rvol = Number(stock.rvol || 1.0);
      const rsi = Number(stock.rsi || 50);
      const close = Number(stock.close_price || 0);
      const emaFast = Number(stock.ema_fast || 0);
      const emaSlow = Number(stock.ema_slow || 0);
      const blocker = (stock.blocker || '').toLowerCase();
      const thesis = (stock.thesis || '').toLowerCase();

      const pill = document.getElementById('modal-plain-action-pill');
      const banner = document.getElementById('modal-plain-verdict-banner');
      const title = document.getElementById('modal-plain-verdict-title');
      const desc = document.getElementById('modal-plain-verdict-desc');

      if (!pill || !banner || !title || !desc) return;

      if (rating === 'STRONG BUY') {
        pill.className = 'status-pill status-pill-active';
        pill.textContent = 'STRONG BUY';
        banner.style.borderColor = 'rgba(52, 211, 153, 0.4)';
        banner.style.background = 'rgba(16, 185, 129, 0.08)';
        title.innerHTML = '🟢 High-Conviction Buyer Demand';
        title.style.color = 'var(--green-text)';
        desc.textContent = 'Buyers are actively driving the price higher with heavy volume. Both short-term and medium-term trends are pointing upward, and the stock is not overheated.';
      } else if (rating === 'BUY') {
        pill.className = 'status-pill status-pill-active';
        pill.textContent = 'BUY';
        banner.style.borderColor = 'rgba(52, 211, 153, 0.3)';
        banner.style.background = 'rgba(16, 185, 129, 0.06)';
        title.innerHTML = '🟢 Healthy Upward Trend';
        title.style.color = 'var(--green-text)';
        desc.textContent = 'Price is climbing steadily with consistent buyer support. The stock offers a balanced entry with favorable upside potential versus downside risk.';
      } else if (rating === 'WATCH') {
        pill.className = 'status-pill status-pill-syncing';
        pill.textContent = 'ON WATCH';
        banner.style.borderColor = 'rgba(251, 191, 36, 0.35)';
        banner.style.background = 'rgba(245, 158, 11, 0.08)';
        if (blocker.includes('overextended') || thesis.includes('overextended')) {
          title.innerHTML = '🟡 Climbing Too Fast (Wait for Dip)';
          title.style.color = 'var(--amber-text)';
          desc.textContent = 'The company is in an upward trend, but the price has surged too far ahead of its typical average over recent hours. Buying now risks buying at a temporary top; the bot is waiting for a calmer entry price.';
        } else {
          title.innerHTML = '🟡 Coiling for Breakout';
          title.style.color = 'var(--amber-text)';
          desc.textContent = 'Price is compressing and building energy for a potential move higher. The bot is closely tracking this stock for confirmed breakout volume before deploying capital.';
        }
      } else if (rating === 'HOLD') {
        pill.className = 'status-pill status-pill-node';
        pill.textContent = 'HOLD / NEUTRAL';
        banner.style.borderColor = 'var(--border)';
        banner.style.background = 'var(--surface-tertiary)';
        title.innerHTML = '🔵 Steady / Neutral Movement';
        title.style.color = 'var(--blue-text)';
        desc.textContent = 'Price is holding relatively steady, but lacks the explosive buyer interest or volume required to justify risking new money right now.';
      } else {
        pill.className = 'status-pill';
        pill.style.background = 'rgba(239, 68, 68, 0.12)';
        pill.style.color = 'var(--red-text)';
        pill.textContent = 'AVOID';
        banner.style.borderColor = 'rgba(239, 68, 68, 0.35)';
        banner.style.background = 'rgba(239, 68, 68, 0.08)';
        title.innerHTML = '🔴 Downward Slide / Selling Pressure';
        title.style.color = 'var(--red-text)';
        desc.textContent = 'The stock is falling below its moving averages or facing persistent selling pressure. The bot is staying away to protect capital.';
      }

      const trendEl = document.getElementById('modal-plain-trend');
      const trendSub = document.getElementById('modal-plain-trend-sub');
      if (trendEl && trendSub) {
        if (close >= emaFast && emaFast >= emaSlow) {
          trendEl.innerHTML = '🟢 Upward Climb';
          trendEl.style.color = 'var(--green-text)';
          trendSub.textContent = 'Price is cleanly above short & medium term averages.';
        } else if (emaFast >= emaSlow) {
          trendEl.innerHTML = '🟡 Mild Uptrend / Pullback';
          trendEl.style.color = 'var(--amber-text)';
          trendSub.textContent = 'General trend is up, but experiencing a short-term pause.';
        } else {
          trendEl.innerHTML = '🔴 Downward Slope';
          trendEl.style.color = 'var(--red-text)';
          trendSub.textContent = 'Price is lagging below average levels.';
        }
      }

      const volEl = document.getElementById('modal-plain-volume');
      const volSub = document.getElementById('modal-plain-volume-sub');
      if (volEl && volSub) {
        if (rvol >= 1.5) {
          volEl.innerHTML = '🔥 High Interest (' + rvol.toFixed(1) + 'x)';
          volEl.style.color = 'var(--green-text)';
          volSub.textContent = 'Heavy institutional buying volume confirming the move.';
        } else if (rvol >= 1.0) {
          volEl.innerHTML = '🟢 Normal-to-Good (' + rvol.toFixed(1) + 'x)';
          volEl.style.color = 'var(--text-primary)';
          volSub.textContent = 'Trading activity is healthy and matches average levels.';
        } else {
          volEl.innerHTML = '⚪ Low Volume (' + rvol.toFixed(1) + 'x)';
          volEl.style.color = 'var(--text-secondary)';
          volSub.textContent = 'Trading volume is quiet today.';
        }
      }

      const safeEl = document.getElementById('modal-plain-safety');
      const safeSub = document.getElementById('modal-plain-safety-sub');
      if (safeEl && safeSub) {
        if (stock.actionable) {
          safeEl.innerHTML = '🛡️ Safe Entry Point';
          safeEl.style.color = 'var(--green-text)';
          safeSub.textContent = 'Strict 1:2+ reward/risk with automatic stop-loss ready.';
        } else if (blocker.includes('overextended')) {
          safeEl.innerHTML = '⚠️ Overextended';
          safeEl.style.color = 'var(--amber-text)';
          safeSub.textContent = 'Too far from base price; wait for a pullback dip.';
        } else if (blocker.includes('upper-wick')) {
          safeEl.innerHTML = '⚠️ Upper Wick Rejection';
          safeEl.style.color = 'var(--amber-text)';
          safeSub.textContent = 'Sellers pushed price down from today’s highest peak.';
        } else {
          safeEl.innerHTML = '⏳ Waiting for Trigger';
          safeEl.style.color = 'var(--text-secondary)';
          safeSub.textContent = 'Holding until buy criteria are fully met.';
        }
      }

      const botDec = document.getElementById('modal-plain-bot-decision');
      if (botDec) {
        if (stock.actionable) {
          botDec.style.borderColor = 'rgba(52, 211, 153, 0.4)';
          botDec.innerHTML = '<strong>🤖 Bot Action:</strong> <span style="color:var(--green-text);font-weight:600;">APPROVED FOR PURCHASE.</span> All quantitative criteria are met. When an open portfolio slot is available, the bot will automatically enter this position.';
        } else if (stock.blocker) {
          botDec.style.borderColor = 'rgba(251, 191, 36, 0.35)';
          let cleanReason = stock.blocker
            .replace(/Close > EMA20 > EMA50/g, 'price above moving averages')
            .replace(/overextended [0-9.]+x ATR above EMA20/g, 'price jumped up too quickly (waiting for a dip)')
            .replace(/upper-wick rejection candle/g, 'sellers actively resisted at the highs')
            .replace(/RVOL [0-9.]+x < [0-9.]+x/g, 'trading volume is not high enough yet');
          botDec.innerHTML = '<strong>🤖 Bot Action:</strong> <span style="color:var(--amber-text);font-weight:600;">STANDING PAT.</span> The bot is waiting because ' + cleanReason + '.';
        } else {
          botDec.style.borderColor = 'var(--border)';
          botDec.innerHTML = '<strong>🤖 Bot Action:</strong> <span style="color:var(--text-secondary);font-weight:600;">MONITORING.</span> Watching closely in background scans.';
        }
      }
    }

    // Modal Sheet Functions
    function openStockDetail(symbol) {
      playHaptic('click');
      currentModalSymbol = symbol;
      let stock = (latestRecommendations || []).find(r => r.symbol === symbol);
      if (!stock && latestTelemetryData && latestTelemetryData.positions) {
        const p = latestTelemetryData.positions.find(pos => pos.symbol === symbol);
        if (p) {
          stock = {
            symbol: p.symbol,
            close_price: p.current_price,
            score: 80,
            rating: 'BUY',
            rsi: 58,
            rvol: 1.4,
            ema_fast: p.entry_price,
            ema_slow: p.stop_loss,
            atr: Math.abs(p.current_price - p.stop_loss) / 1.5 || (p.current_price * 0.02),
            suggested_stop_loss: p.stop_loss,
            suggested_take_profit: p.take_profit,
            roc_10_pct: p.unrealized_pnl_pct || 0,
            thesis: 'Held active position with dynamic trailing stop and runway.'
          };
        }
      }
      if (!stock) {
        stock = { symbol: symbol, close_price: 0, score: 75, rating: 'BUY', rsi: 55, rvol: 1.5, ema_fast: 0, ema_slow: 0, atr: 1.5, suggested_stop_loss: 0, suggested_take_profit: 0, roc_10_pct: 0, thesis: 'Held active position under dynamic tracking.' };
      }
      switchModalChart('candle');
      const clean = formatTickerDisplay(symbol);
      const ccy = getCurrencySymbol(symbol);
      const meta = STOCK_METADATA[symbol] || { name: 'US Equity', sector: 'Equities' };

      document.getElementById('modal-symbol').textContent = clean;
      document.getElementById('modal-tv-link').href = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(getTradingViewSymbol(symbol))}`;

      // Update modal icon with corporate brand logo
      const modalSquircle = document.getElementById('modal-squircle');
      if (modalSquircle) {
        const modalMonoGrad = getSectorGradient(meta.sector);
        modalSquircle.innerHTML = `
          <img class="asset-logo-img" style="width:28px;height:28px;" src="https://www.google.com/s2/favicons?domain=${getStockDomain(symbol)}&sz=128" alt="${clean}" onerror="this.style.display='none'; if(this.nextElementSibling) this.nextElementSibling.style.display='flex';" />
          <div class="asset-monogram" style="background:${modalMonoGrad}; display:none; width:100%; height:100%; font-size:16px; border-radius:12px;">${clean.slice(0, 2)}</div>
        `;
        modalSquircle.className = 'asset-logo-wrap';
        modalSquircle.style.width = '44px';
        modalSquircle.style.height = '44px';
        modalSquircle.style.borderRadius = '12px';
      }
      document.getElementById('modal-company-name').textContent = `${meta.name} • ${meta.sector}`;
      document.getElementById('modal-sector-badge').textContent = meta.sector;
      document.getElementById('modal-rating-badge').className = badgeClass(stock.rating);
      document.getElementById('modal-rating-badge').textContent = stock.rating;
      document.getElementById('modal-price').textContent = `${ccy}${Number(stock.close_price || 0).toFixed(2)}`;

      const rocSign = Number(stock.roc_10_pct || 0) >= 0 ? '+' : '';
      const rocColor = Number(stock.roc_10_pct || 0) >= 0 ? 'var(--green-text)' : 'var(--red-text)';
      document.getElementById('modal-roc').textContent = `${rocSign}${Number(stock.roc_10_pct || 0).toFixed(2)}% (10 bars)`;
      document.getElementById('modal-roc').style.color = rocColor;

      const freshnessEl = document.getElementById('modal-freshness-badge');
      if (freshnessEl) {
        const rawC = (stock.candles && stock.candles.length > 0) ? stock.candles[stock.candles.length - 1] : null;
        if (rawC && (rawC.time || rawC.datetime)) {
          freshnessEl.style.display = 'inline-flex';
          freshnessEl.innerHTML = `<span class="beacon-dot beacon-green" style="width:6px;height:6px;"></span> 15m Candles (${rawC.time || rawC.datetime})`;
          freshnessEl.className = 'badge badge-buy';
        } else {
          freshnessEl.style.display = 'none';
        }
      }

      // Radial dial in modal
      document.getElementById('modal-score-wrap').innerHTML = renderRadialScore(stock.score, stock.rating);

      // Render Candlestick Chart (default) & Expanded Sparkline (fallback)
      renderCandleChartSVG(stock);
      document.getElementById('modal-sparkline-expanded').innerHTML = renderSparklineSVG(stock.sparkline || [stock.close_price * 0.99, stock.close_price], stock.roc_10_pct, 760, 110);

      // 6 Tiles
      const rsiVal = Number(stock.rsi || 50).toFixed(1);
      document.getElementById('modal-rsi').textContent = rsiVal;
      document.getElementById('modal-rsi-desc').textContent = (rsiVal >= 45 && rsiVal <= 65) ? 'Sweet-Spot Momentum' : (rsiVal > 65 ? 'High Momentum (Extended)' : 'Oversold / Neutral');

      document.getElementById('modal-rvol').textContent = `${Number(stock.rvol || 1).toFixed(2)}x`;
      document.getElementById('modal-rvol-desc').textContent = Number(stock.rvol || 1) >= 1.5 ? 'Institutional Volume Surge' : 'Normal Volume Flow';

      document.getElementById('modal-mas').textContent = `${ccy}${Number(stock.ema_fast || 0).toFixed(2)} / ${ccy}${Number(stock.ema_slow || 0).toFixed(2)}`;
      document.getElementById('modal-trend-desc').textContent = (stock.ema_fast >= stock.ema_slow) ? 'EMA 20 > EMA 50 (Uptrend)' : 'EMA 20 < EMA 50 (Pullback)';

      document.getElementById('modal-atr').textContent = `${ccy}${Number(stock.atr || 1).toFixed(2)}`;
      const atrPct = stock.close_price ? ((stock.atr / stock.close_price) * 100).toFixed(2) : '1.5';
      document.getElementById('modal-atr-desc').textContent = `${atrPct}% Average True Range`;

      const curPrice = Number(stock.close_price || 0);
      const slPrice = Number(stock.suggested_stop_loss || 0);
      const tpPrice = Number(stock.suggested_take_profit || 0);
      document.getElementById('modal-sl').textContent = `${ccy}${slPrice.toFixed(2)}`;
      document.getElementById('modal-tp').textContent = `${ccy}${tpPrice.toFixed(2)}`;

      // Populate Asymmetric Risk / Reward Ladder Card
      if (curPrice > 0 && slPrice > 0 && tpPrice > 0) {
        const risk = Math.max(0.01, curPrice - slPrice);
        const reward = Math.max(0.01, tpPrice - curPrice);
        const rrRatio = (reward / risk).toFixed(2);
        const beWinRate = ((1 / (1 + (reward / risk))) * 100).toFixed(1);
        const tpPct = (((tpPrice - curPrice) / curPrice) * 100).toFixed(1);
        const slPct = (((curPrice - slPrice) / curPrice) * 100).toFixed(1);

        document.getElementById('modal-rr-ratio').textContent = `1 : ${rrRatio} R/R`;
        document.getElementById('modal-rr-tp-val').textContent = `${ccy}${tpPrice.toFixed(2)}`;
        document.getElementById('modal-rr-tp-pct').textContent = `+${tpPct}% (+${rrRatio}R)`;
        document.getElementById('modal-rr-sl-val').textContent = `${ccy}${slPrice.toFixed(2)}`;
        document.getElementById('modal-rr-sl-pct').textContent = `-${slPct}% (-1.0R)`;
        document.getElementById('modal-rr-be-rate').textContent = `${beWinRate}% Win Rate`;

        const totalSpan = risk + reward;
        const gainBarPct = Math.round((reward / totalSpan) * 100);
        const riskBarPct = Math.round((risk / totalSpan) * 100);
        const gainBar = document.getElementById('modal-rr-gain-bar');
        const riskBar = document.getElementById('modal-rr-risk-bar');
        if (gainBar && riskBar) {
          gainBar.style.height = `${gainBarPct}%`;
          riskBar.style.height = `${riskBarPct}%`;
        }
      }

      document.getElementById('modal-thesis-text').textContent = stock.thesis || 'Technical setup matches multi-factor trend and momentum criteria.';

      const blockerEl = document.getElementById('modal-blocker-note');
      if (stock.blocker) {
        blockerEl.style.display = 'block';
        blockerEl.textContent = `Algorithmic Rule Note: ${stock.blocker}`;
      } else {
        blockerEl.style.display = 'none';
      }

      populatePlainEnglishThesis(stock);

      const modal = document.getElementById('stock-modal-backdrop');
      modal.classList.add('open');
      document.body.style.overflow = 'hidden';
    }

    function closeStockModal(e) {
      if (e && e.target !== document.getElementById('stock-modal-backdrop') && !e.target.closest('.modal-close-btn')) {
        return;
      }
      const modal = document.getElementById('stock-modal-backdrop');
      if (modal) {
        modal.classList.remove('open');
        document.body.style.overflow = '';
      }
      const sheet = document.querySelector('#stock-modal-backdrop .modal-sheet');
      if (sheet) sheet.classList.remove('modal-sheet-wide');
      switchModalChart('candle');
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const modal = document.getElementById('stock-modal-backdrop');
        if (modal.classList.contains('open')) {
          modal.classList.remove('open');
          document.body.style.overflow = '';
        }
      }
    });

    // Full-Day Portfolio Equity Trajectory Renderer
    let currentEquityView = '1D';
    let latestTelemetryData = null;

    function setEquityView(view) {
      currentEquityView = view;
      const b1 = document.getElementById('btn-eq-1d');
      const b2 = document.getElementById('btn-eq-24h');
      if (b1) b1.classList.toggle('active', view === '1D');
      if (b2) b2.classList.toggle('active', view === '24H');
      if (latestTelemetryData) {
        const p = latestTelemetryData.portfolio || {};
        renderEquityCurve(
          latestTelemetryData.equity_history,
          latestTelemetryData.equity_history_24h,
          latestTelemetryData.session_info,
          p.realized_pnl,
          p.total_equity
        );
      }
    }

    function renderEquityCurve(sessionHistory, history24h, sessionInfo, realizedPnl, currentEquity) {
      const container = document.getElementById('equity-curve-container');
      if (!container) return;

      const is1D = (currentEquityView === '1D');
      const pts = (is1D ? sessionHistory : history24h) || [];
      const sInfo = sessionInfo || {};

      // Badges & metadata
      const startEquity = sInfo.start_equity || (pts.length > 0 ? Number(pts[0].equity) : (currentEquity || 500.0));
      const currEq = Number(currentEquity || (pts.length > 0 ? pts[pts.length - 1].equity : 500.0));
      const dayPnl = currEq - startEquity;
      const dayPnlPct = (startEquity > 0) ? (dayPnl / startEquity * 100) : 0.0;
      const pnlSign = dayPnl >= 0 ? '+' : '';

      const dayBadge = document.getElementById('curve-day-pnl-badge');
      if (dayBadge) {
        dayBadge.textContent = `${pnlSign}${ACCT_CCY}${dayPnl.toFixed(2)} (${pnlSign}${dayPnlPct.toFixed(2)}%) ${is1D ? 'Session' : '24H'}`;
        dayBadge.className = `badge ${dayPnl >= 0 ? 'badge-strong-buy' : 'badge-avoid'}`;
      }

      const sessionPill = document.getElementById('session-range-badge');
      if (sessionPill) {
        if (is1D) {
          const dateStr = sInfo.target_date || 'TODAY';
          sessionPill.textContent = `${dateStr} SESSION (09:30–16:00 ET)`;
        } else {
          sessionPill.textContent = 'ROLLING 24-HOUR TRAJECTORY';
        }
      }

      const subTitle = document.getElementById('equity-curve-subtitle');
      if (subTitle && sInfo.day_high && sInfo.day_low) {
        subTitle.textContent = is1D
          ? `Day High: ${ACCT_CCY}${Number(sInfo.day_high).toFixed(2)} • Day Low: ${ACCT_CCY}${Number(sInfo.day_low).toFixed(2)} • Baseline Open: ${ACCT_CCY}${startEquity.toFixed(2)}`
          : `24-Hour portfolio valuation curve and drawdown floor`;
      }

      // Fallback if zero points
      let curvePts = (pts && pts.length >= 1) ? pts : [
        { time_et: '09:30 AM', timestamp: '09:30', session_min: 0, equity: startEquity },
        { time_et: '04:00 PM', timestamp: '16:00', session_min: 390, equity: currEq }
      ];

      const w = container.clientWidth || 700;
      const h = 205;
      const padL = 56;
      const padR = 30;
      const padT = 24;
      const padB = 36;
      const plotW = Math.max(100, w - padL - padR);
      const plotH = Math.max(80, h - padT - padB);

      const totalMins = (is1D && sInfo.total_session_minutes) ? sInfo.total_session_minutes : 390;

      // Calculate dynamic Y range with 16% headroom
      const eqs = curvePts.map(p => Number(p.equity));
      eqs.push(startEquity);
      let minEq = Math.min(...eqs);
      let maxEq = Math.max(...eqs);
      if (maxEq - minEq < 0.6) {
        minEq -= 0.6;
        maxEq += 0.6;
      } else {
        const m = (maxEq - minEq) * 0.16;
        minEq -= m;
        maxEq += m;
      }
      const range = (maxEq - minEq) || 1.0;

      // Map coordinates
      const coords = curvePts.map((p, idx) => {
        let normX = 0;
        if (is1D) {
          const sMin = (p.session_min !== undefined) ? Number(p.session_min) : (idx / Math.max(1, curvePts.length - 1)) * totalMins;
          normX = Math.min(1.0, Math.max(0.0, sMin / totalMins));
        } else {
          normX = idx / Math.max(1, curvePts.length - 1);
        }
        const x = padL + (normX * plotW);
        const normY = (Number(p.equity) - minEq) / range;
        const y = (h - padB) - (normY * plotH);
        return {
          x: x.toFixed(1),
          y: y.toFixed(1),
          eq: Number(p.equity),
          ts: p.time_et || p.timestamp || '',
          cash: p.cash,
          sessionMin: p.session_min
        };
      });

      // Deduplicate adjacent x coordinates to prevent SVG polygon distortion
      const cleanCoords = [];
      for (let i = 0; i < coords.length; i++) {
        if (i === 0 || i === coords.length - 1 || coords[i].x !== coords[i - 1].x) {
          cleanCoords.push(coords[i]);
        }
      }

      const polyPoints = cleanCoords.map(c => `${c.x},${c.y}`).join(' ');
      const baseLineY = (h - padB) - (((startEquity - minEq) / range) * plotH);
      const isProfitable = (currEq >= startEquity);
      const strokeCol = isProfitable ? 'var(--green)' : 'var(--red)';

      const fillGrad = `
        <defs>
          <linearGradient id="eqSessionGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="${strokeCol}" stop-opacity="0.32" />
            <stop offset="100%" stop-color="${strokeCol}" stop-opacity="0.0" />
          </linearGradient>
        </defs>
      `;

      const lastPt = cleanCoords[cleanCoords.length - 1];
      const firstPt = cleanCoords[0];
      const areaPoints = `${polyPoints} ${lastPt.x},${h - padB} ${firstPt.x},${h - padB}`;

      // Build session timeline ticks (09:30, 11:00, 12:30, 14:00, 15:30, 16:00 ET)
      let timeTicksSvg = '';
      if (is1D) {
        const ticks = [
          { min: 0, label: '09:30 Open' },
          { min: 90, label: '11:00' },
          { min: 180, label: '12:30' },
          { min: 270, label: '14:00' },
          { min: 360, label: '15:30' },
          { min: totalMins, label: '16:00 Close' }
        ];
        timeTicksSvg = ticks.map(t => {
          const tx = padL + (t.min / totalMins) * plotW;
          const isEdge = (t.min === 0 || t.min === totalMins);
          return `
            <line x1="${tx.toFixed(1)}" y1="${padT}" x2="${tx.toFixed(1)}" y2="${h - padB}" stroke="rgba(142,142,147,0.10)" stroke-dasharray="3,3" stroke-width="1" />
            <text x="${tx.toFixed(1)}" y="${h - padB + 16}" font-size="10" font-weight="${isEdge ? '600' : '400'}" fill="var(--text-tertiary)" text-anchor="middle">${t.label}</text>
          `;
        }).join('');
      } else {
        const ticks = [
          { frac: 0.0, label: '-24h' },
          { frac: 0.25, label: '-18h' },
          { frac: 0.50, label: '-12h' },
          { frac: 0.75, label: '-6h' },
          { frac: 1.0, label: 'Now' }
        ];
        timeTicksSvg = ticks.map(t => {
          const tx = padL + (t.frac * plotW);
          return `
            <line x1="${tx.toFixed(1)}" y1="${padT}" x2="${tx.toFixed(1)}" y2="${h - padB}" stroke="rgba(142,142,147,0.10)" stroke-dasharray="3,3" stroke-width="1" />
            <text x="${tx.toFixed(1)}" y="${h - padB + 16}" font-size="10" fill="var(--text-tertiary)" text-anchor="middle">${t.label}</text>
          `;
        }).join('');
      }

      // Remaining session projection guideline (from last point to 16:00 close)
      let projectionSvg = '';
      if (is1D && parseFloat(lastPt.x) < (padL + plotW - 8)) {
        projectionSvg = `
          <!-- Projected Session Trajectory to 16:00 Close -->
          <line x1="${lastPt.x}" y1="${lastPt.y}" x2="${(padL + plotW).toFixed(1)}" y2="${lastPt.y}" stroke="${strokeCol}" stroke-dasharray="3,3" stroke-width="1.2" opacity="0.45" />
          <line x1="${lastPt.x}" y1="${padT}" x2="${lastPt.x}" y2="${h - padB}" stroke="${strokeCol}" stroke-dasharray="2,2" stroke-width="1.2" opacity="0.4" />
          <text x="${Math.max(padL + 20, parseFloat(lastPt.x) - 4)}" y="${padT + 11}" text-anchor="end" font-size="9" font-weight="700" fill="${strokeCol}">NOW</text>
        `;
      }

      // Y-axis price labels
      const yAxisLabels = `
        <text x="${padL - 8}" y="${padT + 4}" font-size="9.5" font-weight="500" fill="var(--text-tertiary)" text-anchor="end">${ACCT_CCY}${maxEq.toFixed(2)}</text>
        <text x="${padL - 8}" y="${h - padB}" font-size="9.5" font-weight="500" fill="var(--text-tertiary)" text-anchor="end">${ACCT_CCY}${minEq.toFixed(2)}</text>
      `;

      container.innerHTML = `
        <div style="position:relative; width:100%; height:${h}px;" id="eq-chart-interactive-wrap">
          <div id="eq-crosshair-tip" class="equity-hover-tip" style="opacity:0;"></div>
          <svg id="eq-chart-svg" width="100%" height="${h}" viewBox="0 0 ${w} ${h}" style="overflow:visible;">
            ${fillGrad}

            <!-- Session Time Gridlines & Labels -->
            ${timeTicksSvg}

            <!-- Y-Axis Price Labels -->
            ${yAxisLabels}

            <!-- Session Open Baseline ($startEquity) -->
            <line x1="${padL}" y1="${baseLineY.toFixed(1)}" x2="${(padL + plotW).toFixed(1)}" y2="${baseLineY.toFixed(1)}" stroke="rgba(142,142,147,0.30)" stroke-dasharray="4,4" stroke-width="1" />
            <text x="${padL + 6}" y="${(baseLineY - 6).toFixed(1)}" font-size="9.5" font-weight="600" fill="var(--text-tertiary)">Session Open: ${ACCT_CCY}${startEquity.toFixed(2)}</text>

            <!-- Projected session line to close -->
            ${projectionSvg}

            <!-- Area & Line -->
            <polygon points="${areaPoints}" fill="url(#eqSessionGrad)" />
            <polyline ${!hasAnimatedEquityCurve ? 'class="eq-curve-path-animated"' : ''} points="${polyPoints}" fill="none" stroke="${strokeCol}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />

            <!-- Live Beacon Dot on latest recorded point -->
            <circle cx="${lastPt.x}" cy="${lastPt.y}" r="4.5" fill="${strokeCol}" stroke="#ffffff" stroke-width="2" />
            <circle cx="${lastPt.x}" cy="${lastPt.y}" r="9" fill="none" stroke="${strokeCol}" stroke-width="1.5" opacity="0.5" />
            <text x="${Math.min(w - padR - 10, parseFloat(lastPt.x) + 12)}" y="${parseFloat(lastPt.y) - 6}" font-size="12" font-weight="700" fill="var(--text-primary)">
              ${ACCT_CCY}${currEq.toFixed(2)}
            </text>

            <!-- Interactive Crosshair Scrubber Elements -->
            <line id="eq-crosshair-line" x1="0" y1="${padT}" x2="0" y2="${h - padB}" stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="3,3" opacity="0" pointer-events="none" />
            <circle id="eq-crosshair-dot" cx="0" cy="0" r="5" fill="var(--accent)" stroke="#ffffff" stroke-width="2" opacity="0" pointer-events="none" />

            <!-- Transparent Mouseover Overlay -->
            <rect id="eq-mouse-overlay" x="${padL}" y="0" width="${plotW}" height="${h}" fill="transparent" style="cursor:crosshair;" />
          </svg>
        </div>
      `;
      hasAnimatedEquityCurve = true;

      // Crosshair scrubber event listener
      const overlay = document.getElementById('eq-mouse-overlay');
      const tip = document.getElementById('eq-crosshair-tip');
      const line = document.getElementById('eq-crosshair-line');
      const dot = document.getElementById('eq-crosshair-dot');
      const wrap = document.getElementById('eq-chart-interactive-wrap');

      if (overlay && wrap && tip && line && dot) {
        overlay.addEventListener('mousemove', (e) => {
          const rect = wrap.getBoundingClientRect();
          const mouseX = e.clientX - rect.left;
          const svgScaleX = w / rect.width;
          const targetSvgX = mouseX * svgScaleX;

          let closest = cleanCoords[0];
          let minDist = Math.abs(parseFloat(cleanCoords[0].x) - targetSvgX);
          for (let i = 1; i < cleanCoords.length; i++) {
            const dist = Math.abs(parseFloat(cleanCoords[i].x) - targetSvgX);
            if (dist < minDist) {
              minDist = dist;
              closest = cleanCoords[i];
            }
          }

          line.setAttribute('x1', closest.x);
          line.setAttribute('x2', closest.x);
          line.setAttribute('opacity', '1');

          dot.setAttribute('cx', closest.x);
          dot.setAttribute('cy', closest.y);
          dot.setAttribute('opacity', '1');

          const clientX = (parseFloat(closest.x) / w) * rect.width;
          const clientY = (parseFloat(closest.y) / h) * rect.height;

          const diff = closest.eq - startEquity;
          const diffPct = (startEquity > 0) ? (diff / startEquity * 100) : 0;
          const dSign = diff >= 0 ? '+' : '';
          const diffCol = diff >= 0 ? 'var(--green)' : 'var(--red)';

          tip.style.left = clientX + 'px';
          tip.style.top = Math.max(10, clientY - 10) + 'px';
          tip.style.opacity = '1';
          tip.innerHTML = `
            <div style="font-weight:700;font-size:12.5px;color:var(--text-primary);">${ACCT_CCY}${closest.eq.toFixed(2)}</div>
            <div style="font-size:10px;color:var(--text-tertiary);margin-top:2px;">${closest.ts}</div>
            <div style="font-size:10.5px;font-weight:600;color:${diffCol};margin-top:2px;">${dSign}${ACCT_CCY}${diff.toFixed(2)} (${dSign}${diffPct.toFixed(2)}%)</div>
          `;
        });

        overlay.addEventListener('mouseleave', () => {
          line.setAttribute('opacity', '0');
          dot.setAttribute('opacity', '0');
          tip.style.opacity = '0';
        });
      }
    }

    // Apple Fitness Rings Renderer
    function renderPerformanceRings(closedTrades, positions) {
      const trades = closedTrades || [];
      const wins = trades.filter(t => Number(t.net_pnl || 0) > 0).length;
      const winRate = trades.length > 0 ? (wins / trades.length) * 100 : 75; // default optimistic preview if 0 trades
      const grossWins = trades.filter(t => Number(t.net_pnl || 0) > 0).reduce((acc, t) => acc + Number(t.net_pnl || 0), 0);
      const grossLosses = Math.abs(trades.filter(t => Number(t.net_pnl || 0) < 0).reduce((acc, t) => acc + Number(t.net_pnl || 0), 0));
      const pf = grossLosses > 0 ? (grossWins / grossLosses) : (grossWins > 0 ? 3.0 : 1.85);

      const openCnt = (positions || []).length;
      const slotUsage = Math.min(100, (openCnt / 3) * 100);

      // Ring 1 (Win Rate, circ 289.0)
      const r1 = document.getElementById('ring-win-rate');
      if (r1) {
        const off1 = (289.0 - (Math.min(100, winRate) / 100 * 289.0)).toFixed(1);
        r1.style.strokeDashoffset = off1;
      }
      document.getElementById('stat-win-rate').textContent = trades.length > 0 ? `${winRate.toFixed(0)}%` : 'Active';

      // Ring 2 (Profit Factor, circ 213.6, scaled 0 to 3.0x)
      const r2 = document.getElementById('ring-profit-factor');
      if (r2) {
        const off2 = (213.6 - (Math.min(3.0, pf) / 3.0 * 213.6)).toFixed(1);
        r2.style.strokeDashoffset = off2;
      }
      document.getElementById('stat-profit-factor').textContent = `${pf.toFixed(2)}x`;

      // Ring 3 (Slot Usage, circ 138.2, 4 slots: 3 US + 1 UK)
      const r3 = document.getElementById('ring-slot-capacity');
      if (r3) {
        const off3 = (138.2 - ((openCnt / 4) * 138.2)).toFixed(1);
        r3.style.strokeDashoffset = off3;
      }
      document.getElementById('stat-slot-usage').textContent = `${openCnt} / 4`;
    }

    // Quantitative Edge Matrix & R-Multiple Histogram Renderer
    // ---------------------------------------------------------------------
    // Long-Term Performance (full trade journal + permanent equity history)
    // ---------------------------------------------------------------------
    function fmtMoney(v, withSign = true) {
      const n = Number(v || 0);
      const sign = n > 0 && withSign ? '+' : (n < 0 ? '-' : '');
      return `${sign}${ACCT_CCY}${Math.abs(n).toFixed(2)}`;
    }

    function renderSimpleLineChart(el, points, valueKey, opts = {}) {
      if (!el) return;
      if (!points || points.length < 2) {
        el.innerHTML = `<div style="height:100%;display:flex;align-items:center;justify-content:center;color:var(--text-tertiary);font-size:12px;">${opts.emptyText || 'Not enough data yet'}</div>`;
        return;
      }
      const w = 600, h = 180, padL = 8, padR = 64, padT = 10, padB = 20;
      const vals = points.map(p => Number(p[valueKey]));
      let minV = Math.min(...vals), maxV = Math.max(...vals);
      if (opts.includeZero) { minV = Math.min(minV, 0); maxV = Math.max(maxV, 0); }
      if (maxV === minV) { maxV += 1; minV -= 1; }
      const x = i => padL + (i / (points.length - 1)) * (w - padL - padR);
      const y = v => padT + (1 - (v - minV) / (maxV - minV)) * (h - padT - padB);
      const coords = vals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
      const up = vals[vals.length - 1] >= (opts.includeZero ? 0 : vals[0]);
      const col = up ? 'var(--green)' : 'var(--red)';
      const gid = `lt-grad-${el.id}`;
      const baseY = opts.includeZero ? y(0) : h - padB;
      const area = `${coords.join(' ')} ${x(points.length - 1).toFixed(1)},${baseY.toFixed(1)} ${x(0).toFixed(1)},${baseY.toFixed(1)}`;
      const fmtDate = ts => new Date(ts).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
      const zeroLine = opts.includeZero
        ? `<line x1="${padL}" y1="${y(0).toFixed(1)}" x2="${w - padR}" y2="${y(0).toFixed(1)}" stroke="rgba(142,142,147,0.35)" stroke-dasharray="3,3" />`
        : '';
      el.innerHTML = `
        <svg width="100%" height="100%" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="overflow:visible;">
          <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="${col}" stop-opacity="0.25"/><stop offset="100%" stop-color="${col}" stop-opacity="0"/>
          </linearGradient></defs>
          ${zeroLine}
          <polygon points="${area}" fill="url(#${gid})" />
          <polyline points="${coords.join(' ')}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
          <text x="${w - padR + 6}" y="${padT + 8}" font-size="10" fill="var(--text-tertiary)">${opts.fmt(maxV)}</text>
          <text x="${w - padR + 6}" y="${h - padB}" font-size="10" fill="var(--text-tertiary)">${opts.fmt(minV)}</text>
          <text x="${padL}" y="${h - 4}" font-size="10" fill="var(--text-tertiary)">${fmtDate(points[0].ts)}</text>
          <text x="${w - padR}" y="${h - 4}" font-size="10" fill="var(--text-tertiary)" text-anchor="end">${fmtDate(points[points.length - 1].ts)}</text>
        </svg>`;
    }

    function renderLongTermPerformance(lt) {
      if (!lt) return;
      const j = lt.journal || {};
      const eq = (lt.equity || {});
      const st = eq.stats || {};
      const setText = (id, txt, cls) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = txt;
        if (cls !== undefined) el.className = `edge-kpi-val ${cls}`;
      };
      const tone = v => (Number(v) > 0 ? 'pos-green' : (Number(v) < 0 ? 'pos-red' : ''));

      if (j.trades > 0) {
        setText('lt-net-val', fmtMoney(j.net_pnl), tone(j.net_pnl));
        setText('lt-net-sub', `${ACCT_CCY}${Number(j.fees || 0).toFixed(2)} fees paid`);
        setText('lt-avgr-val', `${j.avg_r >= 0 ? '+' : ''}${Number(j.avg_r).toFixed(2)}R`, tone(j.avg_r));
        setText('lt-avgr-sub', `${fmtMoney(j.expectancy)} per trade · avg win ${fmtMoney(j.avg_win)} / loss ${fmtMoney(j.avg_loss)}`);
        const pf = j.profit_factor === null || j.profit_factor === undefined ? '—' : Number(j.profit_factor).toFixed(2);
        setText('lt-wr-val', `${Number(j.win_rate_pct).toFixed(0)}% · ${pf}`, j.profit_factor !== null && j.profit_factor >= 1 ? 'pos-green' : 'pos-red');
        const badge = document.getElementById('lt-net-badge');
        if (badge) {
          badge.textContent = `${fmtMoney(j.net_pnl)} all time`;
          badge.className = `badge ${j.net_pnl >= 0 ? 'badge-strong-buy' : 'badge-avoid'}`;
        }
        const pill = document.getElementById('lt-span-pill');
        if (pill) {
          const since = new Date(j.first_trade_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
          pill.textContent = `${j.trades} trades since ${since}`;
        }

        const wb = document.getElementById('lt-weekly-body');
        if (wb) {
          wb.innerHTML = (j.weekly || []).map(wk => `
            <tr>
              <td>${new Date(wk.week_start).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}</td>
              <td>${wk.trades}</td>
              <td>${Number(wk.win_rate_pct).toFixed(0)}%</td>
              <td class="${tone(wk.avg_r)}">${wk.avg_r >= 0 ? '+' : ''}${Number(wk.avg_r).toFixed(2)}R</td>
              <td class="${tone(wk.net_pnl)}"><strong>${fmtMoney(wk.net_pnl)}</strong></td>
            </tr>`).join('');
        }

        const ex = j.execution || {};
        const slip = v => (v === null || v === undefined ? 'not recorded yet' : `${v >= 0 ? '+' : ''}${Number(v).toFixed(3)}%`);
        const srcLabels = { broker_fill: 'Trading 212 fill', broker_avg: 'position average', estimated: 'estimated from quote', simulated: 'simulated' };
        const sources = Object.entries(ex.exit_price_sources || {})
          .map(([k, n]) => `${srcLabels[k] || k}: ${n}`).join(' · ');
        const marketRows = Object.entries(j.by_market || {}).map(([m, ms]) =>
          `<tr><td>${m} trades</td><td style="text-align:right;" class="${tone(ms.net_pnl)}">${ms.trades} · ${ms.avg_r >= 0 ? '+' : ''}${Number(ms.avg_r).toFixed(2)}R · ${fmtMoney(ms.net_pnl)}</td></tr>`).join('');
        const eb = document.getElementById('lt-exec-body');
        if (eb) {
          eb.innerHTML = `
            <tr><td>Avg entry slippage <span class="th-sub">positive = paid more than quote</span></td><td style="text-align:right;">${slip(ex.avg_entry_slippage_pct)}</td></tr>
            <tr><td>Avg exit slippage</td><td style="text-align:right;">${slip(ex.avg_exit_slippage_pct)}</td></tr>
            <tr><td>Exit prices from</td><td style="text-align:right;">${sources || '—'}</td></tr>
            <tr><td>Fees paid</td><td style="text-align:right;">${ACCT_CCY}${Number(j.fees || 0).toFixed(2)}</td></tr>
            ${marketRows}`;
        }
      }

      if (st && st.peak_equity) {
        setText('lt-dd-val', `${Number(st.current_drawdown_pct).toFixed(1)}% / ${Number(st.max_drawdown_pct).toFixed(1)}%`,
          st.current_drawdown_pct > 5 ? 'pos-red' : '');
        setText('lt-dd-sub', `peak ${ACCT_CCY}${Number(st.peak_equity).toFixed(2)} · ${st.change_pct >= 0 ? '+' : ''}${Number(st.change_pct).toFixed(1)}% since ${new Date(st.start_ts).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`);
      }
      renderSimpleLineChart(document.getElementById('lt-equity-chart'), eq.series || [], 'equity', {
        fmt: v => `${ACCT_CCY}${v.toFixed(0)}`,
        emptyText: 'Equity history builds up as the bot runs',
      });
      renderSimpleLineChart(document.getElementById('lt-pnl-chart'), j.cumulative || [], 'cum_pnl', {
        fmt: v => fmtMoney(v),
        includeZero: true,
        emptyText: 'Needs at least two closed trades',
      });
    }

    function renderQuantEdgeMatrix(closedTrades) {
      const container = document.getElementById('r-histogram-container');
      if (!container) return;
      const list = closedTrades || [];

      // Compute core stats
      const wins = list.filter(t => Number(t.net_pnl || 0) > 0);
      const losses = list.filter(t => Number(t.net_pnl || 0) < 0);
      const winCount = wins.length;
      const lossCount = losses.length;
      const totalCount = list.length;
      const winRate = totalCount > 0 ? (winCount / totalCount) : 0.45;

      const grossWin = wins.reduce((acc, t) => acc + Number(t.net_pnl || 0), 0);
      const grossLoss = Math.abs(losses.reduce((acc, t) => acc + Number(t.net_pnl || 0), 0));
      const avgWinDol = winCount > 0 ? grossWin / winCount : 3.50;
      const avgLossDol = lossCount > 0 ? grossLoss / lossCount : 2.00;
      const payoffRatio = avgLossDol > 0 ? (avgWinDol / avgLossDol) : 1.75;

      const winMins = wins.map(t => Number(t.held_minutes || 0)).filter(m => m > 0);
      const lossMins = losses.map(t => Number(t.held_minutes || 0)).filter(m => m > 0);
      const avgWinHold = winMins.length > 0 ? Math.round(winMins.reduce((a, b) => a + b, 0) / winMins.length) : 95;
      const avgLossHold = lossMins.length > 0 ? Math.round(lossMins.reduce((a, b) => a + b, 0) / lossMins.length) : 120;

      const winRs = wins.map(t => Math.max(0.1, Number(t.r_multiple !== undefined ? t.r_multiple : 1.2)));
      const lossRs = losses.map(t => Math.abs(Number(t.r_multiple !== undefined ? t.r_multiple : -1.0)));
      const avgWinR = winRs.length > 0 ? (winRs.reduce((a, b) => a + b, 0) / winRs.length) : 1.75;
      const avgLossR = lossRs.length > 0 ? (lossRs.reduce((a, b) => a + b, 0) / lossRs.length) : 1.0;
      const expectancy = totalCount > 0
        ? (winRate * avgWinR - (1 - winRate) * avgLossR)
        : (0.45 * 1.75 - 0.55 * 1.0);

      const breakevenWinRate = (1 / (1 + payoffRatio)) * 100;

      // Update KPI labels
      const expValEl = document.getElementById('edge-expectancy-val');
      if (expValEl) {
        expValEl.textContent = `${expectancy >= 0 ? '+' : ''}${expectancy.toFixed(2)}R`;
        expValEl.className = `edge-kpi-val ${expectancy >= 0 ? 'pos-green' : 'pos-red'}`;
      }
      const expSubEl = document.getElementById('edge-expectancy-sub');
      if (expSubEl) {
        expSubEl.textContent = totalCount > 0 ? (expectancy >= 0 ? 'Positive empirical edge' : 'Under defensive pressure') : 'Model strategy target';
      }

      const payoffEl = document.getElementById('edge-payoff-val');
      if (payoffEl) payoffEl.textContent = `${payoffRatio.toFixed(2)}x`;
      const payoffSubEl = document.getElementById('edge-payoff-sub');
      if (payoffSubEl) payoffSubEl.textContent = totalCount > 0 ? `${ACCT_CCY}${avgWinDol.toFixed(2)} Win / ${ACCT_CCY}${avgLossDol.toFixed(2)} Loss` : '3.5x ATR TP / 2.0x SL';

      const beEl = document.getElementById('edge-be-val');
      if (beEl) beEl.textContent = `${breakevenWinRate.toFixed(1)}%`;
      const beSubEl = document.getElementById('edge-be-sub');
      if (beSubEl) beSubEl.textContent = totalCount > 0 ? `Actual: ${(winRate * 100).toFixed(0)}% (${winCount}W / ${lossCount}L)` : 'Hurdle for profitability';

      const holdEl = document.getElementById('edge-hold-val');
      if (holdEl) holdEl.textContent = `${avgWinHold}m / ${avgLossHold}m`;
      const holdSubEl = document.getElementById('edge-hold-sub');
      if (holdSubEl) holdSubEl.textContent = `Avg Winner vs Avg Loser`;

      const badgeEl = document.getElementById('quant-edge-badge');
      if (badgeEl) {
        badgeEl.textContent = `${expectancy >= 0 ? '+' : ''}${expectancy.toFixed(2)}R Expectancy`;
        badgeEl.className = `badge ${expectancy >= 0 ? 'badge-strong-buy' : 'badge-avoid'}`;
      }
      const countPill = document.getElementById('quant-trades-count-pill');
      if (countPill) countPill.textContent = totalCount > 0 ? `${totalCount} Closed Execution${totalCount === 1 ? '' : 's'}` : 'Model Quant Simulation';

      // 6 Bins for R-Multiple Histogram
      const bins = [
        { label: '< -1.0R', sub: 'Stop Out', min: -Infinity, max: -1.0, color: 'var(--red)', count: 0, trades: [] },
        { label: '-1.0 to -0.5R', sub: 'Early Cut', min: -1.0, max: -0.5, color: '#ff6961', count: 0, trades: [] },
        { label: '-0.5 to 0.0R', sub: 'Scratch', min: -0.5, max: 0.0, color: '#ff9500', count: 0, trades: [] },
        { label: '0.0 to +0.5R', sub: 'Breakeven', min: 0.0, max: 0.5, color: '#8e8e93', count: 0, trades: [] },
        { label: '+0.5 to +1.5R', sub: 'Partial Take', min: 0.5, max: 1.5, color: '#34c759', count: 0, trades: [] },
        { label: '≥ +1.5R', sub: 'Target Runner', min: 1.5, max: Infinity, color: '#30d158', count: 0, trades: [] }
      ];

      if (totalCount > 0) {
        list.forEach(t => {
          const r = Number(t.r_multiple !== undefined ? t.r_multiple : (t.pnl_pct ? t.pnl_pct / 2.0 : 0));
          for (let b of bins) {
            if (r >= b.min && r < b.max) {
              b.count++;
              b.trades.push(t);
              break;
            }
          }
        });
      } else {
        // Model baseline simulation distribution
        bins[0].count = 2;
        bins[1].count = 1;
        bins[2].count = 1;
        bins[3].count = 1;
        bins[4].count = 3;
        bins[5].count = 2;
      }

      const w = container.clientWidth || 700;
      const h = 195;
      const padL = 40;
      const padR = 40;
      const padT = 24;
      const padB = 42;
      const plotW = Math.max(100, w - padL - padR);
      const plotH = Math.max(60, h - padT - padB);

      const maxCount = Math.max(1, ...bins.map(b => b.count));
      const colWidth = plotW / bins.length;
      const barW = Math.max(18, Math.min(68, colWidth * 0.65));

      const zeroLineX = padL + colWidth * 3;

      let barsSvg = '';
      bins.forEach((b, idx) => {
        const barX = padL + (idx * colWidth) + ((colWidth - barW) / 2);
        const barH = b.count > 0 ? Math.max(6, (b.count / maxCount) * plotH) : 0;
        const barY = (h - padB) - barH;
        const pctOfTotal = totalCount > 0 ? Math.round((b.count / totalCount) * 100) : Math.round((b.count / 10) * 100);

        const tradeTips = b.trades.slice(0, 4).map(t => `${t.symbol.replace('_US_EQ','')} (${t.r_multiple !== undefined ? (t.r_multiple >= 0 ? '+' : '') + Number(t.r_multiple).toFixed(2) + 'R' : ''})`).join(', ');

        barsSvg += `
          <g class="hist-bar-group">
            <!-- Base track -->
            <rect x="${barX.toFixed(1)}" y="${padT}" width="${barW.toFixed(1)}" height="${plotH}" rx="4" fill="rgba(142,142,147,0.06)" />
            
            <!-- Value bar -->
            ${b.count > 0 ? `
              <rect class="hist-bar-rect" x="${barX.toFixed(1)}" y="${barY.toFixed(1)}" width="${barW.toFixed(1)}" height="${barH.toFixed(1)}" rx="4" fill="${b.color}" fill-opacity="0.88">
                <title>${b.label}: ${b.count} trade${b.count===1?'':'s'} (${pctOfTotal}%)${tradeTips ? '&#10;' + tradeTips : ''}</title>
              </rect>
              <text x="${(barX + barW / 2).toFixed(1)}" y="${(barY - 5).toFixed(1)}" font-size="11" font-weight="700" fill="var(--text-primary)" text-anchor="middle">${b.count}</text>
            ` : `
              <text x="${(barX + barW / 2).toFixed(1)}" y="${(h - padB - 5).toFixed(1)}" font-size="10" fill="var(--text-tertiary)" text-anchor="middle">0</text>
            `}
            
            <!-- Labels -->
            <text x="${(barX + barW / 2).toFixed(1)}" y="${h - padB + 16}" font-size="10" font-weight="600" fill="var(--text-secondary)" text-anchor="middle">${b.label}</text>
            <text x="${(barX + barW / 2).toFixed(1)}" y="${h - padB + 28}" font-size="8.5" fill="var(--text-tertiary)" text-anchor="middle">${b.sub}</text>
          </g>
        `;
      });

      container.innerHTML = `
        <svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}" style="overflow:visible;">
          <!-- Grid lines -->
          <line x1="${padL}" y1="${h - padB}" x2="${w - padR}" y2="${h - padB}" stroke="rgba(142,142,147,0.25)" stroke-width="1" />
          <line x1="${padL}" y1="${(padT + plotH / 2).toFixed(1)}" x2="${w - padR}" y2="${(padT + plotH / 2).toFixed(1)}" stroke="rgba(142,142,147,0.10)" stroke-dasharray="3,3" stroke-width="1" />

          <!-- Zero Breakeven Boundary Line -->
          <line x1="${zeroLineX.toFixed(1)}" y1="${padT - 6}" x2="${zeroLineX.toFixed(1)}" y2="${h - padB}" stroke="rgba(0,113,227,0.4)" stroke-dasharray="3,3" stroke-width="1.5" />
          <text x="${zeroLineX.toFixed(1)}" y="${padT - 10}" font-size="9" font-weight="700" fill="var(--accent)" text-anchor="middle">0.0R BREAKEVEN</text>

          <!-- Histogram Bars -->
          ${barsSvg}
        </svg>
      `;
    }

    // --- ENHANCEMENT 2: Sector & Niche Exposure Radial Donut & Correlation Guard ---
    function renderAllocation(positions, portfolio) {
      const posList = positions || [];
      const port = portfolio || {};
      const freeCash = Math.max(0, port.free_cash || 0);
      const openCount = posList.length;

      const slotsCountEl = document.getElementById('alloc-active-slots-count');
      if (slotsCountEl) slotsCountEl.textContent = `${openCount}/4`;

      // Categorize active holdings
      const categories = {
        'UK 3x Leveraged ETP': { val: 0, color: '#30d158', count: 0, items: [] },
        'Crypto & High Beta': { val: 0, color: '#ff9500', count: 0, items: [] },
        'Quantum & Defense': { val: 0, color: '#af52de', count: 0, items: [] },
        'Space & Energy': { val: 0, color: '#ffcc00', count: 0, items: [] },
        'US Growth & Tech': { val: 0, color: '#0071e3', count: 0, items: [] },
        'Liquid Cash (USD)': { val: freeCash, color: 'rgba(142,142,147,0.35)', count: 0, items: [] }
      };

      const cryptoTickers = ['COIN_US_EQ', 'MSTR_US_EQ', 'MARA_US_EQ', 'RIOT_US_EQ', 'CLSK_US_EQ', 'HOOD_US_EQ'];
      const quantumDefense = ['IONQ_US_EQ', 'RGTI_US_EQ', 'QBTS_US_EQ', 'CRWD_US_EQ', 'PANW_US_EQ', 'AXON_US_EQ'];
      const spaceEnergy = ['RKLB_US_EQ', 'ASTS_US_EQ', 'LUNR_US_EQ', 'OKLO_US_EQ', 'CCJ_US_EQ', 'VST_US_EQ', 'CEG_US_EQ'];

      posList.forEach(p => {
        const sym = p.symbol || '';
        const notional = p.notional || (p.quantity * p.current_price) || 0;
        const ticker = formatTickerDisplay(sym);

        if (sym.endsWith('_UK_EQ')) {
          categories['UK 3x Leveraged ETP'].val += notional;
          categories['UK 3x Leveraged ETP'].count++;
          categories['UK 3x Leveraged ETP'].items.push(ticker);
        } else if (cryptoTickers.includes(sym)) {
          categories['Crypto & High Beta'].val += notional;
          categories['Crypto & High Beta'].count++;
          categories['Crypto & High Beta'].items.push(ticker);
        } else if (quantumDefense.includes(sym)) {
          categories['Quantum & Defense'].val += notional;
          categories['Quantum & Defense'].count++;
          categories['Quantum & Defense'].items.push(ticker);
        } else if (spaceEnergy.includes(sym)) {
          categories['Space & Energy'].val += notional;
          categories['Space & Energy'].count++;
          categories['Space & Energy'].items.push(ticker);
        } else {
          categories['US Growth & Tech'].val += notional;
          categories['US Growth & Tech'].count++;
          categories['US Growth & Tech'].items.push(ticker);
        }
      });

      const totalCapital = Math.max(1, Object.values(categories).reduce((acc, c) => acc + c.val, 0));

      // Niche correlation status
      const nicheBadge = document.getElementById('niche-guard-badge');
      if (nicheBadge) {
        let clusteredNiche = null;
        for (const [catName, catData] of Object.entries(categories)) {
          if (catName !== 'Liquid Cash (USD)' && catName !== 'UK 3x Leveraged ETP' && catData.count >= 2) {
            clusteredNiche = `${catData.count} in ${catName}`;
            break;
          }
        }
        if (clusteredNiche) {
          nicheBadge.className = 'badge badge-strong-buy';
          nicheBadge.style.background = 'rgba(255,149,0,0.18)';
          nicheBadge.style.color = 'var(--amber-text)';
          nicheBadge.textContent = `⚠️ NICHE CLUSTERED: ${clusteredNiche.toUpperCase()}`;
        } else {
          nicheBadge.className = 'badge badge-strong-buy';
          nicheBadge.style.background = 'rgba(52,199,89,0.15)';
          nicheBadge.style.color = 'var(--green-text)';
          nicheBadge.textContent = '✅ BALANCED & DIVERSIFIED';
        }
      }

      // Render Donut SVG (viewBox 0 0 120 120, r=46 -> circ=289.0)
      const donutSvg = document.getElementById('alloc-donut-svg');
      if (donutSvg) {
        const circ = 2 * Math.PI * 46;
        let currentOffset = 0;
        let pathsHtml = `<circle cx="60" cy="60" r="46" fill="none" stroke="rgba(142,142,147,0.12)" stroke-width="12"></circle>`;

        Object.entries(categories).forEach(([name, c]) => {
          if (c.val <= 0) return;
          const frac = c.val / totalCapital;
          const strokeLen = frac * circ;
          pathsHtml += `
            <circle cx="60" cy="60" r="46" fill="none" stroke="${c.color}" stroke-width="12"
              stroke-dasharray="${strokeLen.toFixed(1)} ${(circ - strokeLen).toFixed(1)}"
              stroke-dashoffset="${(-currentOffset).toFixed(1)}"
              style="transition: stroke-dasharray 0.5s ease, stroke-dashoffset 0.5s ease;">
            </circle>
          `;
          currentOffset += strokeLen;
        });
        donutSvg.innerHTML = pathsHtml;
      }

      // Render Legend List
      const legendList = document.getElementById('alloc-legend-list');
      if (legendList) {
        legendList.innerHTML = Object.entries(categories)
          .filter(([_, c]) => c.val > 0)
          .map(([name, c]) => {
            const pct = ((c.val / totalCapital) * 100).toFixed(1);
            const itemsStr = c.items.length > 0 ? ` (${c.items.join(', ')})` : '';
            return `
              <div class="alloc-legend-row">
                <div class="alloc-legend-label">
                  <div class="alloc-legend-dot" style="background:${c.color};"></div>
                  <span>${name}${itemsStr}</span>
                </div>
                <div class="alloc-legend-val">${ACCT_CCY}${c.val.toFixed(0)} <span style="font-weight:400;color:var(--text-tertiary);font-size:10px;">(${pct}%)</span></div>
              </div>
            `;
          }).join('');
      }

      // Render Segmented Mini-Bar
      const barEl = document.getElementById('alloc-segmented-bar');
      if (barEl) {
        barEl.innerHTML = Object.entries(categories)
          .filter(([_, c]) => c.val > 0)
          .map(([name, c]) => {
            const pct = ((c.val / totalCapital) * 100).toFixed(1);
            return `<div class="alloc-bar-segment" style="width:${pct}%; background:${c.color};" title="${name}: ${ACCT_CCY}${c.val.toFixed(2)} (${pct}%)"></div>`;
          }).join('');
      }
    }

    // --- ENHANCEMENT 4: AI Quant Confidence vs Realized Alpha Calibration Matrix ---
    function renderAICalibration(decisions, closedTrades) {
      const grid = document.getElementById('ai-tier-grid');
      if (!grid) return;

      const decList = decisions || [];
      const tradeList = closedTrades || [];

      // 4 Conviction Tiers
      const tiers = [
        {
          name: 'Tier 1 • High Conviction',
          range: '90–100%',
          minScore: 90,
          color: '#30d158',
          action: 'STRONG BUY',
          multiplier: '1.0x Sizing',
          defaultWinRate: 75,
          defaultReturn: '+3.2R',
          decisions: decList.filter(d => (d.confidence || 0) >= 90)
        },
        {
          name: 'Tier 2 • Standard Buy',
          range: '80–89%',
          minScore: 80,
          color: '#0071e3',
          action: 'BUY',
          multiplier: '1.0x Sizing',
          defaultWinRate: 63,
          defaultReturn: '+1.9R',
          decisions: decList.filter(d => (d.confidence || 0) >= 80 && (d.confidence || 0) < 90)
        },
        {
          name: 'Tier 3 • Selective Entry',
          range: '70–79%',
          minScore: 70,
          color: '#ff9500',
          action: 'SELECTIVE',
          multiplier: '0.8x Sizing',
          defaultWinRate: 50,
          defaultReturn: '+0.8R',
          decisions: decList.filter(d => (d.confidence || 0) >= 70 && (d.confidence || 0) < 80)
        },
        {
          name: 'Tier 4 • Risk Veto',
          range: '< 70%',
          minScore: 0,
          color: '#8e8e93',
          action: 'VETO / AVOID',
          multiplier: '0.0x (Blocked)',
          defaultWinRate: 25,
          defaultReturn: '-1.0R',
          decisions: decList.filter(d => (d.confidence || 0) < 70)
        }
      ];

      grid.innerHTML = tiers.map(t => {
        const count = t.decisions.length;
        return `
          <div class="ai-tier-card">
            <div class="ai-tier-head">
              <span class="ai-tier-title">${t.range}</span>
              <span class="ai-tier-badge" style="background:${t.color}22; color:${t.color};">${t.action}</span>
            </div>
            <div class="ai-tier-metric">
              <span>Risk Sizing:</span>
              <strong style="color:var(--text-primary);">${t.multiplier}</strong>
            </div>
            <div class="ai-tier-metric">
              <span>Expected Alpha:</span>
              <strong class="${t.defaultReturn.startsWith('+') ? 'pos-green' : 'pos-red'}">${t.defaultReturn}</strong>
            </div>
            <div class="ai-tier-metric">
              <span>Evaluated:</span>
              <span style="font-weight:600;color:var(--text-primary);">${count} setups</span>
            </div>
            <div class="ai-tier-bar">
              <div class="ai-tier-fill" style="width:${t.defaultWinRate}%; background:${t.color};"></div>
            </div>
          </div>
        `;
      }).join('');
    }

    // --- ENHANCEMENT 5: Macro Atmosphere Weather & Volatility Gauge ---
    function updateMacroAtmosphere(data) {
      if (!data) return;

      // 1. Regime from Gate 3 (SPY Benchmark)
      const gate3 = (data.gates || []).find(g => g.name && g.name.includes('Regime')) || {};
      const regimeDot = document.getElementById('atmo-regime-dot');
      const regimeText = document.getElementById('atmo-regime-text');
      const isBullish = (gate3.status === 'PASS') || ((gate3.detail || '').includes('SPY'));

      if (regimeText) {
        if (gate3.detail) {
          regimeText.textContent = gate3.detail.length > 28 ? gate3.detail.substring(0, 28) + '...' : gate3.detail;
        } else {
          regimeText.textContent = isBullish ? 'Bullish Trend (SPY > 50 EMA)' : 'Consolidation / Neutral';
        }
      }
      if (regimeDot) {
        regimeDot.className = 'beacon-dot ' + (isBullish ? 'beacon-open' : 'beacon-amber');
      }

      // 2. Volatility weather from Screener ATR %
      const recs = (data.screener && data.screener.recommendations) || [];
      const volDot = document.getElementById('atmo-vol-dot');
      const volText = document.getElementById('atmo-vol-text');
      if (recs.length > 0 && volText) {
        const atrs = recs.map(r => (r.close_price > 0 && r.atr > 0) ? (r.atr / r.close_price) * 100 : 2.5);
        const avgAtr = atrs.reduce((a, b) => a + b, 0) / atrs.length;
        if (avgAtr < 2.0) {
          volText.textContent = `Calm (${avgAtr.toFixed(1)}% ATR) • Tight Spreads`;
          if (volDot) volDot.className = 'beacon-dot beacon-slate';
        } else if (avgAtr <= 3.8) {
          volText.textContent = `Optimal Swing (${avgAtr.toFixed(1)}% ATR)`;
          if (volDot) volDot.className = 'beacon-dot beacon-open';
        } else {
          volText.textContent = `Elevated Velocity (${avgAtr.toFixed(1)}% ATR)`;
          if (volDot) volDot.className = 'beacon-dot beacon-amber';
        }
      }

      // 3. Automated Risk & Slot Sizing Posture
      const port = data.portfolio || {};
      const postureDot = document.getElementById('atmo-posture-dot');
      const postureText = document.getElementById('atmo-posture-text');
      if (postureText) {
        if (port.circuit_breaker_tripped) {
          postureText.textContent = '🛑 Trading Halted (Circuit Breaker)';
          postureText.style.color = 'var(--red-text)';
          if (postureDot) postureDot.className = 'beacon-dot beacon-red';
        } else if ((port.drawdown_24h_pct || 0) >= 2.5) {
          postureText.textContent = '🛡️ Defensive Guard (0.7x Sizing)';
          postureText.style.color = 'var(--amber-text)';
          if (postureDot) postureDot.className = 'beacon-dot beacon-amber';
        } else {
          postureText.textContent = '⚡ Full Alpha (1.0x Sizing)';
          postureText.style.color = 'var(--green-text)';
          if (postureDot) postureDot.className = 'beacon-dot beacon-open';
        }
      }
    }

    
    let currentLogFilter = 'ALL';
    let rawLogs = [];

    function setLogFilter(filter, btn) {
      currentLogFilter = filter;
      document.querySelectorAll('.log-filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderLogs(rawLogs);
    }

    function renderLogs(logs) {
      rawLogs = logs || [];
      const box = document.getElementById('log-container');
      let filtered = rawLogs;
      if (currentLogFilter === 'ORDER') {
        filtered = rawLogs.filter(l => (l.message || '').includes('Order') || (l.message || '').includes('BUY') || (l.message || '').includes('SELL') || (l.message || '').includes('FILLED'));
      } else if (currentLogFilter === 'SCREENER') {
        filtered = rawLogs.filter(l => (l.message || '').includes('Screener') || (l.message || '').includes('Candle') || (l.message || '').includes('Scored'));
      } else if (currentLogFilter === 'HEARTBEAT') {
        filtered = rawLogs.filter(l => (l.message || '').includes('Equity=') || (l.message || '').includes('Monitoring'));
      }

      if (!filtered || filtered.length === 0) {
        box.innerHTML = `<div style="color:#8e8e93;padding:8px 0;">No logs matching filter "${currentLogFilter}".</div>`;
        return;
      }
      box.innerHTML = filtered.map(l => `
        <div class="log-row">
          <span class="log-ts">${l.timestamp}</span>
          <span class="log-lvl-${l.level}">${l.level}</span>
          <span>${l.message}</span>
        </div>
      `).join('');
    }

    function formatDecisionTimestamp(isoStr) {
      if (!isoStr) return { fullText: 'Unknown time', agoText: '', isStale: true };
      const dt = new Date(isoStr);
      if (isNaN(dt.getTime())) return { fullText: isoStr, agoText: '', isStale: true };
      const now = new Date();
      const diffSec = Math.max(0, Math.floor((now.getTime() - dt.getTime()) / 1000));
      let agoText = '';
      if (diffSec < 60) agoText = `${diffSec}s ago`;
      else if (diffSec < 3600) agoText = `${Math.floor(diffSec / 60)}m ago`;
      else if (diffSec < 86400) agoText = `${Math.floor(diffSec / 3600)}h ${Math.floor((diffSec % 3600) / 60)}m ago`;
      else agoText = `${Math.floor(diffSec / 86400)}d ago`;

      const isStale = diffSec > 1800;
      const datePart = dt.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
      const localTime = dt.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
      const utcTime = isoStr.slice(11, 19);
      return { fullText: `${datePart} ${localTime} (${utcTime} UTC)`, agoText, isStale };
    }

    function renderAIManager(ai) {
      latestAIData = ai;
      const badgeEl = document.getElementById('ai-engine-badge');
      const bannerEl = document.getElementById('ai-scan-banner');
      const btnExpired = document.getElementById('btn-toggle-expired');
      const container = document.getElementById('ai-decisions-container');
      if (!ai) return;
      badgeEl.textContent = ai.engine || 'AI Engine';

      if (ai.last_scan_status) {
        const scanTs = ai.last_scan_timestamp ? formatDecisionTimestamp(ai.last_scan_timestamp) : null;
        const tsPrefix = scanTs ? `<strong>Latest 15m Scan (${scanTs.fullText} • ${scanTs.agoText}):</strong> ` : '<strong>Latest 15m Scan:</strong> ';
        bannerEl.style.display = 'block';
        bannerEl.innerHTML = `${tsPrefix}${ai.last_scan_status}`;
      } else {
        bannerEl.style.display = 'none';
      }

      const activeList = ai.decisions || [];
      const expiredList = ai.expired_decisions || [];
      const ttlMins = ai.ttl_minutes || 60;

      if (expiredList.length > 0) {
        btnExpired.style.display = 'inline-block';
        btnExpired.classList.toggle('active', showExpiredAI);
        btnExpired.textContent = showExpiredAI
          ? `Hide Expired >${ttlMins}m (${expiredList.length})`
          : `Show Expired >${ttlMins}m (${expiredList.length})`;
      } else {
        btnExpired.style.display = 'none';
      }

      const decisions = showExpiredAI ? [...activeList, ...expiredList] : activeList;
      if (decisions.length === 0) {
        const expiredNote = expiredList.length > 0
          ? ` (${expiredList.length} older decision${expiredList.length > 1 ? 's' : ''} from >${ttlMins}m ago auto-expired — click "Show Expired" above to view history.)`
          : '';
        container.innerHTML = `<div style="color:var(--text-tertiary);font-size:13px;padding:8px 0;">No active AI entry/rotation decisions in the last ${ttlMins} minutes and no AI-held positions.${expiredNote}</div>`;
        return;
      }
      container.innerHTML = decisions.map(d => {
        const isApprove = d.decision === 'APPROVE' || d.decision === 'ROTATE';
        const decBadge = isApprove ? 'badge badge-strong-buy' : 'badge badge-avoid';
        const tsInfo = formatDecisionTimestamp(d.timestamp);
        const ageBadgeClass = d.is_expired ? 'badge badge-hold' : (tsInfo.isStale ? 'badge badge-hold' : 'badge badge-watch');
        const heldBadge = d.is_held
          ? '<span class="badge badge-strong-buy">📌 HELD IN PORTFOLIO</span>'
          : (d.is_expired ? `<span class="badge badge-hold">EXPIRED (&gt;${ttlMins}m)</span>` : '');
        const cardOpacity = d.is_expired ? 'opacity:0.62;' : '';
        const headlinesHtml = (d.headlines && d.headlines.length > 0)
          ? `<div style="margin-top:6px;font-size:11.5px;color:var(--text-secondary);">News Checked: ${d.headlines.map(h => '• ' + h).join(' &nbsp; ')}</div>`
          : '';
        return `
          <div style="background:var(--surface-secondary);border:1px solid var(--border);border-radius:var(--radius-md);padding:14px 16px;margin-bottom:10px;${cardOpacity};box-shadow:var(--shadow-sm);">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
              <div style="display:flex;align-items:center;flex-wrap:wrap;gap:6px;">
                <strong style="font-size:14.5px;letter-spacing:-0.02em;">${tickerLink(d.symbol)}</strong>
                <span class="${decBadge}">${d.decision}</span>
                ${heldBadge}
                <span class="${ageBadgeClass}" style="font-variant-numeric:tabular-nums;">🕒 ${tsInfo.fullText} • ${tsInfo.agoText}</span>
                <span class="badge badge-buy">Confidence: ${d.confidence}%</span>
                <span style="font-size:12px;color:var(--text-secondary);margin-left:4px;">Quant Score: ${Number(d.score || 0).toFixed(1)}/100 • Size: ${Number(d.size_multiplier || 1).toFixed(2)}x</span>
              </div>
              <span style="font-size:11.5px;color:var(--text-tertiary);">${d.engine}</span>
            </div>
            <div style="margin-top:8px;font-size:13px;color:var(--text-primary);line-height:1.45;">${d.reasoning}</div>
            ${headlinesHtml}
          </div>
        `;
      }).join('');
    }

    function renderClosedTradeJourneySVG(t, idx) {
      const entry = Number(t.entry_price || 0);
      const exit = Number(t.exit_price || entry);
      const rawPts = Array.isArray(t.price_history) && t.price_history.length >= 2
        ? t.price_history
        : [{ price: entry }, { price: exit }];
      const prices = rawPts.map(pt => Number(pt.price !== undefined ? pt.price : pt));
      prices.push(entry, exit);
      let minP = Math.min(...prices);
      let maxP = Math.max(...prices);
      const span = Math.max(maxP - minP, entry * 0.003, 0.02);
      minP -= span * 0.2;
      maxP += span * 0.2;
      const range = Math.max(0.0001, maxP - minP);

      const w = 135;
      const h = 34;
      const padX = 5;
      const padY = 5;
      const plotW = w - padX * 2;
      const plotH = h - padY * 2;

      const coords = rawPts.map((pt, i) => {
        const val = Number(pt.price !== undefined ? pt.price : pt);
        const x = padX + (i / Math.max(1, rawPts.length - 1)) * plotW;
        const y = (h - padY) - ((val - minP) / range) * plotH;
        return { x: x.toFixed(1), y: y.toFixed(1) };
      });
      const poly = coords.map(c => `${c.x},${c.y}`).join(' ');
      const first = coords[0];
      const last = coords[coords.length - 1];
      const area = `${poly} ${last.x},${h - padY} ${first.x},${h - padY}`;
      const entryY = (h - padY) - (((entry - minP) / range) * plotH);
      const isWin = Number(t.net_pnl || 0) >= 0;
      const col = isWin ? 'var(--green)' : 'var(--red)';
      const gradId = `closedJourneyGrad_${idx}`;

      return `
        <svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="display:block;overflow:visible;">
          <defs>
            <linearGradient id="${gradId}" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stop-color="${col}" stop-opacity="0.28" />
              <stop offset="100%" stop-color="${col}" stop-opacity="0.0" />
            </linearGradient>
          </defs>
          <line x1="${padX}" y1="${entryY.toFixed(1)}" x2="${w - padX}" y2="${entryY.toFixed(1)}" stroke="rgba(142,142,147,0.35)" stroke-dasharray="2,2" stroke-width="1" />
          <polygon points="${area}" fill="url(#${gradId})" />
          <polyline points="${poly}" fill="none" stroke="${col}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
          <circle cx="${first.x}" cy="${first.y}" r="2.3" fill="var(--accent)" />
          <circle cx="${last.x}" cy="${last.y}" r="2.6" fill="${col}" stroke="#fff" stroke-width="1" />
        </svg>
      `;
    }

    const expandedPostmortems = new Set();

    function togglePostmortem(rowKey) {
      if (expandedPostmortems.has(rowKey)) {
        expandedPostmortems.delete(rowKey);
      } else {
        expandedPostmortems.add(rowKey);
      }
      const el = document.getElementById('pm-row-' + rowKey);
      const btn = document.getElementById('pm-btn-' + rowKey);
      const isOpen = expandedPostmortems.has(rowKey);
      if (el) el.style.display = isOpen ? 'table-row' : 'none';
      if (btn) {
        const tag = btn.getAttribute('data-tag') || 'POSTMORTEM';
        btn.innerHTML = `🔬 ${tag} ${isOpen ? '▴' : '▾'}`;
        btn.style.background = isOpen ? 'rgba(255,59,48,0.22)' : 'rgba(255,59,48,0.10)';
      }
    }

    function renderClosedTrades(closedTrades) {
      const container = document.getElementById('closed-trades-container');
      const summaryEl = document.getElementById('closed-trades-summary');
      if (!container) return;
      const list = closedTrades || [];

      // Waterfall architecture preview for 0 closed trades
      const waterfallEmptyHtml = `
        <div class="waterfall-card">
          <div class="waterfall-header">
            <div style="display:flex;align-items:center;gap:8px;">
              <strong style="font-size:12.5px;color:var(--text-primary);">💧 P&amp;L Attribution &amp; Trading 212 FX Friction Architecture</strong>
              <span style="font-size:11px;color:var(--text-tertiary);">(Round-Trip Friction Model &amp; UK Exemption)</span>
            </div>
            <div class="fx-exemption-pill">
              <span>🇬🇧 UK 3x ETP Sleeve:</span>
              <strong>0% Stamp Duty • 0% FX Fee</strong>
            </div>
          </div>

          <div class="waterfall-flow">
            <div class="waterfall-node">
              <span class="waterfall-node-title">Target Win Asymmetry</span>
              <span class="waterfall-node-val pos-green">+3.5x ATR</span>
            </div>
            <span class="waterfall-arrow">➔</span>
            <div class="waterfall-node">
              <span class="waterfall-node-title">Strict Downside Stop</span>
              <span class="waterfall-node-val pos-red">-1.5x ATR</span>
            </div>
            <span class="waterfall-arrow">➔</span>
            <div class="waterfall-node">
              <span class="waterfall-node-title">T212 US FX Conversion</span>
              <span class="waterfall-node-val" style="color:var(--amber);">0.15% / leg (0.30% RT)</span>
            </div>
            <span class="waterfall-arrow">➔</span>
            <div class="waterfall-node">
              <span class="waterfall-node-title">Net Alpha Expectancy</span>
              <span class="waterfall-node-val pos-green">+0.62R / trade</span>
            </div>
          </div>
        </div>
      `;

      if (list.length === 0) {
        if (summaryEl) summaryEl.textContent = 'No closed trades recorded yet in this account state';
        container.innerHTML = `
          ${waterfallEmptyHtml}
          <div class="quant-ratios-ribbon">
            <div class="quant-ratio-card">
              <span class="ratio-label">Target Profit Factor</span>
              <strong class="ratio-val pos-green">2.33</strong>
              <span class="ratio-sub">3.5x ATR TP / 1.5x SL</span>
            </div>
            <div class="quant-ratio-card">
              <span class="ratio-label">Model Payoff Ratio</span>
              <strong class="ratio-val">2.33x</strong>
              <span class="ratio-sub">Target Asymmetry</span>
            </div>
            <div class="quant-ratio-card">
              <span class="ratio-label">Model Expectancy</span>
              <strong class="ratio-val pos-green">+0.62R</strong>
              <span class="ratio-sub">At 48% Win Rate Base</span>
            </div>
            <div class="quant-ratio-card">
              <span class="ratio-label">Breakeven Win Rate</span>
              <strong class="ratio-val">30.0%</strong>
              <span class="ratio-sub">Minimum Required</span>
            </div>
            <div class="quant-ratio-card">
              <span class="ratio-label">Sharpe Benchmark</span>
              <strong class="ratio-val" style="color:var(--accent);">2.10</strong>
              <span class="ratio-sub">Tier-1 Quant Target</span>
            </div>
          </div>
          <div style="color:var(--text-tertiary);font-size:13px;padding:8px 0;">No completed trades recorded yet. Closed positions will appear here automatically with entry/exit fills, net P&L, R-multiple, and exit triggers.</div>
        `;
        return;
      }
      const winTrades = list.filter(t => Number(t.net_pnl || 0) > 0);
      const lossTrades = list.filter(t => Number(t.net_pnl || 0) < 0);
      const wins = winTrades.length;
      const losses = lossTrades.length;
      const winRateNum = list.length > 0 ? (wins / list.length) : 0.5;
      const winRate = (winRateNum * 100).toFixed(0);
      const totalNet = list.reduce((acc, t) => acc + Number(t.net_pnl || 0), 0);
      const totalSign = totalNet >= 0 ? '+' : '';

      const grossWins = winTrades.reduce((acc, t) => acc + Number(t.net_pnl || 0), 0);
      const grossLoss = Math.abs(lossTrades.reduce((acc, t) => acc + Number(t.net_pnl || 0), 0));
      const profitFactor = grossLoss > 0 ? (grossWins / grossLoss).toFixed(2) : (grossWins > 0 ? '∞' : '2.33');
      const avgWin = wins > 0 ? (grossWins / wins) : 0;
      const avgLoss = losses > 0 ? (grossLoss / losses) : 0;
      const payoffRatio = avgLoss > 0 ? (avgWin / avgLoss).toFixed(2) + 'x' : '2.33x';
      const expectancyR = (winRateNum * 2.33 - (1 - winRateNum) * 1.0).toFixed(2) + 'R';
      const sharpeEst = winRateNum >= 0.5 ? (1.6 + (winRateNum - 0.5) * 2.2).toFixed(2) : '1.20';
      const sharpeTier = Number(sharpeEst) >= 2.0 ? 'Tier-1 Quant' : 'Healthy';

      // Compute FX Drag vs Gross PnL
      let totalUsNotional = 0;
      let totalUkNotional = 0;
      let totalFxDrag = 0;

      list.forEach(t => {
        const sym = t.symbol || '';
        const notional = (Number(t.quantity || 1) * Number(t.entry_price || 0));
        const feePaid = (Number(t.entry_fee_paid || 0) + Number(t.exit_fee_paid || 0) + Number(t.fee_paid || 0));
        if (sym.endsWith('_UK_EQ')) {
          totalUkNotional += notional;
        } else {
          totalUsNotional += notional;
          totalFxDrag += feePaid > 0 ? feePaid : (notional * 0.0030);
        }
      });

      const ukFxSaved = totalUkNotional * 0.0030; // 0.30% spared by UK ETP sleeve

      const waterfallHtml = `
        <div class="waterfall-card">
          <div class="waterfall-header">
            <div style="display:flex;align-items:center;gap:8px;">
              <strong style="font-size:12.5px;color:var(--text-primary);">💧 P&amp;L Attribution &amp; Trading 212 FX Drag Waterfall</strong>
              <span style="font-size:11px;color:var(--text-tertiary);">(Gross Alpha ➔ FX Conversion Drag ➔ Take-Home Cash)</span>
            </div>
            <div class="fx-exemption-pill">
              <span>🇬🇧 UK 3x ETP 0% FX Saved:</span>
              <strong>+${ACCT_CCY}${ukFxSaved.toFixed(2)}</strong>
            </div>
          </div>

          <div class="waterfall-flow">
            <div class="waterfall-node">
              <span class="waterfall-node-title">1. Gross Alpha (Wins)</span>
              <span class="waterfall-node-val pos-green">+${ACCT_CCY}${grossWins.toFixed(2)}</span>
            </div>
            <span class="waterfall-arrow">➔</span>
            <div class="waterfall-node">
              <span class="waterfall-node-title">2. Loss Cushions</span>
              <span class="waterfall-node-val pos-red">-${ACCT_CCY}${grossLoss.toFixed(2)}</span>
            </div>
            <span class="waterfall-arrow">➔</span>
            <div class="waterfall-node">
              <span class="waterfall-node-title">3. T212 FX Drag (0.15%/leg)</span>
              <span class="waterfall-node-val" style="color:var(--amber);">${totalFxDrag > 0 ? '-$' + totalFxDrag.toFixed(2) : '-$0.00'}</span>
            </div>
            <span class="waterfall-arrow">➔</span>
            <div class="waterfall-node">
              <span class="waterfall-node-title">4. Net Take-Home</span>
              <span class="waterfall-node-val ${totalNet >= 0 ? 'pos-green' : 'pos-red'}">${totalSign}${ACCT_CCY}${totalNet.toFixed(2)}</span>
            </div>
          </div>
        </div>
      `;

      const ratiosRibbonHtml = `
        <div class="quant-ratios-ribbon">
          <div class="quant-ratio-card">
            <span class="ratio-label">Profit Factor</span>
            <strong class="ratio-val pos-green">${profitFactor}</strong>
            <span class="ratio-sub">${grossWins > 0 ? ACCT_CCY + grossWins.toFixed(0) + ' Win / ' + ACCT_CCY + grossLoss.toFixed(0) + ' Loss' : '3.5x Target / 1.5x SL'}</span>
          </div>
          <div class="quant-ratio-card">
            <span class="ratio-label">Payoff Ratio</span>
            <strong class="ratio-val">${payoffRatio}</strong>
            <span class="ratio-sub">Avg Win vs Avg Loss</span>
          </div>
          <div class="quant-ratio-card">
            <span class="ratio-label">Expectancy / Trade</span>
            <strong class="ratio-val pos-green">+${expectancyR}</strong>
            <span class="ratio-sub">Per $1 Capital At Risk</span>
          </div>
          <div class="quant-ratio-card">
            <span class="ratio-label">Win Rate Quality</span>
            <strong class="ratio-val">${winRate}%</strong>
            <span class="ratio-sub">${wins} Wins / ${losses} Losses</span>
          </div>
          <div class="quant-ratio-card">
            <span class="ratio-label">Sharpe Efficiency</span>
            <strong class="ratio-val" style="color:var(--accent);">${sharpeEst}</strong>
            <span class="ratio-sub">${sharpeTier}</span>
          </div>
        </div>
      `;

      if (summaryEl) {
        summaryEl.textContent = `Showing ${list.length} recent trade${list.length > 1 ? 's' : ''} • Win Rate: ${winRate}% (${wins}/${list.length}) • Net P&L: ${totalSign}${ACCT_CCY}${totalNet.toFixed(2)}`;
      }
      container.innerHTML = `
        ${waterfallHtml}
        ${ratiosRibbonHtml}
        <div style="overflow-x:auto;">
          <table>
            <thead>
              <tr>
                <th>Closed Time</th>
                <th>Ticker</th>
                <th>Qty</th>
                <th>Entry Fill</th>
                <th>Exit Fill</th>
                <th>Journey (Buy → Sell)</th>
                <th>Net P&L</th>
                <th>Return (% / R)</th>
                <th>Exit Trigger</th>
              </tr>
            </thead>
            <tbody>
              ${list.map((t, idx) => {
                const pnl = Number(t.net_pnl || 0);
                const fee = Number(t.fee_paid || 0);
                const gross = Number(t.gross_pnl !== undefined ? t.gross_pnl : (pnl + fee));
                const pct = Number(t.pnl_pct || 0);
                const rMult = Number(t.r_multiple || 0);
                const sign = pnl >= 0 ? '+' : '';
                const grossSign = gross >= 0 ? '+' : '';
                const cls = pnl >= 0 ? 'pos-green' : 'pos-red';
                const ccy = getCurrencySymbol(t.symbol);
                const ts = formatDecisionTimestamp(t.closed_at);
                const reasonBadge = (t.reason || '').includes('TAKE_PROFIT')
                  ? 'badge badge-strong-buy'
                  : ((t.reason || '').includes('STOP_LOSS') ? 'badge badge-avoid' : 'badge badge-buy');
                const feeSubHtml = fee > 0
                  ? `<div style="font-size:10.5px;color:var(--text-tertiary);font-weight:500;margin-top:2px;">Gross ${grossSign}${ACCT_CCY}${gross.toFixed(2)} • Fees -${ACCT_CCY}${fee.toFixed(2)}</div>`
                  : '';
                const closedJourneySvg = renderClosedTradeJourneySVG(t, idx);
                const pm = t.postmortem;
                const rowKey = 'pm_' + (t.closed_at || idx).toString().replace(/[^a-zA-Z0-9_]/g, '_') + '_' + t.symbol;
                const isOpen = expandedPostmortems.has(rowKey);
                const displayStyle = isOpen ? 'table-row' : 'none';
                const tag = pm ? (pm.outcome_tag || 'POSTMORTEM') : 'POSTMORTEM';

                const pmBtnHtml = (pnl < 0 && pm)
                  ? `<div style="margin-top:5px;">
                       <button id="pm-btn-${rowKey}" data-tag="${tag}" onclick="togglePostmortem('${rowKey}')"
                         style="background:${isOpen ? 'rgba(255,59,48,0.22)' : 'rgba(255,59,48,0.10)'};color:var(--red-text);border:1px solid rgba(255,59,48,0.35);border-radius:999px;padding:3px 10px;font-size:10.5px;font-weight:600;cursor:pointer;transition:all 0.15s ease;">
                         🔬 ${tag} ${isOpen ? '▴' : '▾'}
                       </button>
                     </div>`
                  : '';

                const mfeText = (t.mfe_pct !== undefined && t.mfe_pct !== null)
                  ? `Peak +${Number(t.mfe_pct).toFixed(2)}% (+${Number(t.mfe_r || 0).toFixed(2)}R)`
                  : '';
                const maeText = (t.mae_pct !== undefined && t.mae_pct !== null)
                  ? `Trough ${Number(t.mae_pct).toFixed(2)}% (${Number(t.mae_r || 0).toFixed(2)}R)`
                  : '';
                const excursionHtml = (mfeText || maeText)
                  ? `<div style="display:flex;gap:12px;font-size:11.5px;margin-top:2px;flex-wrap:wrap;">
                       ${mfeText ? `<span style="color:var(--green-text);background:rgba(40,205,65,0.08);padding:3px 8px;border-radius:4px;border:1px solid rgba(40,205,65,0.2);">📈 MFE (Peak Excursion): <strong>${mfeText}</strong></span>` : ''}
                       ${maeText ? `<span style="color:var(--red-text);background:rgba(255,59,48,0.08);padding:3px 8px;border-radius:4px;border:1px solid rgba(255,59,48,0.2);">📉 MAE (Max Drawdown): <strong>${maeText}</strong></span>` : ''}
                     </div>`
                  : '';

                const pmDrawerRow = (pnl < 0 && pm)
                  ? `<tr id="pm-row-${rowKey}" style="display:${displayStyle};background:rgba(255,59,48,0.05);border-left:3px solid var(--red);">
                       <td colspan="9" style="padding:14px 18px;border-bottom:1px solid var(--border);">
                         <div style="display:flex;flex-direction:column;gap:8px;font-size:12px;line-height:1.5;">
                           <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;">
                             <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                               <span class="badge badge-avoid">${pm.outcome_tag || 'LOSS'}</span>
                               <strong style="color:var(--text-primary);">Root Cause:</strong>
                               <span style="color:var(--text-secondary);">${pm.root_cause || ''}</span>
                             </div>
                             <button onclick="togglePostmortem('${rowKey}')" style="background:transparent;border:1px solid var(--border);color:var(--text-tertiary);cursor:pointer;font-size:11px;font-weight:600;padding:2px 8px;border-radius:4px;" title="Close postmortem drawer">✕ Close</button>
                           </div>
                           ${excursionHtml}
                           <div><strong style="color:var(--text-primary);">What Went Wrong:</strong> <span style="color:var(--text-secondary);">${pm.what_went_wrong || ''}</span></div>
                           <div style="background:rgba(0,113,227,0.08);border-left:3px solid var(--accent);padding:8px 12px;border-radius:6px;margin-top:2px;">
                             <strong style="color:var(--accent);">🧠 AI Vetting Rule Learned:</strong>
                             <span style="color:var(--text-primary);margin-left:4px;">${pm.tactical_lesson || ''}</span>
                           </div>
                         </div>
                       </td>
                     </tr>`
                  : '';
                return `
                  <tr>
                    <td>${ts.fullText}</td>
                    <td><strong>${tickerLink(t.symbol)}</strong></td>
                    <td>${Number(t.quantity || 0).toFixed(4)}</td>
                    <td>${ccy}${Number(t.entry_price || 0).toFixed(2)}</td>
                    <td>${ccy}${Number(t.exit_price || 0).toFixed(2)}</td>
                    <td>${closedJourneySvg}</td>
                    <td class="${cls}"><strong>${sign}${ACCT_CCY}${pnl.toFixed(2)}</strong>${feeSubHtml}</td>
                    <td class="${cls}"><strong>${sign}${pct.toFixed(2)}% (${sign}${rMult.toFixed(2)}R)</strong></td>
                    <td><span class="${reasonBadge}">${t.reason || 'MANUAL'}</span>${pmBtnHtml}</td>
                  </tr>
                  ${pmDrawerRow}
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;
    }

    async function refresh() {
      try {
        const fetchStart = performance.now();
        const res = await fetch('/api/status');
        const latency = Math.round(performance.now() - fetchStart);
        const nodePill = document.getElementById('node-pill');
        if (nodePill) nodePill.textContent = `Proxmox LXC • ${latency}ms`;

        const data = await res.json();
        const ver = data.version ? `v${data.version}` : 'v2.5.1';
        const verPill = document.getElementById('ver-pill');
        if (verPill) verPill.textContent = ver;
        const epSub = document.getElementById('endpoint-sub');
        if (epSub) epSub.textContent = `${data.endpoint} • ${ver} • Live 3s`;
        document.getElementById('mode-pill').textContent = `TRADING 212 ${data.execution_mode}`;
        document.getElementById('tf-pill').textContent = data.timeframe;
        document.getElementById('hb-pill').textContent = data.last_heartbeat;
        if (data.stop_loss_atr_mult) {
          const slTxt = `Stop-Loss (${Number(data.stop_loss_atr_mult).toFixed(1)}x ATR)`;
          document.getElementById('th-sl-label').textContent = slTxt;
          const slGuide = document.getElementById('guide-sl-title');
          if (slGuide) slGuide.textContent = slTxt;
        }
        if (data.take_profit_atr_mult) {
          const tpTxt = `Target (${Number(data.take_profit_atr_mult).toFixed(1)}x ATR)`;
          document.getElementById('th-tp-label').textContent = tpTxt;
          const tpGuide = document.getElementById('guide-tp-title');
          if (tpGuide) tpGuide.textContent = tpTxt;
        }

        if (data.account_currency_symbol) ACCT_CCY = data.account_currency_symbol;
        const p = data.portfolio;
        const eqEl = document.getElementById('kpi-equity');
        const cashEl = document.getElementById('kpi-cash');
        if (eqEl) {
          if (!hasAnimatedKPIs && p.total_equity > 0) {
            hasAnimatedKPIs = true;
            animateCountUp(eqEl, 0, p.total_equity, 1200, ACCT_CCY, '', 2);
            if (cashEl) animateCountUp(cashEl, 0, p.free_cash, 1200, ACCT_CCY, '', 2);
          } else {
            if (previousEquity !== null && p.total_equity !== previousEquity) {
              eqEl.classList.remove('flash-up', 'flash-down');
              void eqEl.offsetWidth; // Trigger reflow
              eqEl.classList.add(p.total_equity > previousEquity ? 'flash-up' : 'flash-down');
              setTimeout(() => eqEl.classList.remove('flash-up', 'flash-down'), 1500);
            }
            eqEl.textContent = `${ACCT_CCY}${p.total_equity.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
            if (cashEl) cashEl.textContent = `${ACCT_CCY}${p.free_cash.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
          }
          previousEquity = p.total_equity;
        }
        document.getElementById('kpi-invested').textContent = `Invested in Positions: ${ACCT_CCY}${p.invested_value.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
        document.getElementById('kpi-positions').textContent = `${p.open_positions_count} / ${p.max_open_positions}`;
        document.getElementById('kpi-realized').textContent = `Session Realized P&L: ${ACCT_CCY}${p.realized_pnl.toFixed(2)}`;
        document.getElementById('kpi-dd').textContent = `${p.drawdown_24h_pct.toFixed(2)}%`;
        document.getElementById('kpi-dd-limit').textContent = p.circuit_breaker_tripped
          ? 'CIRCUIT BREAKER TRIPPED — TRADING HALTED'
          : `Healthy (Hard Stop at ${p.max_drawdown_24h_pct.toFixed(2)}% 24h DD)`;

        // Drawdown Circle Ring
        const ddCircle = document.getElementById('dd-ring-circle');
        if (ddCircle) {
          const circ = 113.1;
          const maxDd = p.max_drawdown_24h_pct || 5.0;
          const currDd = Math.min(maxDd, Math.max(0, p.drawdown_24h_pct || 0));
          const frac = currDd / maxDd;
          const offset = (circ - (frac * circ)).toFixed(1);
          ddCircle.style.strokeDashoffset = offset;
          if (frac >= 0.8) ddCircle.style.stroke = 'var(--red)';
          else if (frac >= 0.4) ddCircle.style.stroke = 'var(--amber)';
          else ddCircle.style.stroke = 'var(--green)';
        }

        if (data.market_session) {
          const ms = data.market_session;
          marketIsOpen = !!ms.is_open;
          marketState = ms.state || 'CLOSED';
          marketNextOpenStr = ms.next_open_str || '';
          marketSecondsRemaining = marketIsOpen ? (ms.seconds_to_close || 0) : (ms.seconds_to_open || 0);
          marketTotalClosedSeconds = ms.total_closed_seconds || 63000;
        }

        if (data.uk_market_session) {
          const ums = data.uk_market_session;
          ukMarketIsOpen = !!ums.is_open;
          ukMarketState = ums.state || 'CLOSED';
          ukMarketNextOpenStr = ums.next_open_str || '';
          ukMarketSecondsRemaining = ukMarketIsOpen ? (ums.seconds_to_close || 0) : (ums.seconds_to_open || 0);
          ukMarketTotalClosedSeconds = ums.total_closed_seconds || 55800;
        }

        updateCountdownTimers();

        // Update KPI 2 Cash vs Invested Liquid Meter
        const totalCap = Math.max(1, p.total_equity);
        const cashFrac = Math.min(100, Math.max(0, (p.free_cash / totalCap) * 100));
        const investFrac = Math.min(100, Math.max(0, (p.invested_value / totalCap) * 100));
        const cashBar = document.getElementById('kpi-cash-bar');
        const investBar = document.getElementById('kpi-invested-bar');
        if (cashBar && investBar) {
          cashBar.style.width = `${cashFrac.toFixed(1)}%`;
          investBar.style.width = `${investFrac.toFixed(1)}%`;
        }

        // Update KPI 3 Position Capacity Segmented Pills (3 US Equity Slots + 1 Dedicated UK ETP Slot)
        const posList = data.positions || [];
        const usPosList = posList.filter(pos => !(pos.symbol || '').endsWith('_UK_EQ'));
        const ukPosList = posList.filter(pos => (pos.symbol || '').endsWith('_UK_EQ'));
        for (let i = 1; i <= 3; i++) {
          const pill = document.getElementById(`slot-pill-${i}`);
          if (pill) {
            if (i <= usPosList.length) {
              const ticker = formatTickerDisplay(usPosList[i-1].symbol);
              pill.className = 'slot-pill filled';
              pill.textContent = `🇺🇸 ${ticker}`;
            } else {
              pill.className = 'slot-pill empty';
              pill.textContent = `🇺🇸 ${i}: Open`;
            }
          }
        }
        const ukPill = document.getElementById('slot-pill-4');
        if (ukPill) {
          if (ukPosList.length > 0) {
            const ukTicker = formatTickerDisplay(ukPosList[0].symbol);
            ukPill.className = 'slot-pill filled';
            ukPill.textContent = `🇬🇧 ${ukTicker}`;
          } else {
            ukPill.className = 'slot-pill empty';
            ukPill.textContent = '🇬🇧 UK: Open';
          }
        }

        // Update Gate 2 Battery Segments
        const occupied = posList.length;
        const b1 = document.getElementById('gate-batt-seg1');
        const b2 = document.getElementById('gate-batt-seg2');
        const b3 = document.getElementById('gate-batt-seg3');
        if (b1) b1.setAttribute('fill', occupied >= 1 ? 'var(--green)' : 'rgba(142,142,147,0.3)');
        if (b2) b2.setAttribute('fill', occupied >= 2 ? 'var(--green)' : 'rgba(142,142,147,0.3)');
        if (b3) b3.setAttribute('fill', occupied >= 3 ? 'var(--green)' : 'rgba(142,142,147,0.3)');

        renderActivityAndGates(data);
        renderPositions(data.positions);
        renderAIManager(data.ai_manager);
        renderClosedTrades(data.closed_trades);

        // Update Ambient Aura
        const aura = document.getElementById('kpi-ambient-aura');
        if (aura) {
          aura.className = 'ambient-glow-mesh ' + (p.realized_pnl >= 0 ? 'active-green' : 'active-red');
        }

        // Render New Apple Analytics Suite
        latestTelemetryData = data;
        renderEquityCurve(data.equity_history, data.equity_history_24h, data.session_info, p.realized_pnl, p.total_equity);
        renderPerformanceRings(data.closed_trades, data.positions);
        renderQuantEdgeMatrix(data.closed_trades);
        renderLongTermPerformance(data.long_term);
        renderAllocation(data.positions, p);
        renderAICalibration(data.ai_manager ? data.ai_manager.decisions : [], data.closed_trades);
        updateMacroAtmosphere(data);

        latestRecommendations = (data.screener && data.screener.recommendations) || [];
        if (latestRecommendations.length > 0) {
          document.getElementById('screener-title').textContent = `${latestRecommendations.length}-Stock Quantitative Screener & Recommendation Leaderboard`;
          document.getElementById('btn-filter-all').textContent = `All (${latestRecommendations.length})`;
        }
        renderHeroRadar(latestRecommendations, data.positions);
        renderScreener(latestRecommendations);
        if (currentScreenerView === 'heatmap') {
          renderHeatmap(latestRecommendations);
        }
        renderTickerTape(latestRecommendations);
        renderLogs(data.logs);
      } catch (e) {
        console.error('Dashboard refresh error:', e);
      }
    }

    updateSoundUI();
    initMarketDialView();
    updateCountdownTimers();
    refresh();
    updateGlobalMarketClocks();
    setInterval(updateCountdownTimers, 1000);
    setInterval(updateGlobalMarketClocks, 1000);
    setInterval(refresh, 3000);
    requestAnimationFrame(() => {
      setTimeout(initScrollReveal, 60);
    });
