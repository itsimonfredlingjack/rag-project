import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Plane } from '@react-three/drei';
import * as THREE from 'three';

const AURORA_VERTEX = `
varying vec2 vUv;
varying float vElevation;
uniform float uTime;

void main() {
  vUv = uv;
  vec4 modelPosition = modelMatrix * vec4(position, 1.0);
  
  // Create organic wave movement
  float elevation = sin(modelPosition.x * 0.5 + uTime * 0.5) * 0.5
                  + sin(modelPosition.y * 0.3 + uTime * 0.3) * 0.5;
                  
  modelPosition.z += elevation * 1.5; // Heighten the wave
  
  vElevation = elevation;
  gl_Position = projectionMatrix * viewMatrix * modelPosition;
}
`;

const AURORA_FRAGMENT = `
varying vec2 vUv;
varying float vElevation;

void main() {
  // Color palette: Cyan main, with deep blue shadows and white peaks
  vec3 colorA = vec3(0.0, 0.05, 0.1); // Deep void blue
  vec3 colorB = vec3(0.0, 0.95, 1.0); // Cyan glow
  
  float mixStrength = (vElevation + 1.0) * 0.4;
  vec3 color = mix(colorA, colorB, mixStrength);
  
  // Add grid transparency logic if desired, or just soft glow
  float alpha = smoothstep(0.0, 1.0, mixStrength) * 0.3;
  
  gl_FragColor = vec4(color, alpha);
}
`;

export function Substrate() {
    const materialRef = useRef<THREE.ShaderMaterial>(null);

    useFrame((state) => {
        if (materialRef.current) {
            materialRef.current.uniforms.uTime.value = state.clock.getElapsedTime();
        }
    });

    return (
        <group rotation={[-Math.PI / 2, 0, 0]} position={[0, -2, 0]}>
            {/* 1. Underlying Grid */}
            <gridHelper args={[60, 60, '#111111', '#050505']} position={[0, 0.1, 0]} />

            {/* 2. The Aurora Mesh */}
            <mesh position={[0, -0.5, 0]}>
                <planeGeometry args={[60, 60, 64, 64]} />
                <shaderMaterial
                    ref={materialRef}
                    vertexShader={AURORA_VERTEX}
                    fragmentShader={AURORA_FRAGMENT}
                    uniforms={{
                        uTime: { value: 0 }
                    }}
                    transparent
                    side={THREE.DoubleSide}
                    depthWrite={false}
                    blending={THREE.AdditiveBlending}
                />
            </mesh>
        </group>
    );
}
