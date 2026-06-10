// AttoGrid 프론트엔드 — pywebview 브리지로 Python Api 호출
let currentPath = null;

const $ = (s) => document.querySelector(s);
const status = (msg, cls = "") => { const e = $("#status"); e.textContent = msg; e.className = cls; };
const esc = (s) => (s ?? "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

// 탭 전환
document.querySelectorAll(".tab").forEach(t => {
  t.onclick = () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    $("#" + t.dataset.tab).classList.add("active");
  };
});

// 파일 열기
$("#btn-open").onclick = async () => {
  status("파일 선택 대기…", "spin");
  const path = await window.pywebview.api.open_dialog();
  if (!path) { status("취소됨"); return; }
  currentPath = path;
  $("#filepath").textContent = path;
  status("로드됨: " + path.split("/").pop());
  run("inspect");
};

// 액션 버튼
document.querySelectorAll("[data-run]").forEach(b => {
  b.onclick = () => run(b.dataset.run);
});

function needFile() {
  if (!currentPath) { status("먼저 도면을 여세요", "sev-warning"); return false; }
  return true;
}

async function run(kind) {
  if (!needFile()) return;
  const out = $("#" + kind + "-out");
  out.innerHTML = `<div class="empty spin">처리 중…</div>`;
  status(kind + " 실행 중…", "spin");
  try {
    if (kind === "inspect") return renderInspect(await window.pywebview.api.inspect(currentPath));
    if (kind === "preview") return renderPreview(await window.pywebview.api.render(currentPath));
    if (kind === "model3d") return renderModel3d(await window.pywebview.api.model3d(currentPath));
    if (kind === "texts") return renderTexts(await window.pywebview.api.texts(currentPath, $("#texts-tonly").checked));
    if (kind === "validate") return renderValidate(await window.pywebview.api.validate(currentPath));
    if (kind === "translate") {
      const backend = $("#tr-backend").value;
      const limit = parseInt($("#tr-limit").value) || 30;
      status(`번역(${backend}) 실행 중… 시간이 걸릴 수 있습니다`, "spin");
      return renderTranslate(await window.pywebview.api.translate(currentPath, backend, limit));
    }
  } catch (e) {
    out.innerHTML = `<div class="empty sev-error">오류: ${esc(String(e))}</div>`;
    status("오류 발생", "sev-error");
  }
}

function renderInspect(d) {
  const rows = d.entities.map(([k, n]) => `<tr><td class="mono">${esc(k)}</td><td>${n}</td></tr>`).join("");
  $("#inspect-out").innerHTML = `
    <div class="cards">
      <div class="card"><div class="num">${d.objects.toLocaleString()}</div><div class="lbl">전체 객체</div></div>
      <div class="card"><div class="num">${d.layers}</div><div class="lbl">레이어</div></div>
    </div>
    <table><thead><tr><th>엔티티 타입</th><th>개수</th></tr></thead><tbody>${rows}</tbody></table>`;
  status(`개요: 객체 ${d.objects.toLocaleString()}개`);
}

function renderPreview(d) {
  $("#preview-out").innerHTML = d.svg;
  status(`도면 렌더: 폴리라인 ${d.polylines.toLocaleString()}개`);
}

function renderTexts(d) {
  const rows = d.rows.map(r =>
    `<tr><td><span class="tag ${r.lang}">${r.lang}</span></td>
     <td>${r.translatable ? "✔" : "—"}</td><td>${esc(r.text)}</td></tr>`).join("");
  const dist = Object.entries(d.dist).map(([k, v]) => `${k}:${v}`).join(" · ");
  $("#texts-out").innerHTML = `
    <div class="cards">
      <div class="card"><div class="num">${d.total.toLocaleString()}</div><div class="lbl">텍스트 (${esc(dist)})</div></div>
    </div>
    <table><thead><tr><th>언어</th><th>번역</th><th>내용</th></tr></thead><tbody>${rows}</tbody></table>`;
  status(`텍스트 ${d.total}개`);
}

function renderValidate(d) {
  if (!d.count) {
    $("#validate-out").innerHTML = `<div class="empty" style="color:var(--ok)">✓ 위반 없음 — 규칙셋: ${esc(d.ruleset)}</div>`;
  } else {
    const rows = d.findings.map(f =>
      `<tr><td class="sev-${f.severity}">${f.severity}</td><td class="mono">${esc(f.rule)}</td>
       <td>${esc(f.message)}</td><td class="mono">${esc(f.context)}</td></tr>`).join("");
    $("#validate-out").innerHTML = `
      <div class="cards"><div class="card"><div class="num sev-warning">${d.count}</div><div class="lbl">위반</div></div></div>
      <table><thead><tr><th>심각도</th><th>규칙</th><th>메시지</th><th>근거</th></tr></thead><tbody>${rows}</tbody></table>`;
  }
  status(`검증: 위반 ${d.count}건`);
}

function renderTranslate(d) {
  const rows = d.rows.map(r =>
    `<tr><td>${esc(r.source)}</td><td>→</td><td>${esc(r.translation)}</td></tr>`).join("");
  $("#translate-out").innerHTML = `
    <div class="cards"><div class="card"><div class="num">${d.count}</div><div class="lbl">번역 (${esc(d.backend)})</div></div></div>
    <table><thead><tr><th>원문</th><th></th><th>번역</th></tr></thead><tbody>${rows}</tbody></table>`;
  status(`번역 완료: ${d.count}건 (${d.backend})`);
}

window.addEventListener("pywebviewready", () => status("준비됨 — 도면을 여세요"));
