// AttoGrid 3D 뷰어 — three.js r128
// zone(구역) / equipment(장비) / rack(랙) 별 높이·PBR 재질
// 그림자 · EdgesGeometry 아웃라인 · 카메라 자동 맞춤 · 범례

let _3d = null;

// ── 타입별 시각화 설정 ───────────────────────────────────────────
const TYPE_CFG = {
  rack: {
    heightMult: 4.0,          // base_height 배율
    color:    0x4da3ff,
    emissive: 0x0a1a30,
    roughness: 0.25,
    metalness: 0.65,
    edge: true,
  },
  equipment: {
    heightMult: 1.8,
    color:    0x00c8a0,
    emissive: 0x003828,
    roughness: 0.35,
    metalness: 0.30,
    edge: true,
  },
  zone: {
    heightMult: 0.12,         // 바닥 슬라브처럼 얇게
    color:    0x1a3a54,
    emissive: 0x000000,
    roughness: 0.95,
    metalness: 0.00,
    edge: false,
  },
};

function _resolveColor(obj) {
  // Python 백엔드에서 넘겨준 레이어 ACI hex 색상 우선 사용 (null이면 타입 기본색)
  if (obj.color && obj.type !== "zone") {
    const n = parseInt(obj.color, 16);
    if (!isNaN(n) && n > 0) return n;
  }
  return null;
}

// ── Three.js 씬 초기화 ──────────────────────────────────────────
function _initThree(host) {
  const w = host.clientWidth || 900;
  const h = host.clientHeight || 580;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x080e16);
  scene.fog = new THREE.FogExp2(0x080e16, 0.006);

  const camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 8000);
  camera.position.set(110, 100, 145);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(w, h);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  renderer.outputEncoding = THREE.sRGBEncoding;

  host.innerHTML = "";
  host.appendChild(renderer.domElement);

  // 컨트롤
  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.07;
  controls.screenSpacePanning = false;
  controls.minDistance = 2;
  controls.maxDistance = 3000;
  controls.maxPolarAngle = Math.PI * 0.88;

  // 조명 — 3점 조명 + 반구광
  const hemi = new THREE.HemisphereLight(0x2a5080, 0x080e16, 0.9);
  scene.add(hemi);

  const sun = new THREE.DirectionalLight(0xffffff, 1.6);
  sun.position.set(80, 160, 60);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.near = 0.5;
  sun.shadow.camera.far = 1200;
  sun.shadow.camera.left = -250;
  sun.shadow.camera.right = 250;
  sun.shadow.camera.top = 250;
  sun.shadow.camera.bottom = -250;
  sun.shadow.bias = -0.0004;
  scene.add(sun);

  const fill = new THREE.DirectionalLight(0x4488cc, 0.55);
  fill.position.set(-70, 50, -90);
  scene.add(fill);

  const rim = new THREE.DirectionalLight(0x88aaff, 0.35);
  rim.position.set(0, -30, -100);
  scene.add(rim);

  // 바닥 플레인 (그림자 수신)
  const floorGeo = new THREE.PlaneGeometry(800, 800);
  const floorMat = new THREE.MeshStandardMaterial({
    color: 0x050b12, roughness: 1.0, metalness: 0.0,
  });
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);

  // 그리드
  const grid = new THREE.GridHelper(500, 50, 0x192840, 0x0e1a28);
  scene.add(grid);

  // 오브젝트 그룹 (도면 XY → 바닥 XZ)
  const group = new THREE.Group();
  group.rotation.x = -Math.PI / 2;
  scene.add(group);

  // 애니메이션 루프
  (function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  })();

  // 리사이즈
  window.addEventListener("resize", () => {
    const nw = host.clientWidth || 900;
    const nh = host.clientHeight || 580;
    camera.aspect = nw / nh;
    camera.updateProjectionMatrix();
    renderer.setSize(nw, nh);
  });

  return { scene, camera, renderer, controls, group, sun };
}

// ── 카메라 자동 맞춤 ────────────────────────────────────────────
function _fitCamera(camera, controls, group) {
  const bbox = new THREE.Box3().setFromObject(group);
  if (bbox.isEmpty()) return;
  const center = bbox.getCenter(new THREE.Vector3());
  const size   = bbox.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const dist   = maxDim * 1.6;
  // group이 -PI/2 회전이므로 world 좌표 변환 후 xz 중심 타겟
  const worldCenter = new THREE.Vector3();
  group.localToWorld(worldCenter.copy(center));
  controls.target.set(worldCenter.x, 0, worldCenter.z);
  camera.position.set(
    worldCenter.x + dist * 0.65,
    dist * 0.75,
    worldCenter.z + dist
  );
  camera.lookAt(worldCenter.x, 0, worldCenter.z);
  controls.update();
}

// ── 메인 렌더 함수 ──────────────────────────────────────────────
function renderModel3d(data) {
  const host = document.getElementById("model3d-out");
  if (!window.THREE) {
    host.innerHTML = '<div class="empty sev-error">three.js 로드 실패</div>';
    return;
  }
  if (!_3d) _3d = _initThree(host);

  // 이전 오브젝트 정리
  const g = _3d.group;
  while (g.children.length) g.remove(g.children[0]);

  const baseH  = data.base_height || 4.0;
  // 신형(objects 배열) / 구형(footprints 배열) 모두 지원
  const items  = (data.objects && data.objects.length)
    ? data.objects
    : (data.footprints || []).map(fp => ({ points: fp, type: "rack", layer: "" }));

  let drawn = 0;
  const matCache = {};

  items.forEach((obj) => {
    const pts = obj.points || [];
    if (pts.length < 3) return;

    const cfg    = TYPE_CFG[obj.type] || TYPE_CFG.rack;
    const layCol = _resolveColor(obj);
    const finalColor = layCol != null ? layCol : cfg.color;
    const objH   = baseH * cfg.heightMult;

    // Shape 생성
    const shape = new THREE.Shape();
    pts.forEach(([x, y], i) =>
      i === 0 ? shape.moveTo(x, y) : shape.lineTo(x, y)
    );
    shape.closePath();

    const geo = new THREE.ExtrudeGeometry(shape, {
      depth: objH,
      bevelEnabled: false,
    });

    // 재질 캐싱 (같은 색·타입 공유)
    const mKey = `${finalColor}_${obj.type}`;
    if (!matCache[mKey]) {
      matCache[mKey] = new THREE.MeshStandardMaterial({
        color:     finalColor,
        emissive:  cfg.emissive,
        roughness: cfg.roughness,
        metalness: cfg.metalness,
      });
    }

    const mesh = new THREE.Mesh(geo, matCache[mKey]);
    mesh.castShadow    = true;
    mesh.receiveShadow = true;
    g.add(mesh);

    // EdgesGeometry 아웃라인 (rack / equipment만)
    if (cfg.edge) {
      const edges   = new THREE.EdgesGeometry(geo, 25);
      const lineMat = new THREE.LineBasicMaterial({
        color: 0x000000, transparent: true, opacity: 0.45,
      });
      g.add(new THREE.LineSegments(edges, lineMat));
    }

    drawn++;
  });

  // 그림자 카메라 범위를 씬에 맞게 조정
  const bbox = new THREE.Box3().setFromObject(g);
  if (!bbox.isEmpty()) {
    const size = bbox.getSize(new THREE.Vector3());
    const r    = Math.max(size.x, size.y) * 0.7 + 40;
    const sh   = _3d.sun.shadow.camera;
    sh.left = sh.bottom = -r;
    sh.right = sh.top   =  r;
    sh.updateProjectionMatrix();
  }

  _fitCamera(_3d.camera, _3d.controls, g);

  // 상태 표시
  const tc = data.type_counts || {};
  const summary = [
    tc.zone      && `구역×${tc.zone}`,
    tc.equipment && `장비×${tc.equipment}`,
    tc.rack      && `랙×${tc.rack}`,
  ].filter(Boolean).join(" / ") || `전체 ${drawn}`;

  document.getElementById("status").textContent =
    `3D: ${drawn.toLocaleString()}개 오브젝트 (${summary}) · span ${data.span}`;

  // 범례 업데이트
  _updateLegend(tc);
}

// ── 범례 ────────────────────────────────────────────────────────
function _updateLegend(tc) {
  const el = document.getElementById("legend-3d");
  if (!el) return;
  const items = [
    { color: "#4da3ff", label: `랙 (${tc.rack || 0})` },
    { color: "#00c8a0", label: `장비 (${tc.equipment || 0})` },
    { color: "#1a3a54", label: `구역 (${tc.zone || 0})`, border: "#4da3ff" },
  ];
  el.innerHTML = items.map(({ color, label, border }) =>
    `<span class="leg-item">
       <span class="leg-dot" style="background:${color};${border ? `border:1px solid ${border}` : ""}"></span>
       ${label}
     </span>`
  ).join("");
  el.style.display = "flex";
}
