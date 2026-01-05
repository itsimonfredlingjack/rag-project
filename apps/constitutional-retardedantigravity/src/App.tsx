import { Suspense } from 'react';
import { Canvas } from '@react-three/fiber';
import { Substrate } from './components/3d/Substrate';
import { TrustHull } from './components/ui/TrustHull';
import { EffectComposer, Noise, Vignette, Bloom } from '@react-three/postprocessing';

import { SourceViewer3D } from './components/3d/SourceViewer3D';
import { ConnectorLogic } from './components/3d/ConnectorLogic';

function App() {
  return (
    <div className="w-screen h-screen bg-[#E7E5E4] overflow-hidden relative">
      {/* ===== LAYER 0: 3D Background (Fixed, Z-0) ===== */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <Canvas
          camera={{ position: [0, 2, 8], fov: 50 }}
          gl={{ antialias: true, powerPreference: "high-performance" }}
        >
          <color attach="background" args={['#E7E5E4']} />
          <fog attach="fog" args={['#E7E5E4', 5, 25]} />

          <ambientLight intensity={0.8} />
          <pointLight position={[10, 10, 10]} intensity={0.6} color="#0f766e" />
          <pointLight position={[-10, 5, -10]} intensity={0.4} color="#b45309" />

          <Suspense fallback={null}>
            <Substrate />

            {/* 3D Source Visualization (Left side) */}
            <SourceViewer3D />
            <ConnectorLogic />
          </Suspense>

          <EffectComposer>
            <Bloom luminanceThreshold={0.8} mipmapBlur intensity={0.2} radius={0.2} />
            <Noise opacity={0.01} />
            <Vignette eskil={false} offset={0.1} darkness={0.4} />
          </EffectComposer>
        </Canvas>
      </div>

      {/* ===== LAYER 1: UI Overlay (Relative, Z-10) ===== */}
      <div className="relative z-10 w-full h-full">
        <TrustHull />
      </div>
    </div>
  );
}

export default App;
