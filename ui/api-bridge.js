/**
 * api-bridge.js — AttoGrid 웹 모드 브리지
 *
 * pywebview 데스크톱 앱: window.pywebview가 이미 있으므로 아무것도 하지 않음.
 * Flask 웹 모드: window.pywebview.api 폴리필을 생성해 app.js가 그대로 동작.
 *
 * app.js는 항상 window.pywebview.api.xxx()를 호출하므로
 * 이 파일은 app.js보다 먼저 로드되어야 한다.
 */
(function () {
  // 데스크톱(pywebview) 모드: 이미 브리지가 있으므로 패스
  if (window.pywebview) return;

  /* ── 내부 유틸 ─────────────────────────────────────────── */

  async function _post(endpoint, data) {
    const r = await fetch("/api/" + endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data || {}),
    });
    const ct = r.headers.get("Content-Type") || "";
    if (!r.ok) {
      const err = ct.includes("json")
        ? await r.json().catch(() => ({}))
        : {};
      throw new Error(err.error || `서버 오류 HTTP ${r.status}`);
    }
    return r.json();
  }

  /**
   * 파일 다운로드 전용 — 서버가 바이너리/텍스트 파일을 반환하면 브라우저 다운로드 트리거.
   * 서버가 JSON { error } 를 반환하면 예외를 던진다.
   * 성공 시 { path: filename, size: bytes } 반환 (app.js 호환).
   */
  async function _download(endpoint, data, fallbackName) {
    const r = await fetch("/api/" + endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data || {}),
    });
    const ct = r.headers.get("Content-Type") || "";

    if (!r.ok || ct.includes("application/json")) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.error || `서버 오류 HTTP ${r.status}`);
    }

    const blob = await r.blob();
    const cd   = r.headers.get("Content-Disposition") || "";
    const m    = cd.match(/filename[^;=\n]*=(['"]?)([^\1;\n,]*)\1/);
    const fname = (m && m[2].trim()) || fallbackName || "download";

    const url = URL.createObjectURL(blob);
    const a   = document.createElement("a");
    a.href     = url;
    a.download = fname;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 5000);

    return { path: fname, size: blob.size };
  }

  /* ── pywebview.api 폴리필 ──────────────────────────────── */

  // 웹 모드 플래그 — pywebview 네이티브가 나중에 이 객체를 덮어쓰면
  // _isPolyfill 키도 사라지므로 app.js에서 정확히 모드를 판단할 수 있다
  window._attogridWebMode = true;

  window.pywebview = {
    _isPolyfill: true,
    api: {
      // 기본 경로 (URL 쿼리스트링 ?file=... 지원)
      default_path: () => {
        const p = new URLSearchParams(location.search).get("file");
        return Promise.resolve(p || null);
      },

      // 웹 모드에서는 파일 다이얼로그 없음 — 경로 입력 필드를 사용
      open_dialog: () => Promise.resolve(null),

      inspect:  (path)                  => _post("inspect",  { path }),
      render:   (path, max_count, h, b) => _post("render",   { path, max_count: max_count || 50000, highlights: h, boxes: b }),
      texts:    (path, translatable_only) => _post("texts",  { path, translatable_only }),
      translate:(path, backend, limit)  => _post("translate",{ path, backend, limit }),
      validate: (path)                  => _post("validate", { path }),
      model3d:  (path)                  => _post("model3d",  { path }),

      locate_voltages:  (path, include_ok)    => _post("locate_voltages",  { path, include_ok }),
      render_translated:(path, backend)       => _post("render_translated",{ path, backend }),
      partition:        (path, method, r, c)  => _post("partition",        { path, method, rows: r, cols: c }),

      // 파일 저장 → 브라우저 다운로드
      export_image: (path, fmt, markers) =>
        _download("export_image", { path, fmt, markers }, `drawing.${fmt || "png"}`),

      // 3D PNG — 서버 왕복 없이 순수 클라이언트 다운로드
      save_canvas_png: (dataUrl) => {
        if (!dataUrl) return Promise.resolve({ error: "dataUrl 없음" });
        const a   = document.createElement("a");
        a.href     = dataUrl;
        a.download = "3d_view.png";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        return Promise.resolve({ path: "3d_view.png", size: dataUrl.length });
      },

      export_translations: (rows, fmt) =>
        _download("export_translations", { rows, fmt }, `translations.${fmt || "csv"}`),

      // 번역 제자리 교체 DXF(CAD 파일) 다운로드
      export_dxf: (path, backend) =>
        _download("export_dxf", { path, backend }, "translated_ko.dxf"),

      export_sections: (path, method, fmt, markers, rows, cols) =>
        _download("export_sections", { path, method, fmt, markers, rows, cols }, "sections.zip"),

      export_section_translations: (path, method, backend, rows, cols) =>
        _download("export_section_translations",
                  { path, method, backend, rows, cols },
                  "section_translations.zip"),
    },
  };

  /* ── pywebviewready 이벤트 발화 ────────────────────────── */
  // app.js가 window.addEventListener("pywebviewready", ...) 에서 초기화를 수행하므로
  // DOM 완료 후 짧은 지연으로 발화한다.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _fire);
  } else {
    _fire();
  }

  function _fire() {
    setTimeout(() => window.dispatchEvent(new Event("pywebviewready")), 80);
  }
})();
