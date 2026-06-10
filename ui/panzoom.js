// SVG 확대/축소 + 이동 (CSS transform 기반, 대형 SVG 성능 고려)
(function () {
  let active = null; // {host, svg, scale, tx, ty}

  function apply(a) {
    a.svg.style.transform = `translate(${a.tx}px,${a.ty}px) scale(${a.scale})`;
  }

  // 컨테이너에 들어 있는 svg에 팬/줌 활성화 (렌더할 때마다 호출)
  window.setupPanZoom = function (host) {
    const svg = host.querySelector("svg");
    if (!svg) return;
    const a = { host, svg, scale: 1, tx: 0, ty: 0 };
    active = a;

    svg.style.transformOrigin = "0 0";
    svg.style.cursor = "grab";

    host.onwheel = function (e) {
      e.preventDefault();
      const r = host.getBoundingClientRect();
      const px = e.clientX - r.left, py = e.clientY - r.top;
      const f = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      const ns = Math.min(80, Math.max(0.3, a.scale * f));
      const k = ns / a.scale;
      a.tx = px - (px - a.tx) * k;
      a.ty = py - (py - a.ty) * k;
      a.scale = ns;
      apply(a);
    };

    let drag = false, sx = 0, sy = 0;
    host.onmousedown = function (e) {
      drag = true; sx = e.clientX - a.tx; sy = e.clientY - a.ty;
      svg.style.cursor = "grabbing"; e.preventDefault();
    };
    host.onmousemove = function (e) {
      if (!drag) return;
      a.tx = e.clientX - sx; a.ty = e.clientY - sy; apply(a);
    };
    host.onmouseup = host.onmouseleave = function () {
      drag = false; svg.style.cursor = "grab";
    };

    apply(a);
  };

  // 원래 크기/위치로 복귀
  window.resetPanZoom = function () {
    if (!active) return;
    active.scale = 1; active.tx = 0; active.ty = 0;
    apply(active);
  };
})();
