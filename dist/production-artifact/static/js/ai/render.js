/**
 * Tarika AI Assistant - Rendering & Exam Simulation Module
 * Handles KaTeX math formatting, Markdown rendering, code highlighting, and interactive practice exams.
 */
(function() {
  'use strict';

  window.TarikaState = window.TarikaState || {
    activeDocId: null,
    activeDocTitle: '',
    activeConversationId: localStorage.getItem('ai_active_convo_id') || null,
    chatHistory: [],
    currentExamData: null,
    currentExamIdx: 0,
    examUserAnswers: {},
    examCheckedStatus: {},
    examTimerInterval: null,
    examTimeRemaining: 0,
    sessionLocalDegraded: false,
    isRequestInFlight: false,
    isHistoryOpen: false,
    currentAbortController: null
  };

  // ── Exam Timer Helpers ──────────────────────────────────────────
  function startExamTimer(seconds) {
    stopExamTimer();
    window.TarikaState.examTimeRemaining = seconds;
    updateTimerDisplay();
    window.TarikaState.examTimerInterval = setInterval(() => {
      window.TarikaState.examTimeRemaining--;
      updateTimerDisplay();
      if (window.TarikaState.examTimeRemaining <= 0) {
        stopExamTimer();
        alert('⏱️ Time is up! Submitting your practice exam now.');
        window.renderModalScorecard();
      }
    }, 1000);
  }

  function stopExamTimer() {
    if (window.TarikaState.examTimerInterval) {
      clearInterval(window.TarikaState.examTimerInterval);
      window.TarikaState.examTimerInterval = null;
    }
  }

  function updateTimerDisplay() {
    const badge = document.getElementById('aiExamTimerBadge');
    const txt = document.getElementById('aiExamTimerText');
    if (!txt) return;
    const m = Math.floor(Math.max(0, window.TarikaState.examTimeRemaining) / 60);
    const s = Math.max(0, window.TarikaState.examTimeRemaining) % 60;
    txt.textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    if (badge) {
      if (window.TarikaState.examTimeRemaining <= 120 && window.TarikaState.examTimeRemaining > 0) badge.classList.add('warning');
      else badge.classList.remove('warning');
    }
  }

  window.toggleExamFullscreen = function() {
    const modal = document.getElementById('tarikaExamModal');
    if (!document.fullscreenElement) {
      if (modal && modal.requestFullscreen) modal.requestFullscreen().catch(() => {});
      else if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => {});
    } else {
      if (document.exitFullscreen) document.exitFullscreen().catch(() => {});
    }
  };

  document.addEventListener('fullscreenchange', () => {
    const btn = document.getElementById('aiExamFullscreenBtn');
    if (btn) btn.innerHTML = document.fullscreenElement ? '🗗 Exit Fullscreen' : '⛶ Fullscreen';
  });

  // ── Exam JSON Parser & Recovery (Task 4.10) ───────────────────
  function extractExamData(text) {
    if (!text || typeof text !== 'string') return null;
    const fullMatch = text.match(/\{[\s\S]*?"questions"\s*:\s*\[[\s\S]*?\}\s*\]\s*\}/);
    if (fullMatch) {
      try {
        const parsed = JSON.parse(fullMatch[0]);
        if (parsed && Array.isArray(parsed.questions) && parsed.questions.length > 0) {
          return { data: parsed, rawMatch: fullMatch[0] };
        }
      } catch (e) {
        try {
          const cleaned = fullMatch[0].replace(/,\s*([\]\}])/g, '$1');
          const parsed = JSON.parse(cleaned);
          if (parsed && Array.isArray(parsed.questions) && parsed.questions.length > 0) {
            return { data: parsed, rawMatch: fullMatch[0] };
          }
        } catch (e2) {}
      }
    }

    if (text.includes('"questions"')) {
      const jsonStartIdx = text.search(/\{[\s\S]*?"questions"/);
      if (jsonStartIdx !== -1) {
        let jsonSubstring = text.slice(jsonStartIdx);
        if (!jsonSubstring.includes(']}')) {
          const lastValidBrace = jsonSubstring.lastIndexOf('}');
          if (lastValidBrace !== -1) {
            jsonSubstring = jsonSubstring.slice(0, lastValidBrace + 1) + ']}';
          }
        }
        const titleMatch = jsonSubstring.match(/"title"\s*:\s*"([^"]+)"/);
        const title = titleMatch ? titleMatch[1] : 'Practice Exam Simulator';
        const questions = [];
        const qRegex = /\{\s*"id"\s*:\s*\d+[\s\S]*?"question"\s*:\s*"[^"]+"[\s\S]*?\}(?=\s*,|\s*\]|\s*$)/g;
        let qm;
        while ((qm = qRegex.exec(jsonSubstring)) !== null) {
          try {
            const qObj = JSON.parse(qm[0]);
            if (qObj && qObj.question) questions.push(qObj);
          } catch (err) {
            try {
              const qObj = JSON.parse(qm[0].replace(/,\s*([\]\}])/g, '$1'));
              if (qObj && qObj.question) questions.push(qObj);
            } catch (err2) {}
          }
        }
        if (questions.length > 0) {
          return { data: { title, questions, isTruncated: true }, rawMatch: jsonSubstring };
        }
      }
    }
    return null;
  }

  // ── Exam Modal Interactions ───────────────────────────────────
  window.openExamModal = function(data) {
    if (!data || !Array.isArray(data.questions) || data.questions.length === 0) return;
    window.TarikaState.currentExamData = data;
    window.TarikaState.currentExamIdx = 0;
    for (let k in window.TarikaState.examUserAnswers) delete window.TarikaState.examUserAnswers[k];
    for (let k in window.TarikaState.examCheckedStatus) delete window.TarikaState.examCheckedStatus[k];

    const modal = document.getElementById('tarikaExamModal');
    const titleEl = document.getElementById('examModalTitle');
    if (titleEl) titleEl.textContent = data.title || 'Practice Exam Simulator';
    if (modal) {
      modal.style.display = 'flex';
      if (modal.requestFullscreen) modal.requestFullscreen().catch(() => {});
      const totalSeconds = data.time_limit_minutes ? (data.time_limit_minutes * 60) : Math.max(300, (data.questions.length || 5) * 90);
      startExamTimer(totalSeconds);
      window.renderModalQuestion(0);
    }
  };

  window.closeExamModal = function() {
    stopExamTimer();
    if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(() => {});
    const modal = document.getElementById('tarikaExamModal');
    if (modal) modal.style.display = 'none';
  };

  function updateExamNavStrip(total, currentIdx) {
    const strip = document.getElementById('examNavStrip');
    if (!strip || !window.TarikaState.currentExamData) return;
    strip.innerHTML = '';
    for (let i = 0; i < total; i++) {
      const q = window.TarikaState.currentExamData.questions[i];
      const pill = document.createElement('button');
      pill.type = 'button';
      pill.className = 'ai-exam-nav-pill';
      if (i === currentIdx) pill.classList.add('active');
      const isAns = window.TarikaState.examUserAnswers[q.id] !== undefined && window.TarikaState.examUserAnswers[q.id] !== '' && (!Array.isArray(window.TarikaState.examUserAnswers[q.id]) || window.TarikaState.examUserAnswers[q.id].length > 0);
      if (isAns) pill.classList.add('answered');
      pill.textContent = `Q${i + 1}`;
      pill.onclick = () => window.renderModalQuestion(i);
      strip.appendChild(pill);
    }
  }

  function isOptMatching(opt, target) {
    if (!opt || !target) return false;
    const cleanOpt = opt.trim().toLowerCase();
    const cleanTarget = String(target).trim().toLowerCase();
    if (cleanOpt === cleanTarget) return true;
    const optLetter = cleanOpt.match(/^([a-d])[\)\.]/);
    const targetLetter = cleanTarget.match(/^([a-d])[\)\.]/);
    if (optLetter && targetLetter && optLetter[1] === targetLetter[1]) return true;
    if (optLetter && cleanTarget === optLetter[1]) return true;
    return false;
  }

  window.checkCurrentModalQuestion = function(idx) {
    if (!window.TarikaState.currentExamData || !window.TarikaState.currentExamData.questions[idx]) return;
    const q = window.TarikaState.currentExamData.questions[idx];
    window.TarikaState.examCheckedStatus[q.id] = true;
    window.renderModalQuestion(idx);
  };

  function renderExplanationBox(box, q) {
    if (!box) return;
    const expText = q.explanation || q.model_answer || 'Check the correct answer and core technical principles.';
    const keywordsText = Array.isArray(q.keywords) && q.keywords.length > 0 ? q.keywords.join(', ') : null;
    const correctAnsStr = q.correct_answer || (Array.isArray(q.correct_options) ? q.correct_options.join(', ') : null) || q.model_answer;

    box.className = 'ai-exam-exp-box';
    box.innerHTML = `
      <div class="ai-exam-exp-title">💡 Correct Solution & Detailed Explanation</div>
      ${correctAnsStr ? `<div style="font-size:13px;margin-bottom:8px;color:#34d399;"><strong>Correct Answer:</strong> ${window.formatAiMarkdown(correctAnsStr)}</div>` : ''}
      <div class="ai-exam-exp-content">${window.formatAiMarkdown(expText)}</div>
      ${keywordsText ? `<div class="ai-exam-keywords">🔑 <strong>Key Keywords:</strong> ${keywordsText}</div>` : ''}
    `;
    window.postProcessAiBubble(box);
  }

  window.renderModalQuestion = function(idx) {
    const data = window.TarikaState.currentExamData;
    if (!data || !data.questions[idx]) return;
    window.TarikaState.currentExamIdx = idx;
    const q = data.questions[idx];
    const total = data.questions.length;
    const progress = Math.round(((idx + 1) / total) * 100);

    const progFill = document.getElementById('examModalProgFill');
    if (progFill) progFill.style.width = `${progress}%`;

    updateExamNavStrip(total, idx);

    const wrap = document.getElementById('examContentWrap') || document.getElementById('examModalBody');
    const ftr = document.getElementById('examModalFtr');
    if (!wrap || !ftr) return;

    let typeLabel = 'MCQ (Single Choice)';
    if (q.type === 'msq') typeLabel = 'MSQ (Multi-Select)';
    else if (q.type === 'one_word') typeLabel = 'One Word / Direct Answer';
    else if (q.type === 'short') typeLabel = 'Short (1-Line Answer)';
    else if (q.type === 'detail' || q.type === 'brief') typeLabel = 'Detailed / Descriptive';

    const isChecked = !!window.TarikaState.examCheckedStatus[q.id];

    wrap.innerHTML = `
      <div class="ai-exam-meta-bar">
        <span class="ai-exam-badge">${typeLabel}</span>
        <span class="ai-exam-badge marks">${q.marks || 2} Marks</span>
        <span class="ai-exam-step">Question ${idx + 1} of ${total}</span>
        <button type="button" class="ai-exam-ask-tarika-btn" onclick="askTarikaAboutQuestion(${idx})" style="margin-left:auto; background:rgba(99,102,241,0.18); border:1px solid rgba(99,102,241,0.35); color:#a5b4fc; font-size:11px; font-weight:600; padding:3px 9px; border-radius:6px; cursor:pointer; display:inline-flex; align-items:center; gap:4px;" title="Ask Tarika to explain or hint this question">✨ Ask Tarika</button>
      </div>
      <div class="ai-exam-qtext-lg" id="modalQText"></div>
      <div class="ai-exam-ans-area" id="modalAnsArea"></div>
      <div id="modalExpBox" style="display:${isChecked ? 'block' : 'none'};"></div>
    `;

    const qTextEl = wrap.querySelector('#modalQText');
    if (qTextEl) {
      qTextEl.innerHTML = window.formatAiMarkdown(q.question);
      window.postProcessAiBubble(qTextEl);
    }

    const ansArea = wrap.querySelector('#modalAnsArea');

    if (q.type === 'mcq' && Array.isArray(q.options)) {
      q.options.forEach((opt) => {
        const isSelected = window.TarikaState.examUserAnswers[q.id] === opt;
        const optCard = document.createElement('div');
        optCard.className = 'ai-exam-opt-card' + (isSelected ? ' selected' : '');
        if (isChecked) {
          const isCorrect = isOptMatching(opt, q.correct_answer);
          if (isCorrect) optCard.classList.add('correct');
          else if (isSelected) optCard.classList.add('incorrect');
        }
        optCard.innerHTML = `
          <input type="radio" name="modal_q_${q.id}" value="${opt.replace(/"/g, '&quot;')}" ${isSelected ? 'checked' : ''} ${isChecked ? 'disabled' : ''}>
          <div style="flex:1;">${window.formatAiMarkdown(opt)}</div>
        `;
        if (!isChecked) {
          optCard.onclick = () => {
            window.TarikaState.examUserAnswers[q.id] = opt;
            ansArea.querySelectorAll('.ai-exam-opt-card').forEach(c => c.classList.remove('selected'));
            optCard.classList.add('selected');
            const r = optCard.querySelector('input');
            if (r) r.checked = true;
            updateExamNavStrip(total, idx);
          };
        }
        ansArea.appendChild(optCard);
        window.postProcessAiBubble(optCard);
      });
    } else if (q.type === 'msq' && Array.isArray(q.options)) {
      if (!Array.isArray(window.TarikaState.examUserAnswers[q.id])) window.TarikaState.examUserAnswers[q.id] = [];
      q.options.forEach((opt) => {
        const isSelected = window.TarikaState.examUserAnswers[q.id].includes(opt);
        const optCard = document.createElement('div');
        optCard.className = 'ai-exam-opt-card' + (isSelected ? ' selected' : '');
        if (isChecked) {
          const isCorrect = Array.isArray(q.correct_options) ? q.correct_options.some(co => isOptMatching(opt, co)) : isOptMatching(opt, q.correct_answer);
          if (isCorrect) optCard.classList.add('correct');
          else if (isSelected) optCard.classList.add('incorrect');
        }
        optCard.innerHTML = `
          <input type="checkbox" name="modal_q_${q.id}" value="${opt.replace(/"/g, '&quot;')}" ${isSelected ? 'checked' : ''} ${isChecked ? 'disabled' : ''}>
          <div style="flex:1;">${window.formatAiMarkdown(opt)}</div>
        `;
        if (!isChecked) {
          optCard.onclick = (e) => {
            if (e.target.tagName !== 'INPUT') {
              const cb = optCard.querySelector('input');
              if (cb) cb.checked = !cb.checked;
            }
            const cb = optCard.querySelector('input');
            if (cb && cb.checked) {
              if (!window.TarikaState.examUserAnswers[q.id].includes(opt)) window.TarikaState.examUserAnswers[q.id].push(opt);
              optCard.classList.add('selected');
            } else {
              window.TarikaState.examUserAnswers[q.id] = window.TarikaState.examUserAnswers[q.id].filter(x => x !== opt);
              optCard.classList.remove('selected');
            }
            updateExamNavStrip(total, idx);
          };
        }
        ansArea.appendChild(optCard);
        window.postProcessAiBubble(optCard);
      });
    } else if (q.type === 'short' || q.type === 'one_word') {
      const inp = document.createElement('input');
      inp.type = 'text';
      inp.className = 'ai-exam-input';
      inp.placeholder = q.type === 'one_word' ? 'Type the exact one-word answer...' : 'Type your one-line answer here...';
      inp.value = window.TarikaState.examUserAnswers[q.id] || '';
      inp.disabled = isChecked;
      inp.oninput = () => {
        window.TarikaState.examUserAnswers[q.id] = inp.value;
        updateExamNavStrip(total, idx);
      };
      ansArea.appendChild(inp);
      if (!isChecked) setTimeout(() => inp.focus(), 60);
    } else {
      const ta = document.createElement('textarea');
      ta.className = 'ai-exam-textarea';
      ta.rows = 4;
      ta.placeholder = 'Write your technical answer and core keywords here...';
      ta.value = window.TarikaState.examUserAnswers[q.id] || '';
      ta.disabled = isChecked;
      ta.oninput = () => {
        window.TarikaState.examUserAnswers[q.id] = ta.value;
        updateExamNavStrip(total, idx);
      };
      ansArea.appendChild(ta);
      if (!isChecked) setTimeout(() => ta.focus(), 60);
    }

    if (isChecked) renderExplanationBox(wrap.querySelector('#modalExpBox'), q);

    ftr.innerHTML = `
      <div>
        ${idx > 0 ? `<button type="button" class="ai-exam-btn sec" onclick="renderModalQuestion(${idx - 1})">← Previous</button>` : ''}
      </div>
      <div style="display:flex;gap:10px;">
        ${!isChecked ? `<button type="button" class="ai-exam-btn sec" onclick="checkCurrentModalQuestion(${idx})">💡 Check Answer & Explanation</button>` : ''}
        ${idx < total - 1 ? `<button type="button" class="ai-exam-btn pri" onclick="renderModalQuestion(${idx + 1})">Next Question ➔</button>` : `<button type="button" class="ai-exam-btn pri" onclick="renderModalScorecard()">View Final Scorecard 🏆</button>`}
      </div>
    `;
  };

  window.renderModalScorecard = function() {
    const data = window.TarikaState.currentExamData;
    if (!data) return;
    stopExamTimer();
    const total = data.questions.length;
    let score = 0;
    let totalPossible = 0;

    data.questions.forEach((q) => {
      const marks = q.marks || 2;
      totalPossible += marks;
      const userAns = window.TarikaState.examUserAnswers[q.id];
      if (q.type === 'mcq' && isOptMatching(userAns, q.correct_answer)) {
        score += marks;
      } else if (q.type === 'msq' && Array.isArray(userAns) && Array.isArray(q.correct_options)) {
        const correctCount = userAns.filter(u => q.correct_options.some(co => isOptMatching(u, co))).length;
        if (correctCount === q.correct_options.length && userAns.length === q.correct_options.length) {
          score += marks;
        } else if (correctCount > 0) {
          score += Math.round(marks / 2);
        }
      } else if (q.type === 'one_word' && userAns && q.correct_answer) {
        if (String(userAns).trim().toLowerCase() === String(q.correct_answer).trim().toLowerCase()) {
          score += marks;
        }
      } else if (userAns && String(userAns).trim().length > 3) {
        score += Math.round(marks * 0.75);
      }
    });

    const pct = Math.round((score / totalPossible) * 100);
    const badge = pct >= 80 ? '🌟 Outstanding Performance' : (pct >= 50 ? '👍 Good Effort — Keep Practicing' : '📚 Needs Review');

    const wrap = document.getElementById('examContentWrap') || document.getElementById('examModalBody');
    const ftr = document.getElementById('examModalFtr');
    const progFill = document.getElementById('examModalProgFill');
    if (progFill) progFill.style.width = '100%';

    wrap.innerHTML = `
      <div style="text-align:center;padding:16px 0 24px;">
        <div style="font-size:42px;margin-bottom:8px;" aria-hidden="true">🏆</div>
        <h2 style="font-size:22px;color:#fff;margin:0 0 8px;font-weight:800;">Exam Completed!</h2>
        <div style="font-size:28px;font-weight:800;color:#38bdf8;margin:8px 0;">${score} / ${totalPossible} <span style="font-size:15px;color:#94a3b8;font-weight:600;">(${pct}%)</span></div>
        <div class="ai-exam-badge marks" style="font-size:12px;padding:5px 14px;display:inline-block;margin-top:6px;">${badge}</div>
      </div>
      <div style="font-size:14px;font-weight:700;color:#e2e8f0;margin-bottom:12px;">📋 Question Review & Solutions:</div>
      <div id="modalReviewList" style="display:flex;flex-direction:column;gap:12px;"></div>
    `;

    const reviewList = wrap.querySelector('#modalReviewList');
    data.questions.forEach((q, i) => {
      const item = document.createElement('div');
      item.style.background = '#161f30';
      item.style.border = '1px solid rgba(255,255,255,0.08)';
      item.style.borderRadius = '12px';
      item.style.padding = '14px 18px';
      
      const userAns = window.TarikaState.examUserAnswers[q.id] || 'Not answered';
      const ansStr = Array.isArray(userAns) ? userAns.join(', ') : userAns;
      const correctStr = q.correct_answer || (Array.isArray(q.correct_options) ? q.correct_options.join(', ') : null) || q.model_answer;

      item.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
          <div style="font-size:13px;font-weight:700;color:#f8fafc;margin-bottom:6px; flex:1;">Q${i+1}. ${window.formatAiMarkdown(q.question)}</div>
          <button type="button" class="ai-exam-ask-tarika-btn" onclick="askTarikaAboutQuestion(${i})" style="flex-shrink:0; background:rgba(99,102,241,0.18); border:1px solid rgba(99,102,241,0.35); color:#a5b4fc; font-size:10.5px; font-weight:600; padding:2px 8px; border-radius:5px; cursor:pointer;" title="Ask Tarika to explain this solution">✨ Ask Tarika</button>
        </div>
        <div style="font-size:12px;color:#94a3b8;margin-bottom:4px;">Your Answer: <span style="color:#fff;font-weight:600;">${window.formatAiMarkdown(ansStr)}</span></div>
        ${correctStr ? `<div style="font-size:12px;color:#34d399;margin-top:6px;border-top:1px dashed rgba(255,255,255,0.08);padding-top:6px;"><strong>Correct Solution:</strong> ${window.formatAiMarkdown(correctStr)}</div>` : ''}
        ${q.explanation ? `<div style="font-size:12px;color:#cbd5e1;margin-top:6px;"><strong>Explanation:</strong> ${window.formatAiMarkdown(q.explanation)}</div>` : ''}
      `;
      reviewList.appendChild(item);
    });
    window.postProcessAiBubble(reviewList);

    ftr.innerHTML = `
      <button type="button" class="ai-exam-btn sec" onclick="openExamModal(window.TarikaState.currentExamData)">🔄 Retake Exam</button>
      <div style="display:flex;gap:10px;">
        <button type="button" class="ai-exam-btn pri" onclick="submitExamScoreToTarika()">📤 Send to Tarika for Strict Marking</button>
        <button type="button" class="ai-exam-btn sec" onclick="closeExamModal()">✕ Close</button>
      </div>
    `;
  };

  window.askTarikaAboutQuestion = function(idx) {
    const data = window.TarikaState.currentExamData;
    if (!data || !data.questions[idx]) return;
    const q = data.questions[idx];
    const prompt = `Can you explain how to solve this question step-by-step?\n\n"${q.question}"`;
    window.closeExamModal();
    const drw = document.getElementById('abhiAiDrawer');
    if (drw && !drw.classList.contains('open') && typeof window.toggleAbhiAiDrawer === 'function') {
      window.toggleAbhiAiDrawer();
    }
    setTimeout(() => {
      if (typeof window.quickSend === 'function') {
        window.quickSend(prompt);
      } else {
        const inp = document.getElementById('aiChatInput');
        if (inp) {
          inp.value = prompt;
          if (typeof window.sendAiMessage === 'function') window.sendAiMessage();
        }
      }
    }, 250);
  };

  window.submitExamScoreToTarika = function() {
    const data = window.TarikaState.currentExamData;
    if (!data) return;
    window.closeExamModal();
    let prompt = `📝 EXAM SUBMISSION FOR EVALUATION\nExam Title: ${data.title || 'Practice Exam'}\n\n`;
    data.questions.forEach((q, i) => {
      const userAns = window.TarikaState.examUserAnswers[q.id] || 'Not answered';
      const ansStr = Array.isArray(userAns) ? userAns.join(', ') : userAns;
      prompt += `Question ${i + 1} [Type: ${q.type}, Marks: ${q.marks || 2}]:\n${q.question}\nKeywords: ${(q.keywords || []).join(', ') || 'N/A'}\nStudent Answer: ${ansStr}\n\n`;
    });
    prompt += `Please strictly evaluate each question: check for matching keywords vs missed keywords, award exact marks, highlight errors, and output the total score with complete model solutions.`;
    if (typeof window.quickSend === 'function') window.quickSend(prompt);
  };

  // ── Markdown, KaTeX & Sanitization ────────────────────────────
  window.formatAiMarkdown = function(text) {
    if (!text) return '';

    const examResult = extractExamData(text);
    let examCardHtml = '';
    if (examResult && examResult.data) {
      const ex = examResult.data;
      window.__LATEST_EXAM__ = ex;
      if (examResult.rawMatch) text = text.replace(examResult.rawMatch, '');
      text = text
        .replace(/```(?:exam_stimulus|json)?[\s\S]*?"questions"[\s\S]*?(?:```|$)/gi, '')
        .replace(/\{[\s\S]*?"questions"[\s\S]*?(?:\}\s*\]\s*\}|$)/gi, '')
        .replace(/```(?:exam_stimulus|json)?\s*```/gi, '')
        .trim();

      const qCount = ex.questions.length;
      examCardHtml = `
        <div class="ai-exam-launch-card">
          <div class="ai-exam-launch-icon">🎯</div>
          <div class="ai-exam-launch-info">
            <div class="ai-exam-launch-title">${ex.title || 'Practice Exam Simulator'}</div>
            <div class="ai-exam-launch-sub">${qCount} Questions • Interactive Exam Environment with Instant Solutions</div>
          </div>
          <button type="button" class="ai-exam-launch-btn" onclick="openExamModal(window.__LATEST_EXAM__)">Start Exam 🚀</button>
        </div>
      `;
    }

    const mathTokens = [];
    let processed = text
      .replace(/\$\$([\s\S]*?)\$\$/g, (match, expr) => {
        const id = `@@MATH_BLOCK_${mathTokens.length}@@`;
        mathTokens.push({ id, expr, display: true });
        return id;
      })
      .replace(/\\\[([\s\S]*?)\\\]/g, (match, expr) => {
        const id = `@@MATH_BLOCK_${mathTokens.length}@@`;
        mathTokens.push({ id, expr, display: true });
        return id;
      })
      .replace(/\\\(([\s\S]*?)\\\)/g, (match, expr) => {
        const id = `@@MATH_INLINE_${mathTokens.length}@@`;
        mathTokens.push({ id, expr, display: false });
        return id;
      })
      .replace(/(^|[^\\])\$([^\$\n]+?)\$/g, (match, prefix, expr) => {
        const id = `@@MATH_INLINE_${mathTokens.length}@@`;
        mathTokens.push({ id, expr, display: false });
        return prefix + id;
      });

    let html = '';
    if (typeof marked !== 'undefined' && marked.parse) {
      try {
        marked.setOptions({ gfm: true, breaks: true });
        html = marked.parse(processed);
      } catch (e) {
        console.warn('[Tarika Markdown Error]', e);
      }
    }

    if (!html) {
      html = processed
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^## (.*$)/gim, '<h2>$1</h2>')
        .replace(/^# (.*$)/gim, '<h1>$1</h1>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
    }

    mathTokens.forEach(({ id, expr, display }) => {
      let renderedMath = '';
      if (typeof katex !== 'undefined' && katex.renderToString) {
        try {
          renderedMath = katex.renderToString(expr.trim(), {
            displayMode: display,
            throwOnError: false
          });
        } catch (e) {
          renderedMath = display ? `<pre class="katex-fallback"><code>$$${expr}$$</code></pre>` : `<code class="katex-fallback">$${expr}$</code>`;
        }
      } else {
        renderedMath = display ? `<pre class="katex-fallback"><code>$$${expr}$$</code></pre>` : `<code class="katex-fallback">$${expr}$</code>`;
      }
      html = html.replace(id, renderedMath);
    });

    if (examCardHtml) html += examCardHtml;

    // Task 4.8: Sanitize raw HTML from model output
    html = html
      .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
      .replace(/\s+on[a-zA-Z]+\s*=\s*(['"]).*?\1/gi, '')
      .replace(/\s+on[a-zA-Z]+\s*=\s*[^ >]+/gi, '');

    return html;
  };

  window.postProcessAiBubble = function(bubble) {
    if (!bubble) return;
    bubble.querySelectorAll('table').forEach(table => {
      if (!table.parentElement.classList.contains('ai-table-wrap')) {
        const wrap = document.createElement('div');
        wrap.className = 'ai-table-wrap';
        table.parentNode.insertBefore(wrap, table);
        wrap.appendChild(table);
      }
    });

    // Task 4.8: Mermaid parsing with fallback to raw code block on syntax error
    bubble.querySelectorAll('pre code.language-mermaid, pre.mermaid').forEach(mEl => {
      if (typeof window.mermaid !== 'undefined' && typeof window.mermaid.run === 'function') {
        try {
          window.mermaid.run({ nodes: [mEl] }).catch(() => {});
        } catch (mErr) {}
      }
    });

    bubble.querySelectorAll('pre').forEach(pre => {
      if (pre.querySelector('.ai-code-copy-btn')) return;
      const copyBtn = document.createElement('button');
      copyBtn.className = 'ai-code-copy-btn';
      copyBtn.type = 'button';
      copyBtn.textContent = 'Copy';
      copyBtn.onclick = (e) => {
        e.stopPropagation();
        const codeEl = pre.querySelector('code') || pre;
        const textToCopy = codeEl.innerText.replace(/Copy$/, '').trim();
        navigator.clipboard.writeText(textToCopy).then(() => {
          copyBtn.textContent = 'Copied!';
          setTimeout(() => { copyBtn.textContent = 'Copy'; }, 2000);
        }).catch(() => {
          copyBtn.textContent = 'Failed';
          setTimeout(() => { copyBtn.textContent = 'Copy'; }, 2000);
        });
      };
      pre.appendChild(copyBtn);
    });

    bubble.querySelectorAll('a').forEach(a => {
      if (!a.classList.contains('ai-card-btn')) {
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
      }
    });

    if (typeof renderMathInElement === 'function') {
      try {
        renderMathInElement(bubble, {
          delimiters: [
            {left: '$$', right: '$$', display: true},
            {left: '\\[', right: '\\]', display: true},
            {left: '$', right: '$', display: false},
            {left: '\\(', right: '\\)', display: false}
          ],
          throwOnError: false
        });
      } catch (err) {}
    }

    if (window.__LATEST_EXAM__ && !bubble.dataset.examAutoOpened) {
      bubble.dataset.examAutoOpened = 'true';
      const modal = document.getElementById('tarikaExamModal');
      if (modal && modal.style.display !== 'flex') {
        setTimeout(() => window.openExamModal(window.__LATEST_EXAM__), 300);
      }
    }
  };

  window.streamAiResponse = async function(bubble, text, onComplete) {
    if (!text) {
      if (onComplete) onComplete();
      return;
    }
    const msgList = document.getElementById('aiMsgList');
    const tokens = text.match(/\S+|\s+/g) || [text];
    let currentText = '';
    let idx = 0;
    const step = Math.max(1, Math.ceil(tokens.length / 50));
    const intervalMs = 14;

    bubble.classList.add('streaming');

    return new Promise((resolve) => {
      const timer = setInterval(() => {
        const nextIdx = Math.min(idx + step, tokens.length);
        for (let i = idx; i < nextIdx; i++) currentText += tokens[i];
        idx = nextIdx;

        bubble.innerHTML = window.formatAiMarkdown(currentText) + (idx < tokens.length ? ' <span class="ai-typing-indicator" title="Typing response..."><span></span><span></span><span></span></span>' : '');
        window.postProcessAiBubble(bubble);
        if (msgList) msgList.scrollTo({ top: msgList.scrollHeight, behavior: 'smooth' });

        if (idx >= tokens.length) {
          clearInterval(timer);
          bubble.classList.remove('streaming');
          bubble.innerHTML = window.formatAiMarkdown(text);
          window.postProcessAiBubble(bubble);
          if (msgList) msgList.scrollTo({ top: msgList.scrollHeight, behavior: 'smooth' });
          if (onComplete) onComplete();
          resolve();
        }
      }, intervalMs);
    });
  };
})();
