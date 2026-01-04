import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

export function Substrate() {
    const meshRef = useRef<THREE.Mesh>(null);

    // Custom shader for the "living noise" floor
    const uniforms = useRef({
        uTime: { value: 0 },
        uColor: { value: new THREE.Color('#0a0a0a') },
    });

    useFrame((state) => {
        if (meshRef.current) {
            uniforms.current.uTime.value = state.clock.getElapsedTime();
        }
    });

    return (
        <mesh ref={meshRef} rotation={[-Math.PI / 2, 0, 0]} position={[0, -2, -10]}>
            <planeGeometry args={[100, 100, 64, 64]} />
            <shaderMaterial
                transparent
                uniforms={uniforms.current}
                vertexShader={`
          varying vec2 vUv;
          uniform float uTime;

          // Simple noise function
          float hash(vec2 p) {
              return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
          }
          float noise(vec2 p) {
              vec2 i = floor(p);
              vec2 f = fract(p);
              vec2 u = f*f*(3.0-2.0*f);
              return mix(mix(hash(i + vec2(0.0,0.0)), hash(i + vec2(1.0,0.0)), u.x),
                         mix(hash(i + vec2(0.0,1.0)), hash(i + vec2(1.0,1.0)), u.x), u.y);
          }

          void main() {
            vUv = uv;
            vec3 pos = position;

            // Subtle wave movement
            float wave = noise(uv * 4.0 + uTime * 0.1) * 0.5;
            pos.z += wave;

            gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
          }
        `}
                fragmentShader={`
          varying vec2 vUv;
          uniform vec3 uColor;
          uniform float uTime;

          void main() {
            // Dark grid/noise pattern
            float grid = step(0.98, fract(vUv.x * 40.0)) + step(0.98, fract(vUv.y * 40.0));
            float alpha = smoothstep(0.0, 1.0, 1.0 - length(vUv - 0.5) * 2.0); // Vignette

            gl_FragColor = vec4(uColor + grid * 0.05, alpha * 0.4);
          }
        `}
            />
        </mesh>
    );
}
