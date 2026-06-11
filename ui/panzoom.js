// SVG 확대/축소 + 이동 — viewBox 직접 조작 방식
//
// ❌ 기존: svg.style.transform = scale() → SVG를 비트맵으로 합성 후 확대 → 흐림
// ✅ 신규: viewBox 속성 변경 → SVG가 매 프레임 벡터로 재렌더 → 어떤 줌에서도 선명
(function () {
  let active = null; // {host, svg, vb:{x,y,w,h}, orig:{...}}

  function applyVB(a) {
    a.svg.setAttribute("viewBox",
      `${a.vb.x} ${a.vb.y} ${a.vb.w} ${a.vb.h}`);
  }

  // 컨테이너 안의 SVG에 팬/줌 활성화
  window.setupPanZoom = function (host) {
    const svg = host.querySelector("svg");
    if (!svg) return;

    const vbBase = svg.viewBox.baseVal;
    if (!vbBase || !vbBase.width) return;

    const orig = { x: vbBase.x, y: vbBase.y, w: vbBase.width, h: vbBase.height };
    const a    = { host, svg, vb: { ...orig }, orig };
    active = a;

    // 이전 CSS transform 잔재 제거
    svg.style.transform       = "";
    svg.style.transformOrigin = "";
    svg.style.cursor          = "grab";

    // ── 줌 (휠) ──────────────────────────────────────
    host.onwheel = function (e) {
      e.preventDefault();
      const r = svg.getBoundingClientRect();
      if (!r.width) return;
      // 마우스 포인터를 SVG 좌표로 환산
      const mx = a.vb.x + (e.clientX - r.left) / r.width  * a.vb.w;
      const my = a.vb.y + (e.clientY - r.top)  / r.height * a.vb.h;
      const f  = e.deltaY < 0 ? 1 / 1.15 : 1.15;        // 줌 인/아웃 배율
      a.vb.w *= f;
      a.vb.h *= f;
      // 마우스 아래 좌표가 고정되도록 원점 보정
      a.vb.x = mx - (e.clientX - r.left) / r.width  * a.vb.w;
      a.vb.y = my - (e.clientY - r.top)  / r.height * a.vb.h;
      applyVB(a);
    };

    // ── 드래그 이동 ───────────────────────────────────
    let drag = false, px = 0, py = 0;
    host.onmousedown = function (e) {
      drag = true; px = e.clientX; py = e.clientY;
      svg.style.cursor = "grabbing"; e.preventDefault();
    };
    host.onmousemove = function (e) {
      if (!drag) return;
      const r = svg.getBoundingClientRect();
      if (!r.width) return;
      // 드래그 델타를 SVG 좌표 변화량으로 환산
      a.vb.x -= (e.clientX - px) / r.width  * a.vb.w;
      a.vb.y -= (e.clientY - py) / r.height * a.vb.h;
      px = e.clientX; py = e.clientY;
      applyVB(a);
    };
    host.onmouseup = host.onmouseleave = function () {
      drag = false; svg.style.cursor = "grab";
    };
  };

  // 원래 크기/위치로 복귀
  window.resetPanZoom = function () {
    if (!active) return;
    active.vb = { ...active.orig };
    applyVB(active);
  };
})();
