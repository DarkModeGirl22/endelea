/* Endelea: About me (talk with Endelea), Diary (fun calendar), Profile (daily story + rentals with Renew).
   Loaded by ONE line at the end of index.html:  <script src="/diary.js"></script> */
(function () {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const nl = s => esc(s).replace(/\n/g, "<br>");
  const KIND_LABEL = { transport: "Transport", clothes: "Clothes", accessories: "Accessories", furniture: "Furniture", decor: "Decoration" };
  const VOICE_PAUSE_MS = 3500;   // voice mode sends your words after this much silence (the mic itself never stops)
  const LANGS = [["en-US", "English"], ["fr-FR", "Français"], ["ar-SA", "العربية"]];
  const MOODS = [[/proud|accomplish|satisf|fier|fière/i, "🥳"], [/happy|joy|glad|cheer|content|heureu|joie/i, "😊"],
    [/tired|exhaust|drain|sleep|fatigu|épuis/i, "😴"], [/stress|anx|overwhelm|worr|nervous|inquiet|angoiss/i, "😰"],
    [/sad|down|low|lonely|trist|déprim/i, "😔"], [/motivat|focus|determin|driven|product|concentr/i, "💪"],
    [/calm|peace|relax|serene|serein|apais/i, "😌"], [/excit|energ|enthus|motivé/i, "🤩"],
    [/angry|frustr|annoy|énerv|colère/i, "😤"], [/hope|optimis|espoir/i, "🌱"]];
  const moodEmoji = m => { for (const [re, e] of MOODS) if (re.test(m || "")) return e; return ""; };

  document.head.insertAdjacentHTML("beforeend", `<style>
    .eb { font-family:inherit; font-weight:700; cursor:pointer; border-radius:16px; padding:6px 14px; border:2px solid var(--line); background:var(--sun); color:#2B2A33; margin:6px 6px 0 0; text-decoration:none; display:inline-block; font-size:14px; }
    .eb:hover { background:var(--coral); color:#fff; }
    .eb.on { background:var(--coral); color:#fff; }
    .eb:disabled { opacity:.5; cursor:not-allowed; }
    textarea, select.es { font-family:inherit; background:var(--panel); color:var(--ink); border:2px solid var(--line); border-radius:10px; padding:8px 10px; width:100%; }
    select.es { width:auto; margin-top:6px; }
    .wide { max-width:760px; }
    #about.active { display:flex; flex-direction:column; height:calc(100vh - 190px); min-height:460px; }
    .chatcard { max-width:none !important; width:100%; flex:1; min-height:0; display:flex; flex-direction:column; margin-bottom:0 !important; }
    .chathead { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; }
    .chathead h2 { margin:0; }
    .chatlog { overflow-y:auto; padding:8px 4px; }
    #aLog { flex:1; min-height:0; }
    #dLog { max-height:340px; min-height:90px; }
    .chatbar { display:flex; gap:6px; align-items:flex-end; flex-wrap:wrap; padding-top:8px; }
    .chatbar textarea { flex:1 1 100%; resize:none; width:auto; }
    .empty { text-align:center; margin-top:30px; }
    .b { padding:9px 13px; border-radius:14px; margin:7px 0; max-width:88%; border:2px solid var(--line); line-height:1.35; }
    .b.user { background:var(--sun); color:#2B2A33; margin-left:auto; }
    .b.assistant { background:var(--card); }
    .b.typing { opacity:.6; font-style:italic; }
    .b.failed { opacity:.75; border-style:dashed; border-color:var(--coral); }
    .b small { color:var(--warnink); font-weight:700; }
    .nt { border-left:4px solid var(--teal); background:var(--card); padding:8px 12px; margin:8px 0; border-radius:6px; }
    .nt.you { border-left-color:var(--coral); }
    .rrow { display:flex; justify-content:space-between; align-items:center; gap:12px; padding:8px 0; border-bottom:1px dashed var(--soft); }
    .rrow small { color:var(--soft); }
    .rright { display:flex; align-items:center; gap:8px; }
    .rright .eb { margin:0; padding:4px 12px; }
    .left { font-weight:800; color:var(--teal); white-space:nowrap; }
    .left.soon-end { color:var(--warnink); }
    [hidden] { display:none !important; }
    .storytext { font-size:18px; line-height:1.5; margin:6px 0 10px; }

    /* Diary: full-screen calendar + a paper per day */
    #diary.active { display:flex; flex-direction:column; height:calc(100vh - 190px); min-height:560px; }
    .calfull { max-width:none !important; width:100%; flex:1; min-height:0; display:flex; flex-direction:column; margin-bottom:0 !important; }
    .calhead { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-bottom:12px; }
    .calnav { display:flex; align-items:center; gap:10px; }
    .calnav h2 { margin:0; min-width:280px; text-align:center; font-size:32px; }
    .calnav .eb, .calhead .eb { margin:0; }
    .dowrow, .calbody { display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); gap:8px; }
    .dowrow { margin-bottom:6px; }
    .calbody { flex:1; min-height:0; }
    .dow { text-align:center; font-weight:800; font-size:13px; color:var(--soft); text-transform:uppercase; letter-spacing:1px; }
    .cell { position:relative; min-height:0; min-width:0; overflow:hidden; border:2px solid var(--line); border-radius:12px; background:var(--card); color:var(--ink); font-family:inherit;
            cursor:pointer; padding:6px 8px 4px; text-align:left; display:flex; flex-direction:column; gap:2px; box-shadow:2px 2px 0 var(--line); }
    .cell:hover { transform:translateY(-2px); background:var(--hov); }
    .cell.blank { visibility:hidden; box-shadow:none; pointer-events:none; }
    .cell .top { display:flex; justify-content:space-between; align-items:center; }
    .cell .dn { font-weight:800; font-size:15px; }
    .cell .mid { flex:1; min-height:0; overflow:hidden; display:flex; flex-direction:column; gap:2px; }
    .cell .em { font-size:22px; line-height:1; }
    .cell .snip { font-size:12px; line-height:1.25; opacity:.85; overflow:hidden; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; word-break:break-word; }
    .cell .hh { font-size:11px; color:var(--soft); display:flex; justify-content:space-between; min-height:13px; }
    .cell.done { background:rgba(255,182,39,.30); }
    .cell.talked { background:rgba(27,181,168,.20); }
    .cell.page { background:rgba(123,97,255,.20); }
    .cell.today { outline:3px solid var(--coral); outline-offset:1px; }
    .cell.today .dn::after { content:" · today"; font-weight:700; font-size:10px; color:var(--coral); }
    .cell.sel { border-color:var(--coral); }
    .cell.future { opacity:.4; cursor:default; box-shadow:none; }
    .cell.future:hover { transform:none; background:var(--card); }
    .legend { font-size:13px; margin:10px 0 0; }

    #paperBack { position:fixed; inset:0; background:rgba(20,18,30,.6); display:flex; align-items:center; justify-content:center; z-index:25; padding:14px; }
    .paper { background:var(--card); border:3px solid var(--line); border-radius:18px; box-shadow:8px 8px 0 var(--line); width:min(980px,100%); height:min(94vh,920px);
             display:flex; flex-direction:column; padding:16px 22px 18px; }
    .paperhead { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; flex-wrap:wrap; }
    .paperhead h2 { margin:0; font-size:26px; }
    .paperhead p { margin:2px 0 0; }
    .paperbar { display:flex; align-items:center; gap:4px; flex-wrap:wrap; }
    .paperbar .eb { margin:0 0 0 4px; }
    #paperState { font-size:13px; }
    #paperText { flex:1 1 auto; min-height:140px; resize:none; margin-top:10px; font-size:18px; line-height:32px; padding:4px 16px 8px; border:2px solid var(--line); border-radius:12px;
                 background-color:var(--panel); background-image:repeating-linear-gradient(transparent 0, transparent 31px, rgba(123,97,255,.30) 31px, rgba(123,97,255,.30) 32px); background-attachment:local; }
    .paperrow { display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-top:8px; }
    .paperrow .eb { margin:0; }
    .pics { display:flex; gap:8px; overflow-x:auto; padding:2px 0; }
    .pic { position:relative; flex:0 0 auto; }
    .pic img { height:84px; width:auto; max-width:160px; object-fit:cover; border:2px solid var(--line); border-radius:10px; cursor:zoom-in; display:block; }
    .pic button { position:absolute; top:-6px; right:-6px; width:22px; height:22px; border-radius:50%; border:2px solid var(--line); background:var(--coral); color:#fff; font-weight:800; line-height:1; cursor:pointer; padding:0; }
    .paper.drag { outline:4px dashed var(--coral); outline-offset:-10px; }
    .nt.ai { background:#FFE08A; color:#2B2A33; border-left:6px solid var(--coral); border-radius:8px; margin:0; }
    #paperNote { flex:0 0 auto; max-height:36%; overflow-y:auto; margin-top:10px; }
    .paper > .paperhead, .paper > .paperrow, .paper > .pics { flex:0 0 auto; }
    #lightbox { position:fixed; inset:0; background:rgba(10,8,20,.85); z-index:40; display:flex; align-items:center; justify-content:center; cursor:zoom-out; padding:20px; }
    #lightbox img { max-width:96vw; max-height:94vh; border-radius:12px; border:3px solid #fff; }
    details.conv { margin:10px 0; }
    details.conv summary { cursor:pointer; font-weight:700; }
    @media (max-width:640px) {
      #diary.active { height:auto; min-height:0; }
      .calbody { min-height:420px; gap:4px; } .dowrow { gap:4px; }
      .cell { padding:3px 4px; } .cell .em { font-size:16px; } .cell .snip { display:none; } .cell .hh { font-size:10px; } .cell .dn { font-size:13px; }
      .calnav h2 { min-width:0; font-size:20px; } .cell.today .dn::after { content:""; }
      .paper { padding:12px; } .paperhead h2 { font-size:20px; } #paperText { font-size:16px; }
    }
  </style>`);

  // ---------- inject tabs ----------
  document.querySelector('#menu [data-tab="community"]').insertAdjacentHTML("beforebegin",
    `<button data-tab="about">About me</button><button data-tab="diary">Diary</button>`);
  document.querySelectorAll('#menu [data-tab="about"], #menu [data-tab="diary"]').forEach(b =>
    b.addEventListener("click", () => {
      goTab(b.dataset.tab);
      if (b.dataset.tab === "about") loadAbout().catch(e => toast(e.message, true));
      else openDiary();
    }));
  document.querySelectorAll("#menu button").forEach(b => b.addEventListener("click", () => {
    stopVoice();
    if (b.dataset.tab === "profile") loadStory(false);
  }));

  const langOpts = LANGS.map(([v, n]) => `<option value="${v}">${n}</option>`).join("");
  function chatHTML(p, extra) {
    return `<div class="chatlog" id="${p}Log"></div>
      <div class="chatbar">
        <textarea id="${p}In" rows="1" placeholder="Type here, or press Dictate and talk. Enter to send."></textarea>
        <button class="eb" id="${p}Send">Send</button>
        <button class="eb" id="${p}Dict">🎤 Dictate</button>
        <button class="eb" id="${p}Voice">🗣 Voice mode</button>
        <select class="es langSel" id="${p}Lang">${langOpts}</select>
        ${extra || ""}
      </div>`;
  }
  document.querySelector("main").insertAdjacentHTML("beforeend", `
    <section class="tab" id="about"><div class="card chatcard">
      <div class="chathead">
        <h2>Talk with Endelea</h2>
        <div><select class="es" id="aTone" title="How Endelea talks to you"><option value="gentle">Gentle</option><option value="balanced">Balanced</option><option value="direct">Direct</option></select></div>
      </div>
      <p class="soon">Let Endelea get to know you. It asks, you answer by typing or with your voice, and it answers out loud in voice mode. When you are done, press "Save to my story".</p>
      ${chatHTML("a", `<button class="eb" id="aSave">✅ Save to my story</button>`)}
    </div></section>

    <section class="tab" id="diary">
      <div class="card calfull">
        <div class="calhead">
          <div class="calnav"><button class="eb" id="calPrev" title="Previous month">◀</button><h2 id="calTitle"></h2><button class="eb" id="calNext" title="Next month">▶</button></div>
          <div><button class="eb" id="calToday">✏️ Write today</button><a class="eb" href="/diary/pdf">⬇ Diary (PDF)</a></div>
        </div>
        <div class="dowrow" id="calDow"></div>
        <div class="calbody" id="calGrid"></div>
        <p class="soon legend">Click a day to open its page: write as much as you like, save, and come back to add more. &nbsp;·&nbsp; 🖼 pictures on that day &nbsp;·&nbsp; the emoji is Endelea's note for that day</p>
      </div>
      <div id="paperBack" hidden><div class="paper">
        <div class="paperhead">
          <div><h2 id="paperTitle"></h2><p class="soon" id="paperSub"></p></div>
          <div class="paperbar"><span class="soon" id="paperState"></span>
            <button class="eb" id="paperDict">🎤 Dictate</button><button class="eb" id="paperSave">💾 Save</button><button class="eb" id="paperClose">✕ Close</button></div>
        </div>
        <textarea id="paperText" placeholder="Write about your day, as much as you like… You can also drop pictures here."></textarea>
        <div class="paperrow">
          <button class="eb" id="paperPic">🖼 Add pictures</button>
          <input type="file" id="picInput" accept="image/*" multiple hidden>
          <button class="eb" id="paperAI">🌙 Endelea's note</button>
          <span class="soon" id="picHint">or drag pictures onto the page</span>
        </div>
        <div class="pics" id="paperPics"></div>
        <div id="paperNote"></div>
      </div></div>
      <div id="lightbox" hidden><img alt=""></div>
    </section>`);
  $("profileCard").insertAdjacentHTML("afterend", `<div class="card" id="storyCard"></div><div class="card" id="rentalsCard"></div>`);

  // ---------- language ----------
  let curLang = "en-US";
  try { curLang = localStorage.getItem("endelea-lang") || "en-US"; } catch (e) {}
  const syncLang = () => document.querySelectorAll("select.langSel").forEach(s => { s.value = curLang; });
  document.addEventListener("change", e => {
    if (e.target.classList && e.target.classList.contains("langSel")) {
      curLang = e.target.value; try { localStorage.setItem("endelea-lang", curLang); } catch (err) {} syncLang();
    }
  });
  syncLang();

  function autosize(t) { t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 140) + "px"; }
  // The server already retries and switches model. If the AI is still busy, we wait a moment and try once more.
  async function aiCall(fn) {
    try { return await fn(); }
    catch (e) {
      if (!/busy|try again/i.test(e.message || "")) throw e;
      await new Promise(r => setTimeout(r, 4000));
      return await fn();
    }
  }
  const bubble = (role, text, extra) => `<div class="b ${role} ${extra || ""}">${nl(text)}</div>`;

  // ---------- microphone: it stays on until YOU stop it ----------
  // The browser ends a recognition by itself after a short silence (or about a minute).
  // We simply start it again right away, so you can pause and think as long as you like.
  const mic = { writing: false, r: null, want: false, owner: null, el: null, lang: "en-US", base: "", fin: "", interim: "", pause: 0, onSend: null, timer: null };

  function micStop() {
    mic.want = false; clearTimeout(mic.timer);
    const r = mic.r; mic.r = null;
    if (r) { r.onend = r.onresult = r.onerror = null; try { r.abort(); } catch (e) {} }
    const o = mic.owner; mic.owner = null;
    if (o) o.paint();
  }
  function micStart(owner, el, pause, onSend) {
    if (!SR) { toast("Speech recognition needs Chrome or Edge.", true); return false; }
    micStop();
    Object.assign(mic, { want: true, owner, el, lang: curLang, base: el.value.trim(), fin: "", interim: "", pause, onSend });
    micRun(); owner.paint(); return true;
  }
  function micRun() {
    if (!mic.want) return;
    const r = new SR(); mic.r = r;
    r.lang = mic.lang; r.continuous = true; r.interimResults = true;
    r.onresult = e => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) mic.fin += t + " "; else interim += t;
      }
      mic.interim = interim;
      const spoken = (mic.fin + interim).trim();
      mic.el.value = [mic.base, spoken].filter(Boolean).join(" ");
      mic.writing = true; mic.el.dispatchEvent(new Event("input")); mic.writing = false;   // lets the paper notice the change
      clearTimeout(mic.timer);
      if (mic.pause && spoken) mic.timer = setTimeout(() => { if (mic.want && mic.onSend) mic.onSend(mic.el.value.trim()); }, mic.pause);
    };
    r.onerror = e => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        stopVoice(); toast("Microphone blocked. Allow it in your browser (the lock icon next to the address).", true);
      }   // other errors (no-speech, network, aborted): onend restarts it
    };
    r.onend = () => {
      if (mic.want && mic.r === r && mic.interim) { mic.fin += mic.interim + " "; mic.interim = ""; }   // never lose words that were not finalized yet
      if (mic.want && mic.r === r) setTimeout(() => { if (mic.want && mic.r === r) micRun(); }, 250);
    };
    try { r.start(); } catch (e) { setTimeout(() => { if (mic.want && mic.r === r) micRun(); }, 500); }
  }

  // ---------- voice out ----------
  const cancelSpeech = () => { if ("speechSynthesis" in window) speechSynthesis.cancel(); };
  function speak(text, done) {
    let fired = false, timer = null;
    const fin = () => { if (!fired) { fired = true; clearTimeout(timer); done && done(); } };
    if (!("speechSynthesis" in window)) { fin(); return; }
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = curLang; u.onend = fin; u.onerror = fin;
    timer = setTimeout(fin, 4000 + text.length * 110);   // safety net if the browser never reports the end
    speechSynthesis.speak(u);
  }

  // ---------- one chat component, used by About me and by the Diary check-in ----------
  const chats = [];
  const stopVoice = () => { chats.forEach(c => { c.voice = false; c.paint(); }); micStop(); cancelSpeech(); };

  function createChat(p, cfg) {
    const C = { msgs: [], busy: false, voice: false };
    chats.push(C);
    const log = () => $(p + "Log"), inp = () => $(p + "In");

    C.paint = () => {
      const dictating = mic.owner === C && !C.voice;
      $(p + "Dict").classList.toggle("on", dictating);
      $(p + "Dict").textContent = dictating ? "⏹ Stop dictating" : "🎤 Dictate";
      $(p + "Voice").classList.toggle("on", C.voice);
      $(p + "Voice").textContent = C.voice ? "⏹ Stop voice mode" : "🗣 Voice mode";
    };
    C.render = () => {
      const l = log();
      if (!C.msgs.length && !C.busy) {
        l.innerHTML = `<div class="empty"><p class="soon">${cfg.emptyText}</p><button class="eb" id="${p}Start">${cfg.startLabel}</button></div>`;
        $(p + "Start").onclick = () => C.start();
      } else {
        l.innerHTML = C.msgs.map(m => m.failed
          ? `<div class="b ${m.role} failed">${nl(m.content)}<br><small>⚠ Not sent. Press Send to try again.</small></div>`
          : bubble(m.role, m.content)).join("") + (C.busy ? bubble("assistant", "…", "typing") : "");
      }
      l.scrollTop = l.scrollHeight;
    };
    C.set = msgs => { C.msgs = msgs; C.render(); cfg.onChange && cfg.onChange(C); };
    C.listen = () => { if (C.voice && !C.busy) micStart(C, inp(), VOICE_PAUSE_MS, t => C.send(t, true)); };
    C.voiceOff = () => { if (!C.voice) return; C.voice = false; micStop(); cancelSpeech(); C.paint(); };
    C.afterReply = (reply, byVoice) => {
      cfg.onChange && cfg.onChange(C);
      if (C.voice || byVoice) speak(reply, () => { if (C.voice) C.listen(); });
    };
    C.start = async () => {
      if (C.busy) return;
      C.busy = true; C.render();
      try {
        const reply = await aiCall(() => cfg.start());
        C.msgs.push({ role: "assistant", content: reply }); C.busy = false; C.render(); C.afterReply(reply, false);
      } catch (e) { C.busy = false; C.render(); toast(e.message, true); C.voiceOff(); cfg.onStartFail && cfg.onStartFail(); }
    };
    C.send = async (text, byVoice) => {
      text = (text || "").trim();
      if (!text || C.busy) return;
      micStop(); cancelSpeech();
      C.msgs = C.msgs.filter(m => !m.failed);
      inp().value = ""; autosize(inp());
      C.msgs.push({ role: "user", content: text }); C.busy = true; C.render();
      try {
        const reply = await aiCall(() => cfg.send(text, C.msgs));
        C.msgs.push({ role: "assistant", content: reply }); C.busy = false; C.render(); C.afterReply(reply, byVoice);
      } catch (e) {
        C.msgs[C.msgs.length - 1].failed = true; C.busy = false; C.render();
        inp().value = text; autosize(inp()); toast(e.message, true); C.voiceOff();
      }
    };

    $(p + "Send").onclick = () => C.send(inp().value, false);
    inp().addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); C.send(inp().value, false); } });
    inp().addEventListener("input", () => {
      autosize(inp());
      if (mic.owner === C && mic.el === inp() && !mic.writing) { mic.base = inp().value.trim(); mic.fin = ""; mic.interim = ""; }   // you edited by hand: keep your text
    });
    $(p + "Dict").onclick = () => {
      if (mic.owner === C && !C.voice) { micStop(); return; }
      stopVoice(); micStart(C, inp(), 0, null);
    };
    $(p + "Voice").onclick = async () => {
      if (C.voice) { C.voiceOff(); return; }
      stopVoice(); C.voice = true; C.paint();
      if (!C.msgs.length) await C.start(); else C.listen();
    };
    C.paint(); C.render();
    return C;
  }

  // ---------- About me ----------
  let aboutText = "", aboutLoaded = false;
  const DRAFT = "endelea-about-chat";
  const about = createChat("a", {
    emptyText: "Hi! Press the button and Endelea will start asking you questions. Answer by typing or with your voice.",
    startLabel: "🎙 Start talking",
    start: async () => (await api("POST", "/about/chat", { messages: [] })).reply,
    send: async (text, msgs) => (await api("POST", "/about/chat", { messages: msgs })).reply,
    onChange: c => { try { localStorage.setItem(DRAFT, JSON.stringify(c.msgs.filter(m => !m.failed))); } catch (e) {} },
  });

  async function loadAbout() {
    const a = await api("GET", "/about");
    aboutText = a.text; $("aTone").value = a.tone; aboutLoaded = true;
    if (!about.msgs.length && !about.busy) {
      try { const d = JSON.parse(localStorage.getItem(DRAFT) || "[]"); if (Array.isArray(d) && d.length) about.set(d); } catch (e) {}
    }
  }
  $("aTone").addEventListener("change", async () => {
    if (!aboutLoaded) return;
    try { await api("POST", "/about", { text: aboutText, tone: $("aTone").value }); toast("Saved."); } catch (e) { toast(e.message, true); }
  });
  $("aSave").addEventListener("click", async () => {
    if (about.busy) { toast("Endelea is still answering, one second.", true); return; }
    if (about.msgs.filter(m => m.role === "user").length < 2) { toast("Talk a little more with Endelea first.", true); return; }
    stopVoice();
    const b = $("aSave"); b.disabled = true; b.textContent = "Saving…";
    try {
      const r = await aiCall(() => api("POST", "/about/finish", { messages: about.msgs.filter(m => !m.failed) }));
      aboutText = r.text; about.set([]);
      try { localStorage.removeItem(DRAFT); } catch (e) {}
      toast("Saved ✓ Your story on Profile will use what you told me.");
    } catch (e) { toast(e.message, true); }
    b.disabled = false; b.textContent = "✅ Save to my story";
  });

  // ---------- Diary: full-screen calendar + a free page per day ----------
  const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const pad = n => String(n).padStart(2, "0");
  const ymd = (y, m, d) => `${y}-${pad(m + 1)}-${pad(d)}`;
  const todayStr = () => { const n = new Date(); return ymd(n.getFullYear(), n.getMonth(), n.getDate()); };
  const niceDay = day => { const [y, m, d] = day.split("-").map(Number); return new Date(y, m - 1, d).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" }); };
  const now0 = new Date();
  const cal = { y: now0.getFullYear(), m: now0.getMonth(), sel: null };
  let DAYS = {};
  $("calDow").innerHTML = DOW.map(d => `<div class="dow">${d}</div>`).join("");

  function renderCal() {
    $("calTitle").textContent = new Date(cal.y, cal.m, 1).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
    const lead = (new Date(cal.y, cal.m, 1).getDay() + 6) % 7, n = new Date(cal.y, cal.m + 1, 0).getDate(), tod = todayStr();
    $("calGrid").style.gridTemplateRows = `repeat(${Math.ceil((lead + n) / 7)}, minmax(0, 1fr))`;
    let h = `<div class="cell blank"></div>`.repeat(lead);
    for (let d = 1; d <= n; d++) {
      const key = ymd(cal.y, cal.m, d), info = DAYS[key], future = key > tod;
      const em = info ? (info.emoji || moodEmoji(info.mood) || (info.finished && !info.page ? "🙂" : "")) : "";
      const cls = ["cell", future ? "future" : "", key === tod ? "today" : "", key === cal.sel ? "sel" : "",
        info && (info.page || info.images || info.ai_note) ? "page" : info && info.finished ? "done" : info && (info.messages || info.notes) ? "talked" : ""].join(" ");
      h += `<button class="${cls}" data-day="${key}" ${future ? "disabled" : ""}>
        <span class="top"><span class="dn">${d}</span>${info && info.bonus > 0 ? `<span>⭐</span>` : ""}</span>
        <span class="mid">${em ? `<span class="em">${esc(em)}</span>` : ""}${info && info.snippet ? `<span class="snip">${esc(info.snippet)}</span>` : ""}</span>
        <span class="hh"><span>${info && info.images ? "🖼 " + info.images : ""}</span><span>${info && info.hours ? info.hours + " h" : ""}</span></span></button>`;
    }
    $("calGrid").innerHTML = h;
  }
  $("calGrid").addEventListener("click", e => { const b = e.target.closest(".cell[data-day]"); if (b && !b.disabled) openPaper(b.dataset.day); });
  $("calPrev").onclick = () => { if (--cal.m < 0) { cal.m = 11; cal.y--; } renderCal(); };
  $("calNext").onclick = () => { if (++cal.m > 11) { cal.m = 0; cal.y++; } renderCal(); };
  $("calToday").onclick = () => { const n = new Date(); cal.y = n.getFullYear(); cal.m = n.getMonth(); openPaper(todayStr()); };

  async function loadDays() {
    const list = await api("GET", "/diary/days");
    DAYS = {}; list.forEach(d => { DAYS[d.day] = d; });
    renderCal();
  }
  async function openDiary() { try { await loadDays(); } catch (e) { toast(e.message, true); } }

  // ----- the paper -----
  const paper = {
    day: null, orig: "", saving: false, timer: null, pics: [],
    paint() { const on = mic.owner === paper; $("paperDict").textContent = on ? "⏹ Stop dictating" : "🎤 Dictate"; $("paperDict").classList.toggle("on", on); },
  };
  const paperDirty = () => !!paper.day && !$("paperText").disabled && $("paperText").value !== paper.orig;
  const paperState = () => { $("paperState").textContent = paperDirty() ? "Unsaved changes…" : paper.orig ? "Saved ✓" : "New page"; };

  async function openPaper(day) {
    stopVoice();
    if (paper.day && paper.day !== day && !(await closePaper())) return;
    paper.day = day; paper.orig = ""; cal.sel = day; renderCal();
    $("paperTitle").textContent = niceDay(day); $("paperSub").textContent = ""; $("paperPics").innerHTML = ""; $("paperNote").innerHTML = ""; paper.pics = [];
    $("paperText").value = ""; $("paperText").disabled = true; $("paperState").textContent = "Opening…";
    $("paperBack").hidden = false; paper.paint();
    try {
      const d = await api("GET", "/diary/day/" + day);
      if (paper.day !== day) return;
      paper.orig = d.page || "";
      const ta = $("paperText"); ta.value = paper.orig; ta.disabled = false;
      $("paperSub").textContent = `Work: ${d.hours_worked} h`;
      paper.pics = d.images || [];
      drawPics(); drawNote(d.ai_note);
      paperState();
      ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); ta.scrollTop = ta.scrollHeight;
    } catch (e) { toast(e.message, true); paper.day = null; $("paperBack").hidden = true; }
  }

  async function savePaper(silent) {
    if (!paper.day || $("paperText").disabled) return true;
    if (paper.saving) { await new Promise(r => setTimeout(r, 300)); return savePaper(silent); }
    const day = paper.day, text = $("paperText").value;
    if (text === paper.orig) { if (!silent) toast("Saved ✓"); return true; }
    paper.saving = true; $("paperState").textContent = "Saving…";
    try {
      await api("POST", "/diary/page", { day, text });
      paper.orig = text; paper.saving = false; paperState();
      if (!silent) toast("Saved ✓");
      loadDays().catch(() => {});
      return true;
    } catch (e) { paper.saving = false; $("paperState").textContent = "⚠ Not saved"; toast(e.message, true); return false; }
  }
  async function closePaper() {
    micStop(); clearTimeout(paper.timer);
    if (paperDirty() && !(await savePaper(true))) {
      if (!confirm("Your page could not be saved. Close anyway and lose the last changes?")) return false;
    }
    paper.day = null; $("paperBack").hidden = true; return true;
  }

  // pictures: drag them on the page, paste them, or use the button
  function drawPics() {
    $("paperPics").innerHTML = paper.pics.map(p => `<div class="pic"><img src="/diary/image/${p.id}" alt="${esc(p.name || "picture")}" data-big="${p.id}"><button data-del="${p.id}" title="Remove this picture">×</button></div>`).join("");
    $("picHint").hidden = paper.pics.length > 0;
  }
  function shrink(file) {   // big phone photos become light JPEGs (max 1600 px) before they are sent
    return new Promise(resolve => {
      if (file.type === "image/gif" || !window.createImageBitmap) { resolve(file); return; }
      createImageBitmap(file).then(bmp => {
        const k = Math.min(1, 1600 / Math.max(bmp.width, bmp.height)), c = document.createElement("canvas");
        c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
        const g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height); g.drawImage(bmp, 0, 0, c.width, c.height);
        c.toBlob(b => resolve(b || file), "image/jpeg", 0.85);
      }).catch(() => resolve(file));
    });
  }
  async function addPictures(files) {
    const day = paper.day;
    const imgs = Array.from(files || []).filter(f => /^image\//.test(f.type));
    if (!day || !imgs.length) { if (files && files.length) toast("Only pictures can be added.", true); return; }
    $("paperPic").disabled = true; $("paperPic").textContent = "Adding…";
    try {
      for (const f of imgs) {
        const blob = await shrink(f);
        const r = await fetch(`/diary/image?day=${day}&name=${encodeURIComponent(f.name || "picture")}`, { method: "POST", headers: { "Content-Type": blob.type || "image/jpeg" }, body: blob });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || "The picture could not be added.");
        if (paper.day === day) { paper.pics.push({ id: data.id, name: data.name }); drawPics(); }
      }
      loadDays().catch(() => {});
    } catch (e) { toast(e.message, true); }
    $("paperPic").disabled = false; $("paperPic").textContent = "🖼 Add pictures";
  }
  $("paperPic").onclick = () => $("picInput").click();
  $("picInput").onchange = () => { addPictures($("picInput").files); $("picInput").value = ""; };
  const paperEl = document.querySelector(".paper");
  ["dragenter", "dragover"].forEach(ev => paperEl.addEventListener(ev, e => { if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files")) { e.preventDefault(); paperEl.classList.add("drag"); } }));
  ["dragleave", "drop"].forEach(ev => paperEl.addEventListener(ev, e => { if (ev === "drop" || e.target === paperEl) paperEl.classList.remove("drag"); }));
  paperEl.addEventListener("drop", e => { if (e.dataTransfer && e.dataTransfer.files.length) { e.preventDefault(); addPictures(e.dataTransfer.files); } });
  $("paperText").addEventListener("paste", e => {
    const files = Array.from((e.clipboardData && e.clipboardData.files) || []).filter(f => /^image\//.test(f.type));
    if (files.length) { e.preventDefault(); addPictures(files); }
  });
  $("paperPics").addEventListener("click", async e => {
    const del = e.target.closest("[data-del]"), big = e.target.closest("[data-big]");
    if (big) { $("lightbox").querySelector("img").src = "/diary/image/" + big.dataset.big; $("lightbox").hidden = false; return; }
    if (del && confirm("Remove this picture from the page?")) {
      try { await api("POST", `/diary/image/${del.dataset.del}/delete`); paper.pics = paper.pics.filter(p => String(p.id) !== del.dataset.del); drawPics(); loadDays().catch(() => {}); }
      catch (err) { toast(err.message, true); }
    }
  });
  $("lightbox").onclick = () => { $("lightbox").hidden = true; };

  // Endelea's note: what she thinks of the day, compared with your recent days (yellow, also in the PDF)
  function drawNote(n) {
    $("paperNote").innerHTML = n && n.text ? `<div class="nt ai"><b>🌙 Endelea's note ${esc(n.emoji || "")}</b> · ${new Date(n.ts * 1000).toLocaleDateString()}<br>${nl(n.text)}</div>` : "";
    $("paperAI").textContent = n && n.text ? "🔄 Update Endelea's note" : "🌙 Endelea's note";
  }
  $("paperAI").onclick = async () => {
    const day = paper.day, b = $("paperAI");
    if (!day || $("paperText").disabled) return;
    if ($("paperText").value.trim().length < 20) { toast("Write a few lines on the page first, then ask Endelea for her note.", true); return; }
    b.disabled = true; b.textContent = "Endelea is reading your page…";
    try {
      if (!(await savePaper(true))) throw new Error("Your page could not be saved, so the note was not asked.");
      const n = await aiCall(() => api("POST", "/diary/endelea-note/" + day));
      if (paper.day === day) { drawNote(n); $("paperNote").scrollIntoView({ block: "nearest" }); }
      loadDays().catch(() => {});
    } catch (e) { toast(e.message, true); if (paper.day === day) $("paperAI").textContent = $("paperNote").innerHTML ? "🔄 Update Endelea's note" : "🌙 Endelea's note"; }
    b.disabled = false;
  };

  $("paperText").addEventListener("input", () => {
    if (mic.owner === paper && !mic.writing) { const t = $("paperText").value.trim(); mic.base = t; mic.fin = ""; mic.interim = ""; }
    paperState();
    clearTimeout(paper.timer); paper.timer = setTimeout(() => savePaper(true), 3000);   // saves by itself after 3 s without typing
  });
  $("paperSave").onclick = () => savePaper(false);
  $("paperClose").onclick = () => closePaper();
  $("paperDict").onclick = () => {
    if (mic.owner === paper) { micStop(); return; }
    stopVoice(); micStart(paper, $("paperText"), 0, null);
  };
  $("paperBack").addEventListener("mousedown", e => { if (e.target === $("paperBack")) closePaper(); });
  document.addEventListener("keydown", e => {
    if ($("paperBack").hidden) return;
    if (e.key === "Escape") { e.preventDefault(); if (!$("lightbox").hidden) $("lightbox").hidden = true; else closePaper(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); savePaper(false); }
  });

  // ---------- Profile: daily story ----------
  const story = { text: "", loaded: false, loading: false };
  function paintStory() {
    $("storyCard").innerHTML = `<h3>✨ My story</h3>` +
      (story.text ? `<p class="storytext">${nl(story.text)}</p><p class="soon">New every day, written from what you told Endelea.</p>`
        : story.loading ? `<p class="soon">Endelea is writing today's story…</p>`
        : `<p class="soon">Talk with Endelea in <b>About me</b> and your story will appear here, new every day.</p>`) +
      `<button class="eb" id="storyHist">📅 My story history</button>`;
    $("storyHist").onclick = () => { goTab("diary"); openDiary(); };
  }
  async function loadStory(force) {
    if (story.loading || (story.loaded && story.text && !force)) return;
    story.loading = true; paintStory();
    try { const r = await api("GET", "/story"); story.text = r.text || ""; story.loaded = !r.stale; } catch (e) { /* keep what we have */ }
    story.loading = false; paintStory();
  }

  // ---------- Profile: active rentals + Renew ----------
  let rentalRows = [];
  function rentals() {
    const rows = [], r = ME.residence;
    if (r && r.mode !== "owned") rows.push({ name: r.home.name, type: `Home · rented by the ${r.mode}`, exp: r.expires, home: r.home });
    CAT.filter(i => i.rented_until && !i.owned).forEach(i => rows.push({ name: i.name, type: KIND_LABEL[i.sub] || i.sub, exp: i.rented_until, item: i }));
    return rows.sort((a, b) => a.exp - b.exp);
  }
  function left(sec) {
    if (sec <= 0) return "Ended";
    const d = Math.floor(sec / 86400), h = Math.floor(sec % 86400 / 3600), m = Math.floor(sec % 3600 / 60), s = Math.floor(sec % 60);
    return d ? `${d}d ${h}h ${m}m` : h ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`;
  }

  // Only the options that exist for that product are shown.
  function renewOptions(row) {
    const o = [];
    if (row.home) {
      const h = row.home;
      o.push({ label: "Rent a day", cost: h.day, run: () => api("POST", `/rent/${h.key}/day`), done: "Rental extended by a day." });
      o.push({ label: "Rent a month", cost: h.month, run: () => api("POST", `/rent/${h.key}/month`), done: "Rental extended by a month." });
      o.push({ label: "Buy", cost: h.buy, ask: true, run: () => api("POST", `/buy-home/${h.key}`), done: "It's yours! 🎉" });
    } else {
      const i = row.item;
      if (i.rent_day != null) o.push({ label: "Rent a day", cost: i.rent_day, run: () => api("POST", `/rent-item/${i.key}/day`), done: "Extended by a day." });
      if (i.rent_month != null) o.push({ label: "Rent a month", cost: i.rent_month, run: () => api("POST", `/rent-item/${i.key}/month`), done: "Extended by a month." });
      if (i.price != null) o.push({ label: "Buy", cost: i.price, ask: true, run: () => api("POST", `/buy/${i.key}`), done: "Yours now! ✓" });
    }
    return o;
  }
  function openRenew(row) {
    const opts = renewOptions(row);
    $("mbox").innerHTML = `<h2>Renew ${esc(row.name)}</h2><p>You have <b>${fmt(ME.hours)} h</b>. What do you want to do?</p>` +
      opts.map((o, n) => `<button class="eb" data-opt="${n}" ${ME.hours < o.cost ? "disabled" : ""}>${o.label} · ${fmt(o.cost)} h</button>`).join("<br>") +
      `<br><button class="eb" data-opt="x">Cancel</button>`;
    $("modal").style.display = "flex";
    $("mbox").onclick = async e => {
      const b = e.target.closest("[data-opt]");
      if (!b) return;
      if (b.dataset.opt === "x") { $("modal").style.display = "none"; return; }
      const o = opts[Number(b.dataset.opt)];
      if (o.ask && !confirm(`${o.label} ${row.name} for ${fmt(o.cost)} h? This cannot be undone.`)) return;
      try { await o.run(); $("modal").style.display = "none"; toast(o.done); await refresh(); }
      catch (err) { toast(err.message, true); }
    };
  }
  $("rentalsCard").addEventListener("click", e => {
    const b = e.target.closest("[data-renew]");
    if (b) openRenew(rentalRows[Number(b.dataset.renew)]);
  });

  window.renderProfile = function () {
    const s = ME.stats, home = curHome();
    $("profileCard").innerHTML = `<h2>Profile</h2>
      <p>Level <b>${s.level}</b> · Day <b>${s.days}</b> of your journey</p>
      <p>Total hours earned: <b>${s.total_hours} h</b></p>
      <p>Started on ${new Date(s.created * 1000).toLocaleDateString()}</p>
      <p>Current home: <b>${home ? esc(home.name) : "Shared room"}</b></p>`;
    paintStory(); loadCommunity();
    rentalRows = rentals();
    const now = Date.now() / 1000;
    $("rentalsCard").innerHTML = `<h3>Active rentals</h3><p class="soon">Ending soonest first.</p>` + (rentalRows.length
      ? rentalRows.map((x, n) => `<div class="rrow"><div><b>${esc(x.name)}</b><br><small>${esc(x.type)} · ends ${new Date(x.exp * 1000).toLocaleString()}</small></div>
          <div class="rright"><div class="left" data-exp="${x.exp}">${left(x.exp - now)}</div><button class="eb" data-renew="${n}">Renew</button></div></div>`).join("")
      : `<p class="soon">Nothing rented right now.</p>`);
  };
  let expiryHandled = new Set();
  setInterval(() => {
    const now = Date.now() / 1000;
    document.querySelectorAll("[data-exp]").forEach(el => {
      const exp = Number(el.dataset.exp), t = exp - now;
      el.textContent = left(t); el.classList.toggle("soon-end", t < 3600);
      if (t <= 0 && !expiryHandled.has(exp)) { expiryHandled.add(exp); refresh().catch(() => {}); }
    });
  }, 1000);


  // ---------- Demo banner + Community leaderboard ----------
  document.head.insertAdjacentHTML("beforeend", `<style>
    #demoBar { background:#FFE08A; color:#2B2A33; text-align:center; padding:6px 12px; font-size:13px; font-weight:600; }
    .lbrow { display:flex; align-items:center; gap:10px; padding:8px 12px; border-radius:12px; border:2px solid var(--line); margin:6px 0; background:var(--panel); }
    .lbrow.you { background:var(--sun); color:#2B2A33; border-color:var(--coral); }
    .lbrank { width:30px; font-weight:800; text-align:center; }
    .lbname { flex:1; font-weight:700; }
    .lbmeta { font-size:12px; font-weight:400; opacity:.75; }
    .lbhrs { font-weight:800; }
  </style>`);
  api("GET", "/status").then(r => {
    if (r && r.demo) $("menu").insertAdjacentHTML("beforebegin",
      `<div id="demoBar">🧪 Demo mode: Endelea's AI answers are examples. Add a free Gemini key to get the real AI (see the README).</div>`);
  }).catch(() => {});

  const comm = { scope: "week", data: {}, loading: false };
  function paintCommunity() {
    const d = comm.data[comm.scope];
    const medal = n => n === 1 ? "🥇" : n === 2 ? "🥈" : n === 3 ? "🥉" : n;
    const rows = d ? d.people.map(p => `<div class="lbrow${p.you ? " you" : ""}"><div class="lbrank">${medal(p.rank)}</div>
        <div class="lbname">${esc(p.name)}${p.you ? " (you)" : ""}<div class="lbmeta">Level ${p.level}</div></div>
        <div class="lbhrs">${fmt(p.hours)} h</div></div>`).join("") : `<p class="soon">Loading…</p>`;
    $("communityCard").innerHTML = `<h2>🏆 Community</h2><p class="soon">Everyone ranked by focus hours.</p>
      <button class="eb${comm.scope === "week" ? " on" : ""}" data-scope="week">This week</button>
      <button class="eb${comm.scope === "all" ? " on" : ""}" data-scope="all">All time</button>` + rows +
      `<p class="soon">Sample names: real accounts are planned.</p>`;
  }
  async function loadCommunity() {
    if (comm.loading) return;
    comm.loading = true;
    try {
      const [w, a] = await Promise.all([api("GET", "/community?scope=week"), api("GET", "/community?scope=all")]);
      comm.data = { week: w, all: a };
    } catch (e) { /* keep what we have */ }
    comm.loading = false; paintCommunity();
  }
  $("communityCard").addEventListener("click", e => {
    const b = e.target.closest("[data-scope]");
    if (b) { comm.scope = b.dataset.scope; paintCommunity(); }
  });
  paintCommunity(); loadCommunity();

  refresh().catch(() => {});   // redraw Profile with the new version
  loadStory(false);
})();
