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
  try {
    const path = await window.pywebview.api.open_dialog();
    if (!path) { status("취소됨"); return; }
    currentPath = path;
    $("#filepath").textContent = path;
    status("로드됨: " + path.split("/").pop());
    run("inspect");
  } catch (e) {
    status("파일 열기 오류: " + String(e), "sev-error");
  }
};

// 경로 직접 입력으로 열기 (다이얼로그 우회)
async function loadPath(p) {
  p = (p || "").trim();
  if (!p) { status("경로를 입력하세요", "sev-warning"); return; }
  currentPath = p;
  $("#filepath").textContent = p;
  status("로드 중: " + p.split("/").pop(), "spin");
  document.querySelector('.tab[data-tab="inspect"]').click();
  await run("inspect");
}
$("#btn-load").onclick = () => loadPath($("#pathinput").value);
$("#pathinput").addEventListener("keydown", e => { if (e.key === "Enter") loadPath(e.target.value); });

// 액션 버튼
document.querySelectorAll("[data-run]").forEach(b => {
  b.onclick = () => run(b.dataset.run);
});

// 위반 전압을 도면에 표시
$("#btn-locate").onclick = async () => {
  if (!needFile()) return;
  status("전압 위치 탐색 중…", "spin");
  try {
    const includeOk = $("#loc-all").checked;
    const loc = await window.pywebview.api.locate_voltages(currentPath, includeOk);
    if (!loc.count) { status("표시할 전압이 없습니다"); return; }
    status(`도면 렌더 + 마커 ${loc.count}곳…`, "spin");
    const r = await window.pywebview.api.render(currentPath, 50000, loc.items);
    $("#preview-out").innerHTML = r.svg;
    setupPanZoom($("#preview-out"));
    document.querySelector('.tab[data-tab="preview"]').click();
    const msg = includeOk
      ? `전압 ${loc.count}곳 (위반 ${loc.violations}=빨강 · 정상 ${loc.ok}=초록) · 휠로 확대`
      : `위반 전압 ${loc.violations}곳 표시(빨강) · 휠로 확대해 확인`;
    status(msg);
  } catch (e) {
    status("위치 표시 오류: " + String(e), "sev-error");
  }
};

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
  setupPanZoom($("#preview-out"));
  status(`도면 렌더: 폴리라인 ${d.polylines.toLocaleString()}개 · 휠 확대/드래그 이동`);
}

$("#btn-fit").onclick = () => resetPanZoom();

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
      `<tr><td class="sev-${f.severity}">${f.severity}</td>
       <td>${esc(f.message)}</td>
       <td class="detail">${esc(f.detail || "")}</td>
       <td class="mono">${esc(f.context)}</td></tr>`).join("");
    $("#validate-out").innerHTML = `
      <div class="cards"><div class="card"><div class="num sev-warning">${d.count}</div><div class="lbl">위반</div></div></div>
      <table><thead><tr><th>심각도</th><th>요약</th><th>무엇이 / 왜 틀렸나</th><th>도면 표기</th></tr></thead><tbody>${rows}</tbody></table>`;
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

// 명령행으로 전달된 파일이 있으면 자동 로드
window.addEventListener("pywebviewready", async () => {
  status("준비됨 — 도면을 여세요");
  try {
    const p = await window.pywebview.api.default_path();
    if (p) {
      currentPath = p;
      $("#filepath").textContent = p;
      status("자동 로드: " + p.split("/").pop());
      run("inspect");
    }
  } catch (e) { /* 무시 */ }
});
