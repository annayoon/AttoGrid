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

async function exportImage(fmt) {
  if (!needFile()) return;
  const markers = $("#img-markers").checked;
  status(`${fmt.toUpperCase()} 내보내는 중…${markers ? " (마커 포함)" : ""}`, "spin");
  try {
    const r = await window.pywebview.api.export_image(currentPath, fmt, markers);
    status(`저장됨: ${r.path}`);
  } catch (e) {
    status("이미지 내보내기 오류: " + String(e), "sev-error");
  }
}
$("#btn-png").onclick = () => exportImage("png");
$("#btn-svg").onclick = () => exportImage("svg");

// 도면 위에 번역 얹기
$("#btn-overlay").onclick = async () => {
  if (!needFile()) return;
  const engine = $("#overlay-engine").value;
  status(`번역 얹는 중… (${engine})${engine !== "glossary" ? " — 시간이 걸릴 수 있습니다" : ""}`, "spin");
  try {
    const r = await window.pywebview.api.render_translated(currentPath, engine);
    $("#preview-out").innerHTML = r.svg;
    setupPanZoom($("#preview-out"));
    document.querySelector('.tab[data-tab="preview"]').click();
    status(`번역 ${r.texts.toLocaleString()}개를 도면에 얹음 (${r.backend}) · 휠로 확대`);
  } catch (e) { status("번역 얹기 오류: " + String(e), "sev-error"); }
};

// 3D PNG 저장 — 현재 보이는 뷰 그대로 캡처
$("#btn-3d-png").onclick = async () => {
  if (!needFile()) return;
  const dataUrl = typeof capture3d === "function" ? capture3d() : null;
  if (!dataUrl) { status("먼저 3D를 생성하세요", "sev-warning"); return; }
  status("3D PNG 저장 중…", "spin");
  try {
    const r = await window.pywebview.api.save_canvas_png(dataUrl);
    if (r.error) { status("3D 저장 오류: " + r.error, "sev-error"); return; }
    status(`3D PNG 저장됨: ${r.path}`);
  } catch (e) { status("3D 저장 오류: " + String(e), "sev-error"); }
};

// 격자 옵션은 grid 방식일 때만 표시
function syncGridOpts() { $("#grid-opts").style.display = $("#part-method").value === "grid" ? "" : "none"; }
$("#part-method").onchange = syncGridOpts;
syncGridOpts();

// 구획 미리보기: 경계 박스 오버레이 + 구획별 집계 표
$("#btn-partition").onclick = async () => {
  if (!needFile()) return;
  const method = $("#part-method").value;
  const rows = parseInt($("#grid-rows").value) || 2, cols = parseInt($("#grid-cols").value) || 2;
  status("구획 분석 중…", "spin");
  try {
    const part = await window.pywebview.api.partition(currentPath, method, rows, cols);
    const r = await window.pywebview.api.render(currentPath, 50000, null, part.sections);
    $("#preview-out").innerHTML = r.svg;
    setupPanZoom($("#preview-out"));
    renderSectionList(part.sections);
    document.querySelector('.tab[data-tab="preview"]').click();
    $("#part-info").textContent = `${part.count}개 구획`;
    status(`구획 ${part.count}개 (${method}) — 경계·집계 표시`);
  } catch (e) { status("구획 오류: " + String(e), "sev-error"); }
};

function renderSectionList(secs) {
  const rows = secs.map((s, i) =>
    `<tr><td>${i + 1}</td><td>${esc(s.title || s.label)}</td>
     <td>${(s.texts ?? 0).toLocaleString()}</td>
     <td>${(s.translatable ?? 0).toLocaleString()}</td>
     <td class="${s.violations ? "sev-warning" : ""}">${s.violations ?? 0}</td></tr>`).join("");
  $("#section-list").innerHTML = `
    <table class="section-table"><thead><tr>
      <th>#</th><th>구획 제목</th><th>텍스트</th><th>번역 대상</th><th>위반</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
}

// 시트별 번역 CSV (번역 탭의 엔진 사용)
$("#btn-sec-trans").onclick = async () => {
  if (!needFile()) return;
  const method = $("#part-method").value;
  const rows = parseInt($("#grid-rows").value) || 2, cols = parseInt($("#grid-cols").value) || 2;
  const backend = $("#tr-backend").value;
  status(`시트별 번역 CSV 생성 중… (${backend})${backend !== "mock" ? " — 시간이 걸릴 수 있습니다" : ""}`, "spin");
  try {
    const r = await window.pywebview.api.export_section_translations(currentPath, method, backend, rows, cols);
    status(`시트별 번역 CSV ${r.count}개 저장됨: ${r.dir}`);
  } catch (e) { status("시트별 번역 오류: " + String(e), "sev-error"); }
};

// 구획별 이미지 저장
$("#btn-sections").onclick = async () => {
  if (!needFile()) return;
  const method = $("#part-method").value;
  const rows = parseInt($("#grid-rows").value) || 2, cols = parseInt($("#grid-cols").value) || 2;
  const markers = $("#img-markers").checked;
  status(`구획별 이미지 생성 중…`, "spin");
  try {
    const r = await window.pywebview.api.export_sections(currentPath, method, "png", markers, rows, cols);
    status(`구획 ${r.count}개 저장됨: ${r.dir}`);
  } catch (e) { status("구획 저장 오류: " + String(e), "sev-error"); }
};

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
    const viol = d.findings.filter(f => f.severity !== "info").length;
    const info = d.findings.length - viol;
    const rows = d.findings.map(f =>
      `<tr><td class="sev-${f.severity}">${f.severity}</td>
       <td>${esc(f.message)}</td>
       <td class="detail">${esc(f.detail || "")}</td>
       <td class="mono">${esc(f.context)}</td></tr>`).join("");
    $("#validate-out").innerHTML = `
      <div class="cards">
        <div class="card"><div class="num sev-warning">${viol}</div><div class="lbl">위반</div></div>
        <div class="card"><div class="num sev-info">${info}</div><div class="lbl">정보</div></div>
      </div>
      <table><thead><tr><th>심각도</th><th>요약</th><th>무엇이 / 왜 틀렸나</th><th>도면 표기</th></tr></thead><tbody>${rows}</tbody></table>`;
  }
  status(`검증: 위반 ${d.count}건`);
}

let lastTranslate = null;
function renderTranslate(d) {
  lastTranslate = d;
  $("#btn-export-csv").disabled = !d.rows.length;
  $("#btn-export-json").disabled = !d.rows.length;
  const rows = d.rows.map(r =>
    `<tr><td>${esc(r.source)}</td><td>→</td><td>${esc(r.translation)}</td></tr>`).join("");
  $("#translate-out").innerHTML = `
    <div class="cards"><div class="card"><div class="num">${d.count}</div><div class="lbl">번역 (${esc(d.backend)})</div></div></div>
    <table><thead><tr><th>원문</th><th></th><th>번역</th></tr></thead><tbody>${rows}</tbody></table>`;
  status(`번역 완료: ${d.count}건 (${d.backend}) · 내보내기 가능`);
}

async function exportTranslations(fmt) {
  if (!lastTranslate || !lastTranslate.rows.length) { status("먼저 번역하세요", "sev-warning"); return; }
  status(`${fmt.toUpperCase()} 내보내는 중…`, "spin");
  try {
    const r = await window.pywebview.api.export_translations(lastTranslate.rows, fmt);
    status(`저장됨: ${r.path} (${r.count}건)`);
  } catch (e) {
    status("내보내기 오류: " + String(e), "sev-error");
  }
}
$("#btn-export-csv").onclick = () => exportTranslations("csv");
$("#btn-export-json").onclick = () => exportTranslations("json");

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
