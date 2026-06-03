import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { GraphLink, GraphNode } from "../api/types";
import { linkMatchesLens, nodeMatchesLens, riskColor, type RiskLens } from "../graph/lenses";
import type { GraphSelection } from "../graph/selection";
import { getFocusTarget, getLinkFocusTarget, seededPosition, type FocusTarget } from "../graph/spatialLayout";
import { advanceFocusAnimation, type FocusAnimationState } from "../graph/cameraFocus";
import { getVisibleLabelNodes, type LabelMode } from "../graph/labelMode";
import { buildFocusVisibility, type FocusVisibilityState } from "../graph/focusVisibility";
import { summarizeRiskConcentration } from "../graph/riskConcentration";

type Props = {
  nodes: GraphNode[];
  links: GraphLink[];
  lens: RiskLens;
  selection: GraphSelection;
  onSelectNode: (node: GraphNode) => void;
  onSelectLink: (link: GraphLink) => void;
  onClearSelection: () => void;
};

type PositionedNode = GraphNode & { position: THREE.Vector3 };
type CameraAction = { type: "reset" | "fit" | "focus-selected"; nonce: number };

function toVector3(position: { x: number; y: number; z: number }): THREE.Vector3 {
  return new THREE.Vector3(position.x, position.y, position.z);
}

function CameraRig({ focusTarget, focusKey }: { focusTarget: FocusTarget | null; focusKey: string | null }) {
  const { camera, gl } = useThree();
  const controlsRef = useRef<OrbitControls | null>(null);
  const focusAnimationRef = useRef<FocusAnimationState>({ key: null, frames: 0, active: false });
  useEffect(() => {
    camera.position.set(0, 5.6, 14);
    const controls = new OrbitControls(camera, gl.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 5;
    controls.maxDistance = 28;
    controls.target.set(0, 0, 0);
    controlsRef.current = controls;
    return () => {
      controls.dispose();
      controlsRef.current = null;
    };
  }, [camera, gl]);
  useFrame(() => {
    const controls = controlsRef.current;
    if (!controls) return;
    focusAnimationRef.current = advanceFocusAnimation(focusAnimationRef.current, focusKey);
    if (focusTarget && focusAnimationRef.current.active) {
      camera.position.lerp(toVector3(focusTarget.camera), 0.055);
      controls.target.lerp(toVector3(focusTarget.lookAt), 0.07);
    }
    controls.update();
  });
  return null;
}

function Atmosphere({ paused }: { paused: boolean }) {
  const grid = useRef<THREE.GridHelper>(null);
  useFrame(({ clock }) => {
    if (grid.current && !paused) {
      grid.current.rotation.y = clock.elapsedTime * 0.018;
    }
  });
  return (
    <>
      <color attach="background" args={["#05070a"]} />
      <fog attach="fog" args={["#05070a", 13, 34]} />
      <ambientLight intensity={0.42} />
      <pointLight position={[4, 6, 7]} intensity={2.8} color="#6fd3ff" />
      <pointLight position={[-5, -2, -4]} intensity={1.9} color="#ffb547" />
      <gridHelper ref={grid} args={[28, 28, "#1d2732", "#111820"]} position={[0, -4.2, 0]} />
    </>
  );
}

function linkOpacity(link: GraphLink, lens: RiskLens, focusState: FocusVisibilityState): number {
  const inLens = linkMatchesLens(link, lens);
  if (focusState === "selected") return 0.98;
  if (focusState === "context") return inLens ? 0.64 : 0.38;
  if (focusState === "dimmed") return inLens ? 0.12 : 0.035;
  return inLens ? (link.riskKind === "standard" ? 0.14 : 0.74) : 0.06;
}

function nodeOpacity(node: GraphNode, lens: RiskLens, focusState: FocusVisibilityState): number {
  const inLens = nodeMatchesLens(node, lens);
  if (focusState === "selected") return 0.98;
  if (focusState === "context") return inLens ? 0.78 : 0.46;
  if (focusState === "dimmed") return inLens ? 0.24 : 0.08;
  return inLens ? 0.96 : 0.2;
}

function LinkLine({ link, source, target, lens, focusState, onSelect }: { link: GraphLink; source: PositionedNode; target: PositionedNode; lens: RiskLens; focusState: FocusVisibilityState; onSelect: () => void }) {
  const selected = focusState === "selected";
  const points = useMemo(() => [source.position, target.position], [source.position, target.position]);
  const geometry = useMemo(() => new THREE.BufferGeometry().setFromPoints(points), [points]);
  const hitGeometry = useMemo(() => new THREE.TubeGeometry(new THREE.LineCurve3(source.position, target.position), 1, selected ? 0.18 : 0.12, 8), [source.position, target.position, selected]);
  const material = useMemo(() => new THREE.LineBasicMaterial({ transparent: true }), []);
  const line = useMemo(() => new THREE.Line(geometry, material), [geometry, material]);
  material.color.set(selected ? "#f7fbff" : focusState === "context" ? "#f5c95f" : riskColor(link.riskKind));
  material.opacity = linkOpacity(link, lens, focusState);
  material.linewidth = selected ? 3 : 1;
  return (
    <group>
      <primitive object={line} />
      {selected && (
        <mesh geometry={hitGeometry}>
          <meshBasicMaterial transparent opacity={0.22} color="#f7fbff" />
        </mesh>
      )}
      <mesh geometry={hitGeometry} onClick={(event) => { event.stopPropagation(); onSelect(); }}>
        <meshBasicMaterial transparent opacity={0.002} color="#ffffff" />
      </mesh>
    </group>
  );
}

function NodeOrb({ node, lens, focusState, paused, onSelect }: { node: PositionedNode; lens: RiskLens; focusState: FocusVisibilityState; paused: boolean; onSelect: () => void }) {
  const mesh = useRef<THREE.Mesh>(null);
  const opacity = nodeOpacity(node, lens, focusState);
  const nodeColor = riskColor(node.riskKind);
  const displayColor = focusState === "context" ? "#f5c95f" : nodeColor;
  const selectionRingColor = "#d8f3ff";
  const scale = focusState === "selected" ? 1.28 : focusState === "context" ? 1.08 : node.riskKind === "high" ? 1.22 : node.riskKind === "fragility" ? 1.12 : 0.9;
  useFrame(({ clock }) => {
    if (mesh.current && !paused) {
      mesh.current.position.y = node.position.y + Math.sin(clock.elapsedTime * 1.4 + node.position.x) * 0.045;
    }
  });
  return (
    <group position={node.position}>
      {(node.riskKind === "high" || node.riskKind === "fragility") && (
        <mesh scale={scale * (focusState === "selected" ? 1.45 : 1.8)}>
          <sphereGeometry args={[0.32, 32, 32]} />
          <meshBasicMaterial color={nodeColor} transparent opacity={focusState === "dimmed" ? 0.035 : focusState === "selected" ? 0.08 : 0.14} />
        </mesh>
      )}
      {focusState === "selected" && (
        <mesh scale={scale * 1.46}>
          <sphereGeometry args={[0.31, 32, 32]} />
          <meshBasicMaterial color={selectionRingColor} transparent opacity={0.62} wireframe />
        </mesh>
      )}
      <mesh ref={mesh} scale={scale} onClick={(event) => { event.stopPropagation(); onSelect(); }}>
        <sphereGeometry args={[0.22, 32, 32]} />
        <meshStandardMaterial color={displayColor} emissive={displayColor} emissiveIntensity={focusState === "dimmed" ? 0.04 : focusState === "selected" ? 0.62 : 0.48} roughness={0.32} metalness={0.18} transparent opacity={opacity} />
      </mesh>
      <mesh scale={scale * 1.8} onClick={(event) => { event.stopPropagation(); onSelect(); }}>
        <sphereGeometry args={[0.24, 20, 20]} />
        <meshBasicMaterial transparent opacity={0.002} color="#ffffff" />
      </mesh>
    </group>
  );
}

function resetTarget(): FocusTarget {
  return { camera: { x: 0, y: 5.6, z: 14 }, lookAt: { x: 0, y: 0, z: 0 } };
}

function fitTarget(nodes: PositionedNode[]): FocusTarget {
  const maxRadius = nodes.reduce((max, node) => Math.max(max, node.position.length()), 0);
  return { camera: { x: 0, y: Math.max(5.6, maxRadius * 0.35), z: Math.max(14, maxRadius * 1.9) }, lookAt: { x: 0, y: 0, z: 0 } };
}

function SpatialScene(props: Props & { cameraAction: CameraAction | null; pausedMotion: boolean }) {
  const positioned = useMemo<PositionedNode[]>(() => (
    props.nodes.map((node, index) => ({ ...node, position: toVector3(seededPosition(index, props.nodes.length, node.riskScore)) }))
  ), [props.nodes]);
  const nodeMap = useMemo(() => new Map(positioned.map((node) => [node.id, node])), [positioned]);
  const focusVisibility = useMemo(() => buildFocusVisibility(props.nodes, props.links, props.selection), [props.nodes, props.links, props.selection]);
  const selectionFocusTarget = useMemo(() => {
    const selection = props.selection;
    if (selection.type === "node") {
      const node = nodeMap.get(selection.id);
      return node ? getFocusTarget(node.position) : null;
    }
    if (selection.type === "link") {
      const link = props.links.find((item) => item.id === selection.id);
      const source = link ? nodeMap.get(link.source) : null;
      const target = link ? nodeMap.get(link.target) : null;
      return source && target ? getLinkFocusTarget(source.position, target.position) : null;
    }
    return null;
  }, [nodeMap, props.links, props.selection]);
  const focusTarget = useMemo(() => {
    if (props.cameraAction?.type === "reset") return resetTarget();
    if (props.cameraAction?.type === "fit") return fitTarget(positioned);
    return selectionFocusTarget;
  }, [positioned, props.cameraAction, selectionFocusTarget]);
  const focusKey = props.cameraAction
    ? `${props.cameraAction.type}:${props.cameraAction.nonce}`
    : props.selection.type === "none" ? null : `${props.selection.type}:${props.selection.id}`;

  return (
    <>
      <Atmosphere paused={props.pausedMotion} />
      <CameraRig focusTarget={focusTarget} focusKey={focusKey} />
      {props.links.map((link) => {
        const source = nodeMap.get(link.source);
        const target = nodeMap.get(link.target);
        if (!source || !target) return null;
        return (
          <LinkLine
            key={link.id}
            link={link}
            source={source}
            target={target}
            lens={props.lens}
            focusState={focusVisibility.linkState(link.id)}
            onSelect={() => props.onSelectLink(link)}
          />
        );
      })}
      {positioned.map((node) => (
        <NodeOrb
          key={node.id}
          node={node}
          lens={props.lens}
          focusState={focusVisibility.nodeState(node.id)}
          paused={props.pausedMotion}
          onSelect={() => props.onSelectNode(node)}
        />
      ))}
    </>
  );
}

export function SpatialCanvas3D(props: Props) {
  const [cameraAction, setCameraAction] = useState<CameraAction | null>(null);
  const [pausedMotion, setPausedMotion] = useState(false);
  const [labelMode, setLabelMode] = useState<LabelMode>("top-risks");
  const selectedNodeId = props.selection.type === "node" ? props.selection.id : null;
  const selectedLinkId = props.selection.type === "link" ? props.selection.id : null;
  const selectedNode = selectedNodeId ? props.nodes.find((node) => node.id === selectedNodeId) : null;
  const selectedLink = selectedLinkId ? props.links.find((link) => link.id === selectedLinkId) : null;
  const riskSummary = useMemo(() => summarizeRiskConcentration(props.nodes, props.links), [props.nodes, props.links]);
  const effectiveLabelMode = props.selection.type === "none" ? labelMode : labelMode === "top-risks" ? "selected-neighbors" : labelMode;
  const commandNonce = useRef(0);
  useEffect(() => {
    setCameraAction(null);
  }, [props.selection]);
  const topLabels = useMemo(() => (
    getVisibleLabelNodes(props.nodes, props.links, props.selection, props.lens, effectiveLabelMode)
  ), [props.nodes, props.links, props.selection, props.lens, effectiveLabelMode]);

  function runCameraAction(type: CameraAction["type"]) {
    commandNonce.current += 1;
    setCameraAction({ type, nonce: commandNonce.current });
  }

  return (
    <section className="graph-stage graph-stage-3d" aria-label="Cinematic 3D spatial canvas">
      <Canvas camera={{ position: [0, 5.6, 14], fov: 48 }} onPointerMissed={props.onClearSelection}>
        <SpatialScene {...props} cameraAction={cameraAction} pausedMotion={pausedMotion} />
      </Canvas>
      <div className="canvas-control-bar" aria-label="3D canvas controls">
        <button onClick={() => runCameraAction("reset")}>Reset View</button>
        <button onClick={() => runCameraAction("fit")}>Fit Graph</button>
        <button onClick={() => runCameraAction("focus-selected")} disabled={!selectedNode && !selectedLink}>Focus Selected</button>
        <button onClick={props.onClearSelection} disabled={!selectedNode && !selectedLink}>Clear Selection</button>
        <button onClick={() => setPausedMotion((value) => !value)}>{pausedMotion ? "Resume Motion" : "Pause Motion"}</button>
        <label>
          <span>Labels</span>
          <select className="label-density" value={labelMode} onChange={(event) => setLabelMode(event.target.value as LabelMode)}>
            <option value="top-risks">Top Risks</option>
            <option value="selected-neighbors">Selected + Neighbors</option>
            <option value="none">None</option>
          </select>
        </label>
      </div>
      <div className="graph-label-stack">
        {(selectedNode || selectedLink) && (
          <div className="selection-callout">
            <span>Focused</span>
            {selectedNode?.name || selectedLink?.relationship || "Selected risk path"}
          </div>
        )}
        {topLabels.map((node) => (
          <button key={node.id} className={`floating-label ${node.riskKind}${selectedNodeId === node.id ? " active" : ""}`} onClick={() => props.onSelectNode(node)}>
            <span>{node.riskKind}</span>
            {node.name}
          </button>
        ))}
      </div>
      <div className="risk-concentration-hud">
        <span>Risk concentration</span>
        <strong>{riskSummary.primaryNode?.name || "No dominant node"}</strong>
        <p>{riskSummary.caption}</p>
      </div>
      <div className="scene-caption">3D command view - drag to orbit - scroll to zoom</div>
    </section>
  );
}
