import { Canvas } from '@react-three/fiber';
import { Substrate } from './components/3d/Substrate';
import { EvidenceDeck } from './components/3d/EvidenceDeck';
import { ConnectorLogic } from './components/3d/ConnectorLogic';
import { TrustHull } from './components/ui/TrustHull';
import { ConnectorOverlay } from './components/ui/ConnectorOverlay';
import { EffectComposer, Noise, Vignette, Bloom } from '@react-three/postprocessing';

function App() {
  return (
    <div className="w-screen h-screen bg-[#030303] overflow-hidden">
      {/* ===== LAYER 0: 3D Background (Fixed, Z-0) ===== */}
      <div className="fixed inset-0 z-0">
        <Canvas
          camera={{ position: [0, 2, 8], fov: 50 }}
          gl={{ antialias: false, powerPreference: "high-performance" }}
        >
          <color attach="background" args={['#030303']} />
          <fog attach="fog" args={['#030303', 8, 30]} />

          <ambientLight intensity={0.15} />
          <pointLight position={[10, 10, 10]} intensity={0.8} color="#00f3ff" />
          <pointLight position={[-10, 5, -10]} intensity={0.4} color="#ffaa00" />

          <Substrate />
          <EvidenceDeck />
          <ConnectorLogic />

          <EffectComposer>
            <Bloom luminanceThreshold={0.3} mipmapBlur intensity={0.4} radius={0.3} />
            <Noise opacity={0.03} />
            <Vignette eskil={false} offset={0.1} darkness={0.8} />
          </EffectComposer>
        </Canvas>
      </div>

      {/* ===== LAYER 1: UI Overlay (Relative, Z-10) ===== */}
      <div className="relative z-10 w-full h-full">
        <TrustHull />
      </div>

      {/* ===== LAYER 2: Connector Lines (Fixed, Z-50) ===== */}
      <ConnectorOverlay />
    </div>
  );
}

export default App;
