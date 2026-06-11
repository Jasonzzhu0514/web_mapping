import * as THREE from './vendor/three.module.js'
import { OrbitControls } from './vendor/OrbitControls.js'

const canvas = document.querySelector('#pointCanvas')
const viewportPanel = document.querySelector('.viewport-panel')
const params = new URLSearchParams(window.location.search)

const ui = {
  wsState: document.querySelector('#wsState'),
  imuState: document.querySelector('#imuState'),
  poseState: document.querySelector('#poseState'),
  radarDetailState: document.querySelector('#radarDetailState'),
  sensorHealthState: document.querySelector('#sensorHealthState'),
  clientCount: document.querySelector('#clientCount'),
  sensorDataAge: document.querySelector('#sensorDataAge'),
  radarHz: document.querySelector('#radarHz'),
  radarAge: document.querySelector('#radarAge'),
  radarTopic: document.querySelector('#radarTopic'),
  radarPoints: document.querySelector('#radarPoints'),
  poseHz: document.querySelector('#poseHz'),
  poseAge: document.querySelector('#poseAge'),
  poseX: document.querySelector('#poseX'),
  poseY: document.querySelector('#poseY'),
  poseZ: document.querySelector('#poseZ'),
  poseYaw: document.querySelector('#poseYaw'),
  poseFrame: document.querySelector('#poseFrame'),
  imuHz: document.querySelector('#imuHz'),
  imuAge: document.querySelector('#imuAge'),
  imuAccelNorm: document.querySelector('#imuAccelNorm'),
  imuGyroNorm: document.querySelector('#imuGyroNorm'),
  imuFrame: document.querySelector('#imuFrame'),
  hudFrame: document.querySelector('#hudFrame'),
  bufferPoints: document.querySelector('#bufferPoints'),
  mapPoints: document.querySelector('#mapPoints'),
  optimizedPoints: document.querySelector('#optimizedPoints'),
  rawPoints: document.querySelector('#rawPoints'),
  poseReadout: document.querySelector('#poseReadout'),
  imuReadout: document.querySelector('#imuReadout'),
  pointSize: document.querySelector('#pointSize'),
  pointSizeValue: document.querySelector('#pointSizeValue'),
  pointBudget: document.querySelector('#pointBudget'),
  pointBudgetValue: document.querySelector('#pointBudgetValue'),
  clearCloud: document.querySelector('#clearCloud'),
  layerSettingsToggle: document.querySelector('#layerSettingsToggle'),
  layerSettingsPopover: document.querySelector('#layerSettingsPopover'),
  resetView: document.querySelector('#resetView'),
  followPose: document.querySelector('#followPose'),
  layerToggles: Array.from(document.querySelectorAll('.layer-toggle')),
  sectionToggles: Array.from(document.querySelectorAll('.section-toggle')),
  backendTopicRows: Array.from(document.querySelectorAll('.topic-row')),
}

const SOURCES = ['map', 'optimized', 'raw']
const UNLIMITED_POINT_BUDGET = 10000000
const DEFAULT_VISIBLE_SOURCES = new Set(['map', 'optimized', 'raw'])
const ACCUMULATING_SOURCES = new Set(['map', 'optimized'])
const SOURCE_LABELS = {
  map: '原始地图',
  optimized: '回环地图',
  raw: '雷达实时地图',
}

const SCENE = {
  background: '#050505',
  fog: '#151515',
  coarseGrid: '#242424',
  fineGrid: '#171717',
  path: '#7c8cff',
  optimizedLow: new THREE.Color(0x242424),
  optimizedHigh: new THREE.Color(0xffffff),
  mapLow: new THREE.Color(0x191919),
  mapHigh: new THREE.Color(0xf6f6f6),
  trajectory: new THREE.Color(0x8fa5ff),
}

const GRID_HELPERS = [
  { size: 240, divisions: 240, color: SCENE.fineGrid, z: -0.024, renderOrder: -20 },
  { size: 240, divisions: 48, color: SCENE.coarseGrid, z: -0.016, renderOrder: -10 },
]

const WORLD_AXES = {
  length: 6,
  width: 2,
  radius: 0.024,
  mode: 'mesh',
  zOffset: 0.08,
  renderOrder: 10,
}

const GIZMO_AXES = {
  length: 1.5,
  width: 2,
}

const RAW_COLOR_STOPS = [
  [0.00, new THREE.Color(0x265dff)],
  [0.28, new THREE.Color(0x00d8ff)],
  [0.52, new THREE.Color(0x26e85f)],
  [0.76, new THREE.Color(0xffe447)],
  [1.00, new THREE.Color(0xff3030)],
]

const state = {
  mockMode: params.has('mock'),
  pointSize: Number(ui.pointSize.value),
  pointBudget: Number(ui.pointBudget.value),
  heartbeatTimer: null,
  bridgeConnected: false,
  visibleSources: new Set(DEFAULT_VISIBLE_SOURCES),
  layers: {},
  cloudSeq: 0,
  latestFramePoints: 0,
  renderFrameCount: 0,
  renderFpsLastAt: performance.now(),
  pose: null,
  imu: null,
  paths: {
    raw: [],
    optimized: [],
  },
  bounds: null,
  followPose: false,
  reconnectTimer: null,
  mockTimer: null,
  mockStartTime: performance.now(),
}

let ws = null
let renderer = null
let scene = null
let camera = null
let controls = null
let poseGeometry = null
let poseMarker = null
let pathLines = { raw: null, optimized: null }
let pointSprite = null
let gizmoRenderer = null
let gizmoScene = null
let gizmoCamera = null

function initThree() {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false })
  renderer.setClearColor(SCENE.background, 1)
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))

  scene = new THREE.Scene()
  scene.background = new THREE.Color(SCENE.background)
  scene.fog = new THREE.Fog(SCENE.fog, 80, 240)

  camera = new THREE.PerspectiveCamera(45, 1, 0.05, 1200)
  camera.up.set(0, 0, 1)
  camera.position.set(14, 14, 12)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.screenSpacePanning = true
  controls.minPolarAngle = 0.05
  controls.maxPolarAngle = Math.PI / 2 - 0.02
  controls.minDistance = 1.2
  controls.maxDistance = 520
  controls.target.set(0, 0, 0)
  controls.update()
  controls.addEventListener('start', () => {
    if (!state.followPose) return
    state.followPose = false
    updateFollowButton()
  })

  scene.add(new THREE.AmbientLight(0xffffff, 0.75))
  const sun = new THREE.DirectionalLight(0xffffff, 0.7)
  sun.position.set(12, 16, 10)
  scene.add(sun)

  addGroundGrid()
  addAxes(scene, WORLD_AXES)
  pointSprite = getSquarePointSprite()
  createCloudLayers()
  createPoseLayer()
  createGizmo()
  syncLayerButtons()
  resizeRenderer()
}

function addGroundGrid() {
  scene.add(...GRID_HELPERS.map(createGroundGrid))
}

function createGroundGrid({ size, divisions, color, z, renderOrder }) {
  const grid = new THREE.GridHelper(size, divisions, color, color)
  grid.rotation.x = Math.PI / 2
  grid.position.z = z
  grid.renderOrder = renderOrder
  configureHelperMaterials(grid)
  return grid
}

function addAxes(targetScene, { length, width, radius = 0.02, mode = 'line', zOffset = 0, renderOrder = 0 }) {
  const axes = [
    [[0, 0, 0], [length, 0, 0], 0xff3030],
    [[0, 0, 0], [0, length, 0], 0x15d84d],
    [[0, 0, 0], [0, 0, length], 0x265dff],
  ]
  for (const [from, to, color] of axes) {
    const start = helperPoint(from, zOffset)
    const end = helperPoint(to, zOffset)
    const axis =
      mode === 'mesh'
        ? createAxisMesh(start, end, color, radius)
        : createAxisLine(start, end, color, width)
    axis.renderOrder = renderOrder
    configureHelperMaterials(axis)
    targetScene.add(axis)
  }
}

function helperPoint(point, zOffset) {
  return new THREE.Vector3(point[0], point[1], point[2] + zOffset)
}

function createAxisLine(start, end, color, width) {
  const geometry = new THREE.BufferGeometry().setFromPoints([start, end])
  const material = new THREE.LineBasicMaterial({ color, linewidth: width, toneMapped: false })
  return new THREE.Line(geometry, material)
}

function createAxisMesh(start, end, color, radius) {
  const direction = new THREE.Vector3().subVectors(end, start)
  const length = direction.length()
  const geometry = new THREE.CylinderGeometry(radius, radius, length, 12, 1)
  const material = new THREE.MeshBasicMaterial({ color, toneMapped: false })
  const axis = new THREE.Mesh(geometry, material)
  axis.position.addVectors(start, end).multiplyScalar(0.5)
  axis.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize())
  return axis
}

function configureHelperMaterials(object) {
  const materials = Array.isArray(object.material) ? object.material : [object.material]
  for (const material of materials) {
    material.depthTest = true
    material.depthWrite = true
    material.toneMapped = false
  }
}

function createCloudLayers() {
  for (const source of SOURCES) {
    const geometry = new THREE.BufferGeometry()
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), 1000)
    const material = new THREE.PointsMaterial({
      size: pointSizeForSource(source),
      vertexColors: true,
      sizeAttenuation: false,
      map: pointSprite,
      alphaMap: pointSprite,
      transparent: true,
      opacity: opacityForSource(source),
      alphaTest: 0.36,
      depthWrite: false,
      depthTest: true,
      toneMapped: false,
    })
    const object = new THREE.Points(geometry, material)
    object.renderOrder = source === 'map' ? 0 : source === 'optimized' ? 1 : 2
    object.visible = state.visibleSources.has(source)
    scene.add(object)
    state.layers[source] = {
      source,
      geometry,
      material,
      object,
      positions: new Float32Array(0),
      colors: new Float32Array(0),
      pointCount: 0,
      framePointCount: 0,
      sourcePointCount: 0,
      seq: 0,
      topic: '-',
      hz: 0,
      bounds: null,
      intensityRange: [0, 1],
      hasIntensity: false,
    }
  }
}

function pointSizeForSource(source) {
  if (source === 'raw') return Math.max(0.7, state.pointSize * 1.08)
  if (source === 'map') return Math.max(0.5, state.pointSize * 0.72)
  return state.pointSize
}

function opacityForSource(source) {
  if (source === 'raw') return 0.96
  if (source === 'map') return 0.9
  return 0.95
}

function createPoseLayer() {
  poseGeometry = new THREE.BufferGeometry()
  const poseLine = new THREE.LineSegments(
    poseGeometry,
    new THREE.LineBasicMaterial({ vertexColors: true, toneMapped: false }),
  )
  poseMarker = new THREE.Mesh(
    new THREE.SphereGeometry(0.14, 16, 12),
    new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false }),
  )
  poseMarker.visible = false
  scene.add(poseLine)
  scene.add(poseMarker)
}

function createGizmo() {
  const gizmoCanvas = document.createElement('canvas')
  gizmoCanvas.className = 'axis-gizmo'
  viewportPanel.appendChild(gizmoCanvas)
  gizmoRenderer = new THREE.WebGLRenderer({ canvas: gizmoCanvas, antialias: true, alpha: true })
  gizmoRenderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))
  gizmoRenderer.setClearColor(0x000000, 0)
  gizmoScene = new THREE.Scene()
  gizmoCamera = new THREE.PerspectiveCamera(45, 1, 0.05, 20)
  gizmoCamera.up.set(0, 0, 1)
  addAxes(gizmoScene, GIZMO_AXES)
}

function getSquarePointSprite() {
  const size = 64
  const spriteCanvas = document.createElement('canvas')
  spriteCanvas.width = size
  spriteCanvas.height = size
  const ctx = spriteCanvas.getContext('2d')
  ctx.clearRect(0, 0, size, size)
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, size, size)
  const texture = new THREE.CanvasTexture(spriteCanvas)
  texture.colorSpace = THREE.NoColorSpace
  texture.generateMipmaps = true
  texture.minFilter = THREE.LinearMipmapLinearFilter
  texture.magFilter = THREE.LinearFilter
  texture.needsUpdate = true
  return texture
}

function connect() {
  if (state.mockMode) {
    startMockStream()
    return
  }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${window.location.host}/ws`)
  ws.binaryType = 'arraybuffer'
  setConnectionState('connecting')

  ws.addEventListener('open', () => {
    setConnectionState('connected')
    sendLayerSelection()
    startHeartbeat()
  })
  ws.addEventListener('message', (event) => {
    if (typeof event.data === 'string') {
      handleJson(JSON.parse(event.data))
    } else {
      handleCloud(event.data)
    }
  })
  ws.addEventListener('close', () => {
    setConnectionState('disconnected')
    stopHeartbeat()
    scheduleReconnect()
  })
  ws.addEventListener('error', () => {
    setConnectionState('error')
  })
}

function sendLayerSelection() {
  if (state.mockMode || ws?.readyState !== WebSocket.OPEN) return
  ws.send(JSON.stringify({ type: 'set_sources', sources: [...state.visibleSources] }))
}

function startMockStream() {
  setConnectionState('mock')
  setConnectionPill(connectionStateFromHealth('online'))
  const topicBySource = {
    raw: '/livox/lidar',
    optimized: 'corrected_current_pcd',
    map: 'corrected_map',
  }
  let ticks = 0
  if (state.mockTimer) window.clearInterval(state.mockTimer)
  state.mockTimer = window.setInterval(() => {
    const elapsed = (performance.now() - state.mockStartTime) / 1000
    ticks += 1
    for (const source of SOURCES) {
      if (!state.visibleSources.has(source)) continue
      if (source === 'map' && ticks % 12 !== 1) continue
      const count = source === 'map' ? 36000 : source === 'raw' ? 12000 : 14000
      const values = buildMockCloud(count, elapsed, source)
      appendPoints(values, {
        seq: state.cloudSeq + 1,
        source,
        source_point_count: count,
        topic: topicBySource[source],
        has_intensity: true,
        intensity_range: [0, 1],
        bounds: {
          min: [-18, -16, -2],
          max: [18, 16, 7],
        },
      })
    }
    updatePose({
      type: 'pose',
      x: Math.cos(elapsed * 0.35) * 5.8,
      y: Math.sin(elapsed * 0.35) * 4.4,
      z: 1.1 + Math.sin(elapsed * 0.7) * 0.2,
      yaw: elapsed * 0.35 + Math.PI / 2,
    })
    updateImu({
      type: 'imu',
      topic: '/livox/imu',
      frame_id: 'livox_frame',
      angular_velocity: [
        Math.sin(elapsed * 0.8) * 0.05,
        Math.cos(elapsed * 0.6) * 0.05,
        0.18 + Math.sin(elapsed * 0.35) * 0.03,
      ],
      linear_acceleration: [
        Math.sin(elapsed * 0.9) * 0.12,
        Math.cos(elapsed * 0.7) * 0.12,
        9.81 + Math.sin(elapsed * 1.1) * 0.08,
      ],
      gyro_norm: 0.19,
      accel_norm: 9.81,
    })
    updatePath({
      type: 'path',
      source: 'optimized',
      points: buildMockPath(elapsed),
    })
    updateStatus({
      type: 'status',
      client_count: 1,
      lidar: {
        state: 'online',
        status_text: 'mock mapping stream',
        raw_topic: '/livox/lidar',
      },
      topics: {
        raw: mockTopic('raw', topicBySource.raw, state.visibleSources.has('raw') ? 10 : 0),
        optimized: mockTopic('optimized', topicBySource.optimized, 10),
        map: mockTopic('map', topicBySource.map, 1),
        pose: mockTopic('pose', 'pose_stamped', 10),
        imu: mockTopic('imu', '/livox/imu', 100),
      },
    })
  }, 100)
}

function mockTopic(source, topic, hz) {
  const layer = state.layers[source]
  return {
    topic,
    hz,
    frames: state.cloudSeq,
    state: hz > 0 ? 'online' : 'waiting',
    last_points: layer?.sourcePointCount || 1,
    last_sampled_points: layer?.framePointCount || 1,
  }
}

function buildMockCloud(pointCount, elapsed, source) {
  const values = new Float32Array(pointCount * 4)
  for (let i = 0; i < pointCount; i += 1) {
    const t = i / Math.max(1, pointCount - 1)
    const ring = (i % 480) * (Math.PI / 240)
    const lane = Math.floor(i / 480) % 18
    const pass = Math.floor(i / (480 * 18))
    const corridor = (lane - 9) * 1.35
    const length = (t * 2 - 1) * 28
    const curve = Math.sin(length * 0.12 + pass * 0.4) * 4.5
    const sourceOffset = source === 'raw' ? Math.sin(elapsed * 1.5 + ring) * 0.45 : 0
    const idx = i * 4
    if (source === 'map') {
      values[idx] = length
      values[idx + 1] = corridor + Math.sin(length * 0.18) * 1.2
      values[idx + 2] = -0.8 + Math.sin(ring * 3 + pass) * 0.25 + (pass % 5) * 0.18
    } else {
      const radius = 2.8 + (lane / 18) * 10
      values[idx] = Math.cos(ring) * radius + Math.cos(elapsed * 0.35) * 5.8 + sourceOffset
      values[idx + 1] = Math.sin(ring) * radius + Math.sin(elapsed * 0.35) * 4.4
      values[idx + 2] = -1 + (lane / 18) * 6 + Math.sin(ring * 4 + elapsed) * 0.18
    }
    values[idx + 3] = (Math.sin(ring * 4 + elapsed + pass) + 1) * 0.5
  }
  return values
}

function buildMockPath(elapsed) {
  const points = []
  for (let i = 0; i < 240; i += 1) {
    const t = elapsed * 0.35 - (240 - i) * 0.012
    points.push([Math.cos(t) * 5.8, Math.sin(t) * 4.4, 1.1 + Math.sin(t * 2) * 0.2])
  }
  return points
}

function startHeartbeat() {
  stopHeartbeat()
  state.heartbeatTimer = window.setInterval(() => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ping', time: Date.now() }))
    }
  }, 20000)
}

function stopHeartbeat() {
  if (!state.heartbeatTimer) return
  window.clearInterval(state.heartbeatTimer)
  state.heartbeatTimer = null
}

function scheduleReconnect() {
  if (state.reconnectTimer) return
  state.reconnectTimer = window.setTimeout(() => {
    state.reconnectTimer = null
    connect()
  }, 1200)
}

function setConnectionState(label) {
  state.bridgeConnected = label === 'connected' || label === 'mock'
  if (!state.bridgeConnected) markBridgeOffline(label)
}

function markBridgeOffline(label) {
  const offlineState = 'stale'
  const topics = offlineTopics(offlineState)
  setStatePill(ui.radarDetailState, offlineState)
  setStatePill(ui.imuState, offlineState)
  setStatePill(ui.poseState, offlineState)
  setConnectionPill('disconnected')
  setStatePill(ui.sensorHealthState, offlineState)
  ui.clientCount.textContent = '0'
  ui.radarHz.textContent = '0.00 Hz'
  ui.radarAge.textContent = '-'
  ui.radarTopic.textContent = '-'
  ui.radarPoints.textContent = '0'
  ui.poseHz.textContent = '0.00 Hz'
  ui.poseAge.textContent = '-'
  ui.imuHz.textContent = '0.00 Hz'
  ui.imuAge.textContent = '-'
  ui.sensorDataAge.textContent = '-'
  updatePipelineStatus(topics)
  updateBackendDetails(topics)
}

function offlineTopics(stateText) {
  return {
    raw: { state: stateText },
    optimized: { state: stateText },
    map: { state: stateText },
    pose: { state: stateText },
    imu: { state: stateText },
    optimized_path: { state: stateText },
  }
}

function handleJson(payload) {
  if (payload.type === 'status') updateStatus(payload)
  if (!state.bridgeConnected) return
  if (payload.type === 'pose') updatePose(payload)
  if (payload.type === 'imu') updateImu(payload)
  if (payload.type === 'path') updatePath(payload)
  if (payload.type === 'selected_sources' || payload.type === 'hello') {
    const selectedSources = payload.selected_sources
    if (Array.isArray(selectedSources)) {
      state.visibleSources = new Set(selectedSources.filter((source) => SOURCES.includes(source)))
      syncLayerVisibility()
      syncLayerButtons()
      updatePointUi()
    }
  }
}

function handleCloud(buffer) {
  if (!state.bridgeConnected) return
  const view = new DataView(buffer)
  const headerLength = view.getUint32(0, true)
  const dataOffset = view.getUint32(4, true)
  const headerText = new TextDecoder().decode(buffer.slice(8, 8 + headerLength))
  const header = JSON.parse(headerText)
  if (!SOURCES.includes(header.source)) return
  const values = new Float32Array(buffer, dataOffset)
  appendPoints(values, header)
}

function appendPoints(values, header) {
  const source = header.source
  const layer = state.layers[source]
  if (!layer) return
  const incomingPoints = Math.floor(values.length / 4)
  const maxPoints = sourceBudget(source)
  const unlimited = !Number.isFinite(maxPoints)
  const shouldAccumulate = ACCUMULATING_SOURCES.has(source)
  const existingPoints = shouldAccumulate ? layer.pointCount : 0
  const keepPoints = shouldAccumulate
    ? unlimited
      ? existingPoints
      : Math.max(0, Math.min(existingPoints, maxPoints - incomingPoints))
    : 0
  const nextPoints = unlimited ? keepPoints + incomingPoints : Math.min(maxPoints, keepPoints + incomingPoints)
  const nextPositions = new Float32Array(nextPoints * 3)
  const nextColors = new Float32Array(nextPoints * 3)
  if (keepPoints > 0) {
    const oldStart = existingPoints - keepPoints
    nextPositions.set(layer.positions.subarray(oldStart * 3, existingPoints * 3), 0)
    nextColors.set(layer.colors.subarray(oldStart * 3, existingPoints * 3), 0)
  }

  const incomingStart = unlimited ? 0 : Math.max(0, incomingPoints - maxPoints)
  const incomingKeep = incomingPoints - incomingStart
  const incomingOffset = keepPoints * 3
  const range = header.intensity_range || layer.intensityRange || [0, 1]
  const hasIntensity = Boolean(header.has_intensity)
  for (let i = 0; i < incomingKeep; i += 1) {
    const sourceIndex = (incomingStart + i) * 4
    const targetIndex = incomingOffset + i * 3
    nextPositions[targetIndex] = values[sourceIndex]
    nextPositions[targetIndex + 1] = values[sourceIndex + 1]
    nextPositions[targetIndex + 2] = values[sourceIndex + 2]
    writePointColor(nextColors, targetIndex, source, hasIntensity ? values[sourceIndex + 3] : null, range)
  }

  layer.positions = nextPositions
  layer.colors = nextColors
  layer.pointCount = nextPoints
  layer.framePointCount = incomingPoints
  layer.sourcePointCount = header.source_point_count || incomingPoints
  layer.seq = header.seq || layer.seq + 1
  layer.topic = header.topic || '-'
  layer.bounds = header.bounds || layer.bounds
  layer.intensityRange = range
  layer.hasIntensity = hasIntensity
  state.cloudSeq = Math.max(state.cloudSeq, layer.seq)
  state.latestFramePoints = incomingPoints
  state.bounds = unionBounds(state.bounds, layer.bounds)
  uploadLayer(layer)
  if (layer.pointCount > 0 && layer.bounds) {
    recenterCamera(layer.bounds, source)
  }
  updatePointUi()
}

function sourceBudget(source) {
  if (state.pointBudget >= UNLIMITED_POINT_BUDGET) return Number.POSITIVE_INFINITY
  if (source === 'map') return Math.max(20000, Math.floor(state.pointBudget * 0.6))
  if (source === 'optimized') return Math.max(15000, Math.floor(state.pointBudget * 0.3))
  return Math.max(10000, Math.floor(state.pointBudget * 0.1))
}

function writePointColor(colors, offset, source, intensity, range) {
  const t = intensityTone(intensity, range)
  if (source === 'optimized') {
    writeGradientColor(colors, offset, SCENE.optimizedLow, SCENE.optimizedHigh, t)
    return
  }
  if (source === 'raw') {
    writeRawScanColor(colors, offset, t)
    return
  }
  writeGradientColor(colors, offset, SCENE.mapLow, SCENE.mapHigh, t)
}

function intensityTone(intensity, range) {
  if (intensity === null) return 0.72
  const normalized = clamp((intensity - range[0]) / Math.max(0.0001, range[1] - range[0]), 0, 1)
  return Math.pow(normalized, 0.55)
}

function writeGradientColor(colors, offset, low, high, t) {
  colors[offset] = low.r + (high.r - low.r) * t
  colors[offset + 1] = low.g + (high.g - low.g) * t
  colors[offset + 2] = low.b + (high.b - low.b) * t
}

function writeRawScanColor(colors, offset, t) {
  for (let i = 1; i < RAW_COLOR_STOPS.length; i += 1) {
    if (t > RAW_COLOR_STOPS[i][0]) continue
    const [leftAt, leftColor] = RAW_COLOR_STOPS[i - 1]
    const [rightAt, rightColor] = RAW_COLOR_STOPS[i]
    const localT = clamp((t - leftAt) / Math.max(0.0001, rightAt - leftAt), 0, 1)
    writeGradientColor(colors, offset, leftColor, rightColor, localT)
    return
  }
  const lastColor = RAW_COLOR_STOPS[RAW_COLOR_STOPS.length - 1][1]
  writeGradientColor(colors, offset, lastColor, lastColor, 1)
}

function uploadLayer(layer) {
  layer.geometry.setAttribute('position', new THREE.BufferAttribute(layer.positions, 3))
  layer.geometry.setAttribute('color', new THREE.BufferAttribute(layer.colors, 3))
  layer.geometry.setDrawRange(0, layer.pointCount)
  layer.geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), 1000)
  layer.material.size = pointSizeForSource(layer.source)
  layer.material.opacity = opacityForSource(layer.source)
  layer.material.vertexColors = true
  layer.material.needsUpdate = true
}

function updateStatus(payload) {
  const topics = payload.topics || {}
  const lidarState = payload.lidar?.state || 'waiting'
  const rawTopic = topics.raw || {}
  const imuTopic = topics.imu || {}
  const poseTopic = topics.pose || {}
  const healthState = sensorHealth(topics, lidarState)
  setStatePill(ui.radarDetailState, lidarState)
  setStatePill(ui.imuState, imuTopic.state || 'waiting')
  setStatePill(ui.poseState, poseTopic.state || 'waiting')
  setConnectionPill(connectionStateFromHealth(healthState))
  setStatePill(ui.sensorHealthState, healthState)
  ui.clientCount.textContent = String(payload.client_count ?? 0)
  ui.radarHz.textContent = `${formatHz(rawTopic.hz)} Hz`
  ui.radarAge.textContent = formatAge(rawTopic.age_sec)
  ui.radarTopic.textContent = rawTopic.topic || payload.lidar?.raw_topic || '-'
  ui.radarPoints.textContent = compact(rawTopic.last_points || 0)
  ui.poseHz.textContent = `${formatHz(poseTopic.hz)} Hz`
  ui.poseAge.textContent = formatAge(poseTopic.age_sec)
  ui.imuHz.textContent = `${formatHz(imuTopic.hz)} Hz`
  ui.imuAge.textContent = formatAge(imuTopic.age_sec)
  ui.sensorDataAge.textContent = latestDataAge([rawTopic, imuTopic, poseTopic])
  for (const source of SOURCES) {
    if (state.layers[source]) state.layers[source].hz = topics[source]?.hz || 0
  }
  updatePipelineStatus(topics)
  updateBackendDetails(topics)
  if (payload.pose) updatePose(payload.pose)
  if (payload.imu) updateImu(payload.imu)
  updatePointUi()
}

function setStatePill(element, stateText) {
  if (!element) return
  const next = stateText || 'waiting'
  element.textContent = next
  element.classList.remove('is-online', 'is-stale', 'is-waiting', 'is-disconnected')
  element.classList.add(`is-${next}`)
}

function setConnectionPill(stateText) {
  if (!ui.wsState) return
  const next = stateText || 'connecting'
  ui.wsState.textContent = next
  ui.wsState.classList.remove('is-online', 'is-stale', 'is-waiting', 'is-disconnected')
  const className = next === 'connected'
    ? 'is-online'
    : next === 'disconnected'
      ? 'is-disconnected'
      : 'is-waiting'
  ui.wsState.classList.add(className)
}

function connectionStateFromHealth(healthState) {
  if (healthState === 'online') return 'connected'
  if (healthState === 'waiting') return 'connecting'
  return 'disconnected'
}

function sensorHealth(topics, lidarState) {
  return lidarState || topics.raw?.state || 'waiting'
}

function latestDataAge(stats) {
  const ages = stats
    .map((stat) => stat?.age_sec)
    .filter((age) => Number.isFinite(age))
  if (ages.length === 0) return '-'
  return formatAge(Math.min(...ages))
}

function formatAge(value) {
  if (!Number.isFinite(value)) return '-'
  if (value < 1) return `${Math.round(value * 1000)} ms`
  return `${Number(value).toFixed(1)} s`
}

function updatePipelineStatus(topics) {
  for (const source of SOURCES) {
    setLayerButtonStatus(source, topics[source] || {})
  }
}

function updateBackendDetails(topics) {
  for (const row of ui.backendTopicRows) {
    const stat = topics[row.dataset.topicKey] || {}
    const stateText = stat.state || 'waiting'
    const stateEl = row.querySelector('.topic-state')
    const metaEl = row.querySelector('.topic-meta')
    if (stateEl) {
      stateEl.textContent = stateText
      stateEl.className = `topic-state is-${stateText}`
    }
    if (metaEl) metaEl.textContent = topicMeta(stat)
    row.title = stat.topic ? `${stat.topic} ${stateText}` : stateText
  }
}

function topicMeta(stat) {
  if (!stat.topic) return '-'
  const parts = [stat.topic]
  if (Number.isFinite(stat.hz)) parts.push(`${formatHz(stat.hz)} Hz`)
  if (Number.isFinite(stat.age_sec)) parts.push(`age ${Number(stat.age_sec).toFixed(1)}s`)
  if (Number.isFinite(stat.last_points) && stat.last_points > 0) {
    parts.push(`${compact(stat.last_points)} pts`)
  }
  if (
    Number.isFinite(stat.last_sampled_points)
    && stat.last_sampled_points > 0
    && stat.last_sampled_points !== stat.last_points
  ) {
    parts.push(`${compact(stat.last_sampled_points)} shown`)
  }
  return parts.join(' · ')
}

function setLayerButtonStatus(source, stat) {
  const button = ui.layerToggles.find((item) => item.dataset.source === source)
  if (!button) return
  const stateText = stat.state || 'waiting'
  const online = stateText === 'online'
  const selected = state.visibleSources.has(source)
  button.classList.toggle('is-available', online)
  button.classList.toggle('is-unavailable', !online)
  button.classList.toggle('is-standby', online && !selected)
  button.disabled = !online
  button.setAttribute('aria-disabled', String(!online))
  if (state.bridgeConnected && !online && selected) {
    state.visibleSources.delete(source)
    syncLayerVisibility()
    syncLayerButtons()
    syncPathVisibility()
    sendLayerSelection()
  }
  button.title = `${SOURCE_LABELS[source]}: ${stateText}${stat.topic ? ` (${stat.topic})` : ''}`
  const status = button.querySelector('.layer-status')
  if (status) {
    status.textContent = online ? `${formatHz(stat.hz)} Hz` : stateText
  }
}

function updatePose(payload) {
  state.pose = payload
  if (state.followPose && Number.isFinite(payload.x) && Number.isFinite(payload.y) && Number.isFinite(payload.z)) {
    setControlsTarget([payload.x, payload.y, payload.z], true)
  }
  updatePoseObject()
  const yawDeg = Number.isFinite(payload.yaw) ? (payload.yaw * 180) / Math.PI : null
  ui.poseX.textContent = fmt(payload.x)
  ui.poseY.textContent = fmt(payload.y)
  ui.poseZ.textContent = fmt(payload.z)
  ui.poseYaw.textContent = yawDeg === null ? '-' : fmt(yawDeg)
  ui.poseFrame.textContent = payload.frame_id || '-'
  ui.poseReadout.innerHTML = [
    metricLine('X', fmt(payload.x), 'm'),
    metricLine('Y', fmt(payload.y), 'm'),
    metricLine('Z', fmt(payload.z), 'm'),
    metricLine('Yaw', yawDeg === null ? '-' : fmt(yawDeg), 'deg'),
  ].join('')
}

function updateImu(payload) {
  state.imu = payload
  const accel = payload.linear_acceleration || []
  const gyro = payload.angular_velocity || []
  const accelNorm = Number.isFinite(payload.accel_norm) ? payload.accel_norm : vectorNorm(accel)
  const gyroNorm = Number.isFinite(payload.gyro_norm) ? payload.gyro_norm : vectorNorm(gyro)
  ui.imuAccelNorm.textContent = fmt(accelNorm)
  ui.imuGyroNorm.textContent = fmt(gyroNorm)
  ui.imuFrame.textContent = payload.frame_id || '-'
  ui.imuReadout.innerHTML = [
    metricLine('Acc X', fmt(accel[0]), 'm/s2'),
    metricLine('Acc Y', fmt(accel[1]), 'm/s2'),
    metricLine('Acc Z', fmt(accel[2]), 'm/s2'),
    metricLine('|Acc|', fmt(accelNorm), 'm/s2'),
    metricLine('Gyro X', fmt(gyro[0]), 'rad/s'),
    metricLine('Gyro Y', fmt(gyro[1]), 'rad/s'),
    metricLine('Gyro Z', fmt(gyro[2]), 'rad/s'),
    metricLine('|Gyro|', fmt(gyroNorm), 'rad/s'),
  ].join('')
}

function metricLine(label, value, unit) {
  return `<div class="metric-line"><span>${label}</span><strong>${value}</strong><em>${unit}</em></div>`
}

function updatePoseObject() {
  if (!state.pose || !Number.isFinite(state.pose.x)) return
  const p = [state.pose.x, state.pose.y, state.pose.z]
  const yaw = Number.isFinite(state.pose.yaw) ? state.pose.yaw : 0
  const tip = [p[0] + Math.cos(yaw) * 1.2, p[1] + Math.sin(yaw) * 1.2, p[2]]
  const positions = new Float32Array([
    p[0] - 0.4, p[1], p[2], p[0] + 0.4, p[1], p[2],
    p[0], p[1] - 0.4, p[2], p[0], p[1] + 0.4, p[2],
    p[0], p[1], p[2], tip[0], tip[1], tip[2],
  ])
  const colors = new Float32Array([
    1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1,
    1, 0.84, 0.24, 1, 0.84, 0.24,
  ])
  poseGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  poseGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  poseMarker.position.set(p[0], p[1], p[2])
  poseMarker.visible = true
}

function updatePath(payload) {
  if (payload.source === 'raw' || payload.source === 'optimized') {
    state.paths[payload.source] = payload.points || []
    updatePathObject(payload.source)
  }
}

function updatePathObject(source) {
  const points = state.paths[source] || []
  if (pathLines[source]) {
    scene.remove(pathLines[source])
    pathLines[source].geometry.dispose()
    pathLines[source].material.dispose()
    pathLines[source] = null
  }
  if (points.length < 2) {
    syncPathVisibility()
    return
  }
  const geometry = new THREE.BufferGeometry().setFromPoints(
    points.map((point) => new THREE.Vector3(point[0], point[1], point[2])),
  )
  const material = new THREE.LineBasicMaterial({
    color: SCENE.trajectory,
    transparent: true,
    opacity: 0.92,
    toneMapped: false,
  })
  pathLines[source] = new THREE.Line(geometry, material)
  scene.add(pathLines[source])
  syncPathVisibility()
}

function syncPathVisibility() {
  if (pathLines.raw) pathLines.raw.visible = state.visibleSources.has('raw')
  if (pathLines.optimized) pathLines.optimized.visible = state.visibleSources.has('optimized')
}

function updatePointUi() {
  const totalPoints = SOURCES.reduce((sum, source) => sum + (state.layers[source]?.pointCount || 0), 0)
  ui.pointSizeValue.textContent = `${state.pointSize.toFixed(1)} px`
  ui.pointBudgetValue.textContent = state.pointBudget >= UNLIMITED_POINT_BUDGET ? '全部' : compact(state.pointBudget)
  ui.bufferPoints.textContent = compact(totalPoints)
  ui.mapPoints.textContent = compact(state.layers.map?.pointCount || 0)
  ui.optimizedPoints.textContent = compact(state.layers.optimized?.pointCount || 0)
  ui.rawPoints.textContent = compact(state.layers.raw?.pointCount || 0)
}

function toggleLayer(source) {
  if (!SOURCES.includes(source)) return
  const button = ui.layerToggles.find((item) => item.dataset.source === source)
  if (button?.disabled) return
  if (state.visibleSources.has(source)) {
    state.visibleSources.delete(source)
  } else {
    state.visibleSources.add(source)
  }
  syncLayerVisibility()
  syncLayerButtons()
  syncPathVisibility()
  updatePointUi()
  sendLayerSelection()
}

function syncLayerVisibility() {
  for (const source of SOURCES) {
    if (state.layers[source]) state.layers[source].object.visible = state.visibleSources.has(source)
  }
}

function syncLayerButtons() {
  for (const button of ui.layerToggles) {
    const source = button.dataset.source
    const active = state.visibleSources.has(source)
    button.classList.toggle('is-active', active)
    button.classList.toggle('is-standby', button.classList.contains('is-available') && !active)
    button.setAttribute('aria-pressed', String(active))
  }
}

function clearCloud() {
  for (const source of SOURCES) {
    const layer = state.layers[source]
    layer.positions = new Float32Array(0)
    layer.colors = new Float32Array(0)
    layer.pointCount = 0
    layer.framePointCount = 0
    layer.sourcePointCount = 0
    layer.bounds = null
    uploadLayer(layer)
  }
  state.bounds = null
  state.latestFramePoints = 0
  updatePointUi()
}

function recenterCamera(bounds, source) {
  const totalPoints = SOURCES.reduce((sum, key) => sum + (state.layers[key]?.pointCount || 0), 0)
  if (!bounds || totalPoints > state.latestFramePoints || state.followPose) return
  if (source === 'raw') return
  const target = boundsCenter(bounds)
  const span = boundsSpan(bounds)
  setView(target, Math.max(8, Math.min(240, span * 1.8)))
}

function setView(target, distance) {
  const direction = new THREE.Vector3(13, 12, 9).normalize().multiplyScalar(distance)
  camera.up.set(0, 0, 1)
  controls.target.set(target[0], target[1], target[2])
  camera.position.copy(controls.target).add(direction)
  controls.update()
}

function setControlsTarget(target, preserveOffset) {
  const offset = camera.position.clone().sub(controls.target)
  controls.target.set(target[0], target[1], target[2])
  if (preserveOffset) {
    camera.position.copy(controls.target).add(offset)
  }
  controls.update()
}

function resetCameraView() {
  const target = state.bounds ? boundsCenter(state.bounds) : state.pose && Number.isFinite(state.pose.x)
    ? [state.pose.x, state.pose.y, state.pose.z]
    : [0, 0, 0]
  const span = state.bounds ? boundsSpan(state.bounds) : 20
  state.followPose = false
  updateFollowButton()
  setView(target, Math.max(8, Math.min(240, span * 1.8)))
}

function toggleFollowPose() {
  state.followPose = !state.followPose
  if (state.followPose && state.pose && Number.isFinite(state.pose.x)) {
    setControlsTarget([state.pose.x, state.pose.y, state.pose.z], true)
  }
  updateFollowButton()
}

function updateFollowButton() {
  ui.followPose.classList.toggle('is-active', state.followPose)
  ui.followPose.setAttribute('aria-pressed', String(state.followPose))
  ui.resetView.disabled = state.followPose
}

function resizeRenderer() {
  const width = Math.max(1, canvas.clientWidth)
  const height = Math.max(1, canvas.clientHeight)
  renderer.setSize(width, height, false)
  camera.aspect = width / height
  camera.updateProjectionMatrix()

  if (gizmoRenderer) {
    const size = 112
    gizmoRenderer.setSize(size, size, false)
    gizmoCamera.aspect = 1
    gizmoCamera.updateProjectionMatrix()
  }
}

function render() {
  resizeRenderer()
  controls.update()
  renderer.render(scene, camera)
  renderGizmo()
  updateRenderFps()
  requestAnimationFrame(render)
}

function updateRenderFps() {
  state.renderFrameCount += 1
  const now = performance.now()
  const elapsed = now - state.renderFpsLastAt
  if (elapsed < 500) return
  const fps = (state.renderFrameCount * 1000) / elapsed
  ui.hudFrame.textContent = `${fps.toFixed(0)} FPS`
  state.renderFrameCount = 0
  state.renderFpsLastAt = now
}

function renderGizmo() {
  if (!gizmoRenderer || !gizmoScene || !gizmoCamera) return
  const direction = camera.position.clone().sub(controls.target).normalize().multiplyScalar(4)
  gizmoCamera.position.copy(direction)
  gizmoCamera.up.copy(camera.up)
  gizmoCamera.lookAt(0, 0, 0)
  gizmoRenderer.render(gizmoScene, gizmoCamera)
}

for (const button of ui.layerToggles) {
  button.addEventListener('click', () => toggleLayer(button.dataset.source))
}

for (const button of ui.sectionToggles) {
  button.addEventListener('click', () => {
    const section = button.closest('.panel-section')
    if (!section) return
    const collapsed = section.classList.toggle('is-collapsed')
    button.setAttribute('aria-expanded', String(!collapsed))
  })
}

ui.layerSettingsToggle.addEventListener('click', () => {
  setLayerSettingsOpen(ui.layerSettingsPopover.hidden)
})

document.addEventListener('pointerdown', (event) => {
  if (ui.layerSettingsPopover.hidden) return
  const target = event.target
  if (ui.layerSettingsPopover.contains(target) || ui.layerSettingsToggle.contains(target)) return
  setLayerSettingsOpen(false)
})

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || ui.layerSettingsPopover.hidden) return
  setLayerSettingsOpen(false)
  ui.layerSettingsToggle.focus()
})

function setLayerSettingsOpen(open) {
  ui.layerSettingsPopover.hidden = !open
  ui.layerSettingsToggle.classList.toggle('is-open', open)
  ui.layerSettingsToggle.setAttribute('aria-expanded', String(open))
}

ui.pointSize.addEventListener('input', () => {
  state.pointSize = Number(ui.pointSize.value)
  for (const source of SOURCES) {
    state.layers[source].material.size = pointSizeForSource(source)
  }
  updatePointUi()
})

ui.pointBudget.addEventListener('input', () => {
  state.pointBudget = Number(ui.pointBudget.value)
  trimLayersToBudget()
  updatePointUi()
})

ui.clearCloud.addEventListener('click', clearCloud)
ui.resetView.addEventListener('click', resetCameraView)
ui.followPose.addEventListener('click', toggleFollowPose)
window.addEventListener('resize', resizeRenderer)

function trimLayersToBudget() {
  for (const source of SOURCES) {
    const layer = state.layers[source]
    const budget = sourceBudget(source)
    if (!Number.isFinite(budget)) continue
    if (layer.pointCount <= budget) continue
    const start = layer.pointCount - budget
    layer.positions = layer.positions.subarray(start * 3).slice()
    layer.colors = layer.colors.subarray(start * 3).slice()
    layer.pointCount = budget
    uploadLayer(layer)
  }
}

function unionBounds(a, b) {
  if (!b) return a
  if (!a) return { min: [...b.min], max: [...b.max] }
  return {
    min: [
      Math.min(a.min[0], b.min[0]),
      Math.min(a.min[1], b.min[1]),
      Math.min(a.min[2], b.min[2]),
    ],
    max: [
      Math.max(a.max[0], b.max[0]),
      Math.max(a.max[1], b.max[1]),
      Math.max(a.max[2], b.max[2]),
    ],
  }
}

function boundsCenter(bounds) {
  return [
    (bounds.min[0] + bounds.max[0]) * 0.5,
    (bounds.min[1] + bounds.max[1]) * 0.5,
    (bounds.min[2] + bounds.max[2]) * 0.5,
  ]
}

function boundsSpan(bounds) {
  return Math.max(
    bounds.max[0] - bounds.min[0],
    bounds.max[1] - bounds.min[1],
    bounds.max[2] - bounds.min[2],
  )
}

function formatHz(value) {
  return Number.isFinite(value) ? Number(value).toFixed(value >= 10 ? 1 : 2) : '0.00'
}

function fmt(value) {
  return Number.isFinite(value) ? Number(value).toFixed(3) : '-'
}

function compact(value) {
  if (!Number.isFinite(value)) return '0'
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`
  return String(value)
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function vectorNorm(values) {
  if (!Array.isArray(values) || values.length === 0) return NaN
  return Math.sqrt(values.reduce((sum, value) => sum + Number(value) * Number(value), 0))
}

initThree()
connect()
render()
