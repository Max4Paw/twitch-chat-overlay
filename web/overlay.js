/* ChatStyle — общий рендерер чата для OBS Browser Source и редактора.
 * Стиль хранится как JSON (см. DEFAULTS), превращается в CSS + DOM. */
(function () {
  "use strict";

  const PLATE = {
    type: "color",          // none | color | gradient | image
    color: "#0e0f1a", opacity: 0.72,
    color2: "#3a1f6e", angle: 135,
    tint: 0,                // 0..1 — подмешать цвет ника в фон
    radius: 12,
    borderW: 0, borderColor: "#ffffff", borderOp: 0.10,
    shadow: 14, shadowColor: "#000000", shadowOp: 0.35,
    blur: 0,                // backdrop blur, px
    padX: 14, padY: 8,
    accent: "none",         // none | left | bottom | glow (только для сообщения)
    accentW: 4, accentMode: "nick", accentColor: "#9146ff",
    image: "",              // url
    imgMode: "slice",       // slice | stretch | cover | tile
    slice: [24, 24, 24, 24],// top right bottom left (px исходной картинки)
    sliceScale: 1,
    imgRepeat: "stretch",   // stretch | round | repeat (для 9-slice)
    imgOpacity: 1,
    hue: 0,
  };

  const DEFAULTS = {
    layout: {
      align: "bottom",      // bottom | top
      hAlign: "left",       // left | right
      width: "fit",         // fit | full
      stacked: false,       // ник над текстом
      gap: 8, pad: 12, max: 40,
      lifetime: 0,          // сек, 0 = не скрывать
      anim: "slide-left", animMs: 360,
      showTime: false, showBadges: true, showPlatform: false,
      sep: ":", emote: 1.6,
    },
    text: {
      font: "Montserrat", size: 18, weight: 500, color: "#ffffff",
      lineHeight: 1.35, shadow: "soft", shadowColor: "#000000",
    },
    nick: { colorMode: "twitch", color: "#bf94ff", weight: 800, upper: false },
    plate: Object.assign({}, PLATE),
    nickPlate: Object.assign({}, PLATE, {
      type: "none", radius: 6, padX: 7, padY: 1, shadow: 0, opacity: 0.9, tint: 1,
    }),
    hl: { enabled: true, color: "#ffb347" },
    roles: {
      broadcaster: { enabled: true,  color: "#e91916", plate: true, opacity: 0.85, border: true, nick: false },
      moderator:   { enabled: false, color: "#00ad03", plate: false, opacity: 0.85, border: true, nick: false },
      vip:         { enabled: false, color: "#e005b9", plate: false, opacity: 0.85, border: true, nick: false },
    },
    featured: { scale: 1.6, duration: 15, position: "bottom" },
    events: {
      enabled: true,        // показывать сабки/гифты/рейды/битсы
      frame: true,          // рамка и свечение цветом события
      big: true,            // заголовок события крупнее текста
      colors: { sub: "#a970ff", gift: "#ff6bcb", raid: "#ff9f1c",
                cheer: "#f5c518", announcement: "#4fc3f7", other: "#8b91a7" },
    },
  };

  const P = (o) => o;  // для читаемости пресетов
  const PRESETS = {
    glass: {
      name: "Стекло",
      style: P({
        text: { font: "Montserrat", weight: 500 },
        plate: { type: "color", color: "#14162a", opacity: 0.55, blur: 10, radius: 14,
                 borderW: 1, borderColor: "#ffffff", borderOp: 0.14, shadow: 20, shadowOp: 0.3,
                 accent: "none", tint: 0.18 },
      }),
    },
    cards: {
      name: "Карточки",
      style: P({
        text: { font: "Inter", weight: 500 },
        plate: { type: "color", color: "#0e0f1a", opacity: 0.85, radius: 8, accent: "left",
                 accentW: 4, accentMode: "nick", shadow: 12, shadowOp: 0.4, borderW: 0 },
      }),
    },
    neon: {
      name: "Неон",
      style: P({
        text: { font: "Exo 2", weight: 600, shadow: "glow", shadowColor: "#9146ff" },
        plate: { type: "color", color: "#090614", opacity: 0.8, radius: 10, borderW: 2,
                 borderColor: "#a970ff", borderOp: 0.9, accent: "glow", accentMode: "nick",
                 accentW: 8, shadow: 0 },
      }),
    },
    gradient: {
      name: "Градиент",
      style: P({
        text: { font: "Nunito", weight: 700 },
        plate: { type: "gradient", color: "#6a2cff", color2: "#ff4f8b", angle: 120,
                 opacity: 0.88, radius: 18, shadow: 18, shadowOp: 0.35, accent: "none" },
      }),
    },
    bubbles: {
      name: "Пузыри",
      style: P({
        layout: { stacked: true },
        text: { font: "Rubik", weight: 500, shadow: "none" },
        nick: { weight: 700 },
        plate: { type: "color", color: "#ffffff", opacity: 0.95, radius: 18, shadow: 10,
                 shadowOp: 0.25, accent: "none", tint: 0 },
        nickPlate: { type: "color", opacity: 1, tint: 1, radius: 999, padX: 10, padY: 2 },
      }),
      after: (s) => { s.text.color = "#1b1d2a"; s.nick.colorMode = "fixed"; s.nick.color = "#ffffff"; },
    },
    tags: {
      name: "Ник-плашки",
      style: P({
        text: { font: "Montserrat", weight: 600, shadow: "outline" },
        layout: { sep: "" },
        plate: { type: "none", padX: 4, padY: 2 },
        nickPlate: { type: "color", tint: 1, opacity: 0.95, radius: 6, padX: 8, padY: 1 },
      }),
      after: (s) => { s.nick.colorMode = "fixed"; s.nick.color = "#ffffff"; },
    },
    minimal: {
      name: "Минимал",
      style: P({
        text: { font: "Segoe UI", weight: 600, shadow: "outline" },
        plate: { type: "none", padX: 2, padY: 1 },
      }),
    },
    pixel: {
      name: "Пиксель",
      style: P({
        text: { font: "Press Start 2P", size: 12, weight: 400, lineHeight: 1.7, shadow: "hard" },
        nick: { weight: 400 },
        plate: { type: "color", color: "#1a1030", opacity: 0.92, radius: 0, borderW: 3,
                 borderColor: "#ffffff", borderOp: 1, shadow: 0, accent: "none", padX: 12, padY: 10 },
      }),
    },
  };

  const GOOGLE_FONTS = {
    "Montserrat": "400;500;600;700;800;900",
    "Inter": "400;500;600;700;800",
    "Roboto": "400;500;700;900",
    "Nunito": "400;600;700;800;900",
    "Rubik": "400;500;600;700;800",
    "Exo 2": "400;500;600;700;800",
    "Comfortaa": "400;500;600;700",
    "Ubuntu": "400;500;700",
    "Oswald": "400;500;600;700",
    "Unbounded": "400;500;600;700;800",
    "JetBrains Mono": "400;500;700;800",
    "Caveat": "400;500;600;700",
    "Russo One": "400",
    "Press Start 2P": "400",
    "Lobster": "400",
  };
  const SYSTEM_FONTS = ["Segoe UI", "Arial", "Verdana", "Tahoma", "Trebuchet MS", "Georgia", "Consolas", "Impact"];

  const NICK_COLORS = ["#ff7b72", "#ffa657", "#ffd93d", "#7ee787", "#56d4dd", "#79c0ff",
                       "#d2a8ff", "#ff9ec1", "#ff8a65", "#aed581", "#80deea", "#ce93d8"];

  // ---------- утилиты ----------
  function isObj(v) { return v && typeof v === "object" && !Array.isArray(v); }
  function deepMerge(base, over) {
    const out = Array.isArray(base) ? base.slice() : Object.assign({}, base);
    if (!isObj(over)) return out;
    for (const k of Object.keys(over)) {
      if (k.startsWith("_")) continue;
      if (isObj(out[k]) && isObj(over[k])) out[k] = deepMerge(out[k], over[k]);
      else if (over[k] !== undefined) out[k] = Array.isArray(over[k]) ? over[k].slice() : over[k];
    }
    return out;
  }
  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function normalize(style) { return deepMerge(clone(DEFAULTS), style || {}); }
  function fromPreset(key) {
    const p = PRESETS[key];
    if (!p) return clone(DEFAULTS);
    const s = deepMerge(clone(DEFAULTS), clone(p.style));
    if (p.after) p.after(s);
    return s;
  }

  function hexRgb(h) {
    h = String(h || "").trim().replace("#", "");
    if (h.length === 3) h = h.split("").map((c) => c + c).join("");
    const n = parseInt(h.slice(0, 6), 16);
    if (isNaN(n)) return [255, 255, 255];
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function mix(a, b, t) { return a.map((v, i) => Math.round(v + (b[i] - v) * t)); }
  function rgba(rgb, a) { return `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${(+a).toFixed(3)})`; }
  function num(v, d) { v = Number(v); return isFinite(v) ? v : d; }
  function cssUrl(u) { return 'url("' + String(u).replace(/["\\\n\r]/g, "") + '")'; }
  function cssStr(s) { return '"' + String(s).replace(/["\\\n\r<>]/g, "") + '"'; }

  function nickColorHash(nick) {
    let s = 0;
    for (let i = 0; i < nick.length; i++) s = (s * 31 + nick.charCodeAt(i)) >>> 0;
    return NICK_COLORS[s % NICK_COLORS.length];
  }
  // Слишком тёмные ники Twitch подсветляем, чтобы читались на тёмных плашках
  function readableNick(hex) {
    const c = hexRgb(hex);
    const lum = (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255;
    if (lum < 0.35) return "#" + mix(c, [255, 255, 255], 0.45).map((v) => v.toString(16).padStart(2, "0")).join("");
    return hex;
  }

  const loadedFonts = new Set();
  function ensureFont(name, doc) {
    doc = doc || document;
    if (!GOOGLE_FONTS[name] || loadedFonts.has(name)) return;
    loadedFonts.add(name);
    const l = doc.createElement("link");
    l.rel = "stylesheet";
    l.href = "https://fonts.googleapis.com/css2?family=" + encodeURIComponent(name).replace(/%20/g, "+") +
      ":wght@" + GOOGLE_FONTS[name] + "&display=swap";
    doc.head.appendChild(l);
  }

  // ---------- CSS ----------
  function textShadow(kind, color) {
    const c = hexRgb(color);
    switch (kind) {
      case "soft": return `0 1px 2px ${rgba(c, .85)}, 0 0 6px ${rgba(c, .45)}`;
      case "outline": {
        const a = rgba(c, .95), b = [];
        for (const [x, y] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[-1,-1],[1,-1],[-1,1]]) b.push(`${x}px ${y}px 0 ${a}`);
        b.push(`0 0 4px ${rgba(c, .6)}`);
        return b.join(", ");
      }
      case "hard": return `2px 2px 0 ${rgba(c, .95)}`;
      case "glow": return `0 0 6px ${rgba(c, .9)}, 0 0 14px ${rgba(c, .6)}`;
      default: return "none";
    }
  }

  // CSS для слоя .bg внутри sel (sel > .bg)
  function plateCSS(sel, p, isMsg) {
    const r = [];
    const bg = `${sel} > .bg`;
    if (p.type === "none") {
      r.push(`${bg}{display:none}`);
      r.push(`${sel}{padding:${num(p.padY,0)}px ${num(p.padX,0)}px}`);
      return r.join("\n");
    }
    const rad = num(p.radius, 0);
    const props = [`border-radius:${rad}px`];
    const shadows = [];
    const filters = [];
    const isImg = p.type === "image" && p.image;

    if (isImg) {
      props.push(`opacity:${num(p.imgOpacity, 1)}`);
      if (p.imgMode === "slice") {
        const s = (p.slice || [0, 0, 0, 0]).map((v) => Math.max(0, num(v, 0)));
        const k = num(p.sliceScale, 1);
        const w = s.map((v) => Math.round(v * k) + "px").join(" ");
        props.push(`border-style:solid`, `border-color:transparent`, `border-width:${w}`,
          `border-image-source:${cssUrl(p.image)}`, `border-image-slice:${s.join(" ")} fill`,
          `border-image-width:${w}`, `border-image-repeat:${p.imgRepeat || "stretch"}`,
          `border-radius:0`);
      } else {
        const size = p.imgMode === "cover" ? "cover" : p.imgMode === "tile" ? "auto" : "100% 100%";
        const rep = p.imgMode === "tile" ? "repeat" : "no-repeat";
        props.push(`background:${cssUrl(p.image)} center / ${size} ${rep}`);
      }
      if (num(p.shadow, 0) > 0)
        filters.push(`drop-shadow(0 ${Math.round(p.shadow / 4)}px ${Math.round(p.shadow / 2)}px ${rgba(hexRgb(p.shadowColor), p.shadowOp)})`);
      if (num(p.hue, 0)) filters.push(`hue-rotate(${num(p.hue, 0)}deg)`);
    } else {
      // цвет/градиент берём из CSS-переменных — они считаются на каждое сообщение (tint)
      const v = isMsg ? "--pb" : "--npb";
      if (p.type === "gradient") props.push(`background:linear-gradient(${num(p.angle,135)}deg, var(${v}1), var(${v}2))`);
      else props.push(`background:var(${v}1)`);
      if (num(p.borderW, 0) > 0)
        props.push(`border:${num(p.borderW,0)}px solid ${rgba(hexRgb(p.borderColor), num(p.borderOp,1))}`);
      if (num(p.shadow, 0) > 0)
        shadows.push(`0 ${Math.round(p.shadow / 4)}px ${p.shadow}px ${rgba(hexRgb(p.shadowColor), num(p.shadowOp, .3))}`);
      if (num(p.blur, 0) > 0) props.push(`backdrop-filter:blur(${p.blur}px)`, `-webkit-backdrop-filter:blur(${p.blur}px)`);
    }

    if (isMsg && p.accent === "glow")
      shadows.push(`0 0 ${num(p.accentW, 6) * 2}px var(--acg)`);
    if (shadows.length) props.push(`box-shadow:${shadows.join(", ")}`);
    if (filters.length) props.push(`filter:${filters.join(" ")}`);
    r.push(`${bg}{${props.join(";")}}`);
    r.push(`${sel}{padding:${num(p.padY,0)}px ${num(p.padX,0)}px}`);

    if (isMsg && (p.accent === "left" || p.accent === "bottom")) {
      const w = num(p.accentW, 4);
      const pos = p.accent === "left"
        ? `left:0;top:0;bottom:0;width:${w}px;border-radius:${rad}px 0 0 ${rad}px`
        : `left:0;right:0;bottom:0;height:${w}px;border-radius:0 0 ${rad}px ${rad}px`;
      r.push(`${sel} > .ac{display:block;position:absolute;${pos};background:var(--ac);z-index:-1}`);
      if (p.accent === "left") r.push(`${sel}{padding-left:${num(p.padX,0) + w}px}`);
      else r.push(`${sel}{padding-bottom:${num(p.padY,0) + w}px}`);
    }
    return r.join("\n");
  }

  function buildCSS(s) {
    const L = s.layout, T = s.text, N = s.nick;
    const fontStack = `${cssStr(T.font)}, "Segoe UI", system-ui, Arial, sans-serif`;
    const css = [];
    css.push(`#chat{position:fixed;inset:0;box-sizing:border-box;padding:${num(L.pad,12)}px;display:flex;flex-direction:column;` +
      `justify-content:${L.align === "top" ? "flex-start" : "flex-end"};` +
      `align-items:${L.width === "full" ? "stretch" : (L.hAlign === "right" ? "flex-end" : "flex-start")};` +
      `gap:${num(L.gap,8)}px;overflow:hidden}`);
    css.push(`.msg{position:relative;isolation:isolate;box-sizing:border-box;max-width:100%;` +
      `font-family:${fontStack};font-size:${num(T.size,18)}px;font-weight:${T.weight};line-height:${num(T.lineHeight,1.35)};` +
      `color:${T.color};text-shadow:${textShadow(T.shadow, T.shadowColor)};overflow-wrap:anywhere;` +
      `text-align:${L.hAlign === "right" && L.width !== "full" ? "right" : "left"};` +
      `--anim:${num(L.animMs,360)}ms}`);
    css.push(`.nick{font-weight:${N.weight};${N.upper ? "text-transform:uppercase;letter-spacing:.03em;" : ""}color:var(--nn)}`);
    css.push(`.head{display:${L.stacked ? "flex" : "inline"};align-items:center;gap:.35em;${L.stacked ? "margin-bottom:.2em;" : ""}}`);
    css.push(`.text{display:${L.stacked ? "block" : "inline"}}`);
    css.push(`.time{display:${L.showTime ? "inline" : "none"}}`);
    css.push(`.badges{display:${L.showBadges ? "inline-flex" : "none"}}`);
    css.push(`.plat{display:${L.showPlatform ? "inline-flex" : "none"}}`);
    css.push(`.text img.emo{height:${num(L.emote,1.6)}em}`);
    css.push(plateCSS(".msg", s.plate, true));
    css.push(plateCSS(".nick", s.nickPlate, false));
    if (s.nickPlate.type === "none") css.push(`.nick{padding:0}`);
    const E = s.events || {};
    css.push(`.msg .evh{display:none}`);
    css.push(`.msg.ev .evh{display:flex;align-items:center;gap:.45em;font-weight:800;color:var(--ev);` +
      `${E.big ? "font-size:1.08em;" : ""}margin-bottom:.15em}`);
    css.push(`.msg.ev.nomsg .head,.msg.ev.nomsg .text{display:none}`);
    css.push(`.msg.ev.nomsg .evh{margin-bottom:0}`);
    if (E.frame) {
      if (s.plate.type === "none") css.push(`.msg.ev .evh{text-shadow:0 0 10px var(--evg)}`);
      else if (s.plate.type === "image") css.push(`.msg.ev > .bg{filter:drop-shadow(0 0 3px var(--ev)) drop-shadow(0 0 10px var(--evg))}`);
      else css.push(`.msg.ev > .bg{box-shadow:inset 0 0 0 2px var(--ev), 0 0 20px var(--evg)}`);
    }
    if (s.plate.type === "image") css.push(`.msg.role.rb > .bg{filter:drop-shadow(0 0 2px var(--rc)) drop-shadow(0 0 8px var(--rcg))}`);
    else if (s.plate.type !== "none") css.push(`.msg.role.rb > .bg{box-shadow:inset 0 0 0 2px var(--rc), 0 0 14px var(--rcg)}`);
    else css.push(`.msg.role.rb .nick{text-shadow:0 0 8px var(--rcg)}`);
    if (s.hl && s.hl.enabled) {
      const h = hexRgb(s.hl.color);
      if (s.plate.type === "none") css.push(`.msg.hl .text{color:${s.hl.color}}`);
      else if (s.plate.type === "image") css.push(`.msg.hl > .bg{filter:drop-shadow(0 0 3px ${rgba(h,1)}) drop-shadow(0 0 10px ${rgba(h,.7)})${num(s.plate.hue,0) ? ` hue-rotate(${num(s.plate.hue,0)}deg)` : ""}}`);
      else css.push(`.msg.hl > .bg{box-shadow:inset 0 0 0 2px ${rgba(h,1)}, 0 0 18px ${rgba(h,.45)}}`);
    }
    return css.join("\n");
  }

  const BASE_CSS = `
  html,body{margin:0;height:100%;background:transparent;overflow:hidden}
  .msg>.bg{position:absolute;inset:0;z-index:-2;box-sizing:border-box;pointer-events:none}
  .msg>.ac{display:none}
  .nick{position:relative;isolation:isolate;display:inline-block;box-sizing:border-box;line-height:1.25}
  .nick>.bg{position:absolute;inset:0;z-index:-1;box-sizing:border-box}
  .head{vertical-align:baseline}
  .head>*{vertical-align:middle}
  .sep{margin-right:.3em;opacity:.75}
  .head:not(:empty){margin-right:.15em}
  .time{opacity:.6;font-size:.78em;font-weight:500;margin-right:.35em}
  .badges,.plat{gap:.2em;margin-right:.3em;vertical-align:-.12em}
  .badge{width:1.05em;height:1.05em;border-radius:.22em;display:inline-flex;align-items:center;justify-content:center}
  .badge svg{width:.78em;height:.78em;fill:#fff}
  .text img.emo{vertical-align:middle;margin:-.25em .05em}
  .evh .evi{display:inline-flex;align-items:center;justify-content:center;width:1.35em;height:1.35em;border-radius:.35em;background:var(--ev);color:#fff;font-size:.8em}
  .msg{animation:in-fade var(--anim) cubic-bezier(.2,.8,.2,1) both}
  .msg.a-none{animation:none}
  .msg.a-slide-left{animation-name:in-left}
  .msg.a-slide-right{animation-name:in-right}
  .msg.a-slide-up{animation-name:in-up}
  .msg.a-pop{animation-name:in-pop;animation-timing-function:cubic-bezier(.3,1.5,.5,1)}
  .msg.out{animation:out-fade var(--anim) ease both}
  @keyframes in-fade{from{opacity:0}to{opacity:1}}
  @keyframes in-left{from{opacity:0;transform:translateX(-40px)}to{opacity:1;transform:none}}
  @keyframes in-right{from{opacity:0;transform:translateX(40px)}to{opacity:1;transform:none}}
  @keyframes in-up{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:none}}
  @keyframes in-pop{from{opacity:0;transform:scale(.7)}to{opacity:1;transform:none}}
  @keyframes out-fade{from{opacity:1}to{opacity:0;transform:translateY(-6px)}}
  `;

  const EV_ICONS = { sub: "★", gift: "🎁", raid: "⚑", cheer: "◆", announcement: "📣", other: "•" };

  const BADGES = {
    broadcaster: ["#e91916", '<path d="M3 6h12v12H3zM16 10l5-3v10l-5-3z"/>'],
    moderator: ["#00ad03", '<path d="M14 3l7 7-3 3-2-2-6 6 1 1-2 2-5-5 2-2 1 1 6-6-2-2z"/>'],
    vip: ["#e005b9", '<path d="M12 3l8 7-8 11L4 10z"/>'],
    subscriber: ["#8205b4", '<path d="M12 2l3 6.5 7 .8-5.2 4.8 1.4 7L12 17.6 5.8 21l1.4-7L2 9.3l7-.8z"/>'],
    founder: ["#c99b2a", '<path d="M12 2l3 6.5 7 .8-5.2 4.8 1.4 7L12 17.6 5.8 21l1.4-7L2 9.3l7-.8z"/>'],
    partner: ["#9146ff", '<path d="M9 16.2L4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"/>'],
  };
  const PLATS = {
    twitch: ["#9146ff", '<path d="M5 3L3 7v12h5v3h3l3-3h4l4-4V3zm15 11l-3 3h-4l-3 3v-3H6V5h14zM15 8h2v5h-2zm-5 0h2v5h-2z"/>'],
    youtube: ["#ff0000", '<path d="M9 7.5v9l8-4.5z"/>'],
  };
  function badgeEl(doc, color, path) {
    const b = doc.createElement("span");
    b.className = "badge";
    b.style.background = color;
    b.innerHTML = '<svg viewBox="0 0 24 24">' + path + "</svg>";
    return b;
  }

  // id: Twitch-число или '7tv:ID' / 'bttv:ID' / 'ffz:ID'
  function emoteUrl(id) {
    const enc = (x) => encodeURIComponent(x);
    if (id.startsWith("7tv:")) return "https://cdn.7tv.app/emote/" + enc(id.slice(4)) + "/2x.webp";
    if (id.startsWith("bttv:")) return "https://cdn.betterttv.net/emote/" + enc(id.slice(5)) + "/2x";
    if (id.startsWith("ffz:")) return "https://cdn.frankerfacez.com/emote/" + enc(id.slice(4)) + "/2";
    return "https://static-cdn.jtvnw.net/emoticons/v2/" + enc(id) + "/default/dark/2.0";
  }

  // Рендер текста с эмоутами: emotes = [[start, end, id], ...] в кодовых точках
  function renderText(el, msg, emotes, doc) {
    if (!Array.isArray(emotes) || !emotes.length) { el.textContent = msg; return; }
    const cps = Array.from(msg);
    const parts = emotes.slice().sort((x, y) => x[0] - y[0]);
    let pos = 0;
    for (const e of parts) {
      const a = Number(e[0]), b = Number(e[1]), id = String(e[2] || "");
      if (!id || a < pos || a > b || b >= cps.length) continue;
      if (a > pos) el.appendChild(doc.createTextNode(cps.slice(pos, a).join("")));
      const img = doc.createElement("img");
      img.className = "emo";
      img.alt = img.title = cps.slice(a, b + 1).join("");
      img.src = emoteUrl(id);
      img.onerror = () => { img.replaceWith(doc.createTextNode(img.alt)); };
      el.appendChild(img);
      pos = b + 1;
    }
    if (pos < cps.length) el.appendChild(doc.createTextNode(cps.slice(pos).join("")));
  }

  // ---------- Рендерер ----------
  function Renderer(container, opts) {
    opts = opts || {};
    const doc = container.ownerDocument;
    const baseStyle = doc.createElement("style");
    baseStyle.textContent = BASE_CSS;
    const dynStyle = doc.createElement("style");
    doc.head.append(baseStyle, dynStyle);
    let style = normalize({});
    const timers = new WeakMap();

    function plateVars(el, p, prefix, nc) {
      if (p.type !== "color" && p.type !== "gradient") return;
      const t = Math.max(0, Math.min(1, num(p.tint, 0)));
      const ncr = hexRgb(nc);
      const c1 = mix(hexRgb(p.color), ncr, t);
      const c2 = mix(hexRgb(p.color2), ncr, t);
      el.style.setProperty(prefix + "1", rgba(c1, num(p.opacity, 1)));
      el.style.setProperty(prefix + "2", rgba(c2, num(p.opacity, 1)));
    }

    const ROLE_ORDER = ["broadcaster", "moderator", "vip"];
    function applyRole(m, nc) {
      const badges = (m.dataset.badges || "").split(",");
      const R = style.roles || {};
      m.classList.remove("role", "rb");
      let role = null;
      for (const r of ROLE_ORDER) if (badges.includes(r) && R[r] && R[r].enabled) { role = r; break; }
      if (!role) return;
      const cfg = R[role];
      const rc = cfg.color || "#ffffff";
      m.classList.add("role");
      if (cfg.border) m.classList.add("rb");
      m.style.setProperty("--rc", rc);
      m.style.setProperty("--rcg", rgba(hexRgb(rc), .55));
      if (cfg.nick) m.style.setProperty("--nn", rc);
      const P = style.plate;
      if (cfg.plate && (P.type === "color" || P.type === "gradient")) {
        const op = num(cfg.opacity, 0.85);
        m.style.setProperty("--pb1", rgba(mix(hexRgb(P.color), hexRgb(rc), 0.55), op));
        m.style.setProperty("--pb2", rgba(mix(hexRgb(P.color2), hexRgb(rc), 0.55), op));
      }
    }

    function colorFor(p) {
      const twitch = style.nick.colorMode !== "hash" && p.color && /^#[0-9a-f]{6}$/i.test(p.color)
        ? readableNick(p.color) : null;
      return twitch || nickColorHash(p.user || "");
    }

    function trim() {
      const max = Math.max(1, num(style.layout.max, 40));
      while (container.children.length > max) container.removeChild(container.firstChild);
      // в режиме «сверху» удаляем то, что не помещается снизу
      if (style.layout.align === "top") {
        let guard = 200;
        while (guard-- > 0 && container.children.length > 1 && container.scrollHeight > container.clientHeight + 1)
          container.removeChild(container.firstChild);
      }
    }

    function add(p) {
      if (!p || p.kind !== "msg") return null;
      const L = style.layout;
      const nc = colorFor(p);
      const nn = style.nick.colorMode === "fixed" ? style.nick.color : nc;
      const ac = style.plate.accentMode === "fixed" ? style.plate.accentColor : nc;

      const ev = p.event && style.events && style.events.enabled ? p.event : null;
      if (p.event && !ev && !(p.msg || "").trim()) return null;   // события выключены
      const m = doc.createElement("div");
      m.className = "msg a-" + (L.anim || "fade") + (p.hl ? " hl" : "") +
        (ev ? " ev ev-" + (ev.type || "other") + ((p.msg || "").trim() ? "" : " nomsg") : "");
      if (p.mid) m.dataset.mid = p.mid;
      m.dataset.login = (p.login || p.user || "").toLowerCase();
      m.dataset.badges = (p.badges || []).join(",");
      if (ev) {
        const ec = (style.events.colors || {})[ev.type] || style.events.colors.other || "#8b91a7";
        m.style.setProperty("--ev", ec);
        m.style.setProperty("--evg", rgba(hexRgb(ec), .55));
      }
      m.style.setProperty("--nc", nc);
      m.style.setProperty("--nn", nn);
      m.style.setProperty("--ac", ac);
      m.style.setProperty("--acg", rgba(hexRgb(ac), .65));
      plateVars(m, style.plate, "--pb", nc);
      plateVars(m, style.nickPlate, "--npb", nc);
      applyRole(m, nc);

      const bg = doc.createElement("div"); bg.className = "bg";
      const acEl = doc.createElement("div"); acEl.className = "ac";
      const head = doc.createElement("span"); head.className = "head";

      const time = doc.createElement("span"); time.className = "time";
      time.textContent = (p.ts || "").slice(0, 5);
      const plat = doc.createElement("span"); plat.className = "plat";
      const pl = PLATS[p.platform || "twitch"];
      if (pl) plat.appendChild(badgeEl(doc, pl[0], pl[1]));
      const badges = doc.createElement("span"); badges.className = "badges";
      (p.badges || []).forEach((b) => { const d = BADGES[b]; if (d) badges.appendChild(badgeEl(doc, d[0], d[1])); });
      if (!badges.childNodes.length) badges.style.display = "none";

      const nick = doc.createElement("span"); nick.className = "nick";
      const nbg = doc.createElement("span"); nbg.className = "bg";
      const nname = doc.createElement("span"); nname.textContent = p.user || "";
      nick.append(nbg, nname);
      head.append(time, plat, badges, nick);
      if (L.sep && !L.stacked) {
        const sep = doc.createElement("span"); sep.className = "sep"; sep.textContent = L.sep;
        head.appendChild(sep);
      } else if (!L.stacked) {
        head.appendChild(doc.createTextNode(" "));
      }

      const text = doc.createElement("span"); text.className = "text";
      renderText(text, p.msg || "", p.emotes, doc);

      const evh = doc.createElement("div"); evh.className = "evh";
      if (ev) {
        const ic = doc.createElement("span"); ic.className = "evi";
        ic.textContent = EV_ICONS[ev.type] || "•";
        const et = doc.createElement("span"); et.textContent = ev.text || "";
        evh.append(ic, et);
      }
      m.append(bg, acEl, evh, head, text);
      container.appendChild(m);
      trim();

      const life = num(L.lifetime, 0);
      if (life > 0) {
        timers.set(m, setTimeout(() => {
          m.classList.add("out");
          setTimeout(() => m.remove(), num(L.animMs, 360) + 40);
        }, life * 1000));
      }
      return m;
    }

    function setStyle(s) {
      style = normalize(s);
      ensureFont(style.text.font, doc);
      dynStyle.textContent = buildCSS(style);
      // перекрашиваем уже показанные сообщения (tint/accent зависят от стиля)
      for (const m of Array.from(container.children)) {
        const nc = m.style.getPropertyValue("--nc") || "#ffffff";
        m.style.setProperty("--nn", style.nick.colorMode === "fixed" ? style.nick.color : nc);
        const ac = style.plate.accentMode === "fixed" ? style.plate.accentColor : nc;
        m.style.setProperty("--ac", ac);
        m.style.setProperty("--acg", rgba(hexRgb(ac), .65));
        plateVars(m, style.plate, "--pb", nc);
        plateVars(m, style.nickPlate, "--npb", nc);
        applyRole(m, nc);
        m.className = m.className.replace(/\ba-[\w-]+/, "a-none");
        const evType = (m.className.match(/\bev-(\w+)/) || [])[1];
        if (evType) {
          const ec = (style.events.colors || {})[evType] || "#8b91a7";
          m.style.setProperty("--ev", ec);
          m.style.setProperty("--evg", rgba(hexRgb(ec), .55));
        }
        const head = m.querySelector(".head");
        const sep = head && head.querySelector(".sep");
        if (sep) sep.textContent = style.layout.sep || "";
      }
      trim();
    }

    function clear() { container.textContent = ""; }
    function removeWhere(fn) {
      for (const m of Array.from(container.children)) if (fn(m)) m.remove();
    }
    function remove(mid) { if (mid) removeWhere((m) => m.dataset.mid === mid); }
    function removeUser(login) {
      login = String(login || "").toLowerCase();
      if (login) removeWhere((m) => m.dataset.login === login && !m.classList.contains("ev"));
    }
    setStyle({});
    return { add, setStyle, clear, remove, removeUser, get style() { return style; } };
  }

  // ---------- Демо-сообщения ----------
  const DEMO = [
    { user: "FoxBlade", color: "#ff7f50", badges: ["broadcaster"], msg: "Всем привет! Сегодня проходим финального босса 🔥" },
    { user: "night_owl", color: "#1e90ff", badges: ["moderator"], msg: "Kappa удачи на стриме", emotes: [[0, 4, "25"]] },
    { user: "Мурзик", color: "", badges: ["subscriber"], msg: "а можно ещё раз тот момент? это было легендарно" },
    { user: "pixelpanda", color: "#9acd32", badges: ["vip"], msg: "GG WP" },
    { user: "lena_draws", color: "#ff69b4", badges: ["subscriber"], msg: "нарисовала фанарт, кину в дискорд :)", emotes: [[34, 35, "1"]] },
    { user: "TheRealDmitry", color: "#daa520", badges: [], msg: "первый раз на стриме, очень уютно тут" },
    { user: "kot_v_sapogah", color: "#8a2be2", badges: ["founder"], msg: "это сообщение подлиннее, чтобы посмотреть как плашка растягивается на несколько строк текста и не ломается" },
    { user: "sam", color: "#00ff7f", badges: [], msg: "LUL", hl: true },
    { user: "lena_draws", color: "#ff69b4", badges: ["subscriber"], msg: "уже полгода с вами!",
      event: { type: "sub", text: "lena_draws продлил подписку — 6 мес." } },
    { user: "night_owl", color: "#1e90ff", badges: ["moderator"], msg: "",
      event: { type: "gift", text: "night_owl дарит чату подписки: 5 шт." } },
    { user: "pixelpanda", color: "#9acd32", badges: [], msg: "",
      event: { type: "raid", text: "Рейд! pixelpanda и 42 зрителей" } },
  ];
  function demoMessage(i) {
    const d = DEMO[i % DEMO.length];
    const now = new Date();
    return Object.assign({ kind: "msg", platform: i % 5 === 3 ? "youtube" : "twitch",
      ts: now.toTimeString().slice(0, 8) }, clone(d));
  }

  window.ChatStyle = { DEFAULTS, PRESETS, GOOGLE_FONTS, SYSTEM_FONTS, Renderer, normalize, fromPreset,
                       deepMerge, clone, demoMessage, DEMO, ensureFont };
})();
