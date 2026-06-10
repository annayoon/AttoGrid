// 2D→3D 압출 뷰 (three.js r128, UMD 전역 THREE)
let _3d = null;

function _initThree(host) {
  const w = host.clientWidth || 800;
  const h = host.clientHeight || 520;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0f1419);

  const camera = new THREE.PerspectiveCamera(55, w / h, 0.1, 5000);
  camera.position.set(90, 90, 130);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(w, h);
  host.innerHTML = "";
  host.appendChild(renderer.domElement);

  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  scene.add(new THREE.AmbientLight(0xffffff, 0.65));
  const dir = new THREE.DirectionalLight(0xffffff, 0.85);
  dir.position.set(60, 120, 40);
  scene.add(dir);
  scene.add(new THREE.GridHelper(220, 22, 0x2d3845, 0x1a2029));

  const group = new THREE.Group();
  group.rotation.x = -Math.PI / 2; // 도면 XY평면을 바닥(XZ)으로, 압출은 위(Y)로
  scene.add(group);

  (function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  })();

  window.addEventListener("resize", () => {
    const nw = host.clientWidth, nh = host.clientHeight || 520;
    camera.aspect = nw / nh; camera.updateProjectionMatrix();
    renderer.setSize(nw, nh);
  });

  return { scene, camera, renderer, controls, group };
}

function renderModel3d(data) {
  const host = document.getElementById("model3d-out");
  if (!window.THREE) { host.innerHTML = '<div class="empty sev-error">three.js 로드 실패</div>'; return; }
  if (!_3d) _3d = _initThree(host);

  const g = _3d.group;
  while (g.children.length) g.remove(g.children[0]);

  const mat = new THREE.MeshLambertMaterial({ color: 0x4da3ff });
  let drawn = 0;
  (data.footprints || []).forEach((fp) => {
    if (fp.length < 3) return;
    const shape = new THREE.Shape();
    fp.forEach(([x, y], i) => (i ? shape.lineTo(x, y) : shape.moveTo(x, y)));
    const geo = new THREE.ExtrudeGeometry(shape, { depth: data.height, bevelEnabled: false });
    g.add(new THREE.Mesh(geo, mat));
    drawn++;
  });

  const st = document.getElementById("status");
  st.textContent = `3D 압출: 박스 ${drawn.toLocaleString()}개 (원본 span ${data.span})`;
}
