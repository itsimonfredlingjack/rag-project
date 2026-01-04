import { useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Text, Html } from '@react-three/drei';
import * as THREE from 'three';
import { useAppStore } from '../../stores/useAppStore';

interface SourceCardProps {
    id: string;
    index: number;
    title: string;
    type: string;
}

export function SourceCard({ id, index, title, type }: SourceCardProps) {
    const meshRef = useRef<THREE.Group>(null);
    const activeSourceId = useAppStore(state => state.activeSourceId);
    const setActiveSource = useAppStore(state => state.setActiveSource);

    const isActive = activeSourceId === id;
    const [hovered, setHovered] = useState(false);

    useFrame((state) => {
        if (!meshRef.current) return;

        // Target position calculation
        // Spread them out horizontally, slight curve
        const xPos = (index - 1.5) * 1.8;
        const isTarget = isActive || hovered;

        // Smooth lerp to position
        const targetZ = isActive ? 1.5 : (hovered ? 0.5 : 0);
        const targetY = isActive ? 0.2 : 0;

        meshRef.current.position.x = THREE.MathUtils.lerp(meshRef.current.position.x, xPos, 0.1);
        meshRef.current.position.z = THREE.MathUtils.lerp(meshRef.current.position.z, targetZ, 0.1);
        meshRef.current.position.y = THREE.MathUtils.lerp(meshRef.current.position.y, targetY, 0.1);

        // Slight tilt when active/hovered
        meshRef.current.rotation.x = THREE.MathUtils.lerp(meshRef.current.rotation.x, isActive ? -0.1 : 0, 0.1);
    });

    return (
        <group
            ref={meshRef}
            position={[0, 0, -20]} // Start far back
            onClick={() => setActiveSource(isActive ? null : id)}
            onPointerOver={() => setHovered(true)}
            onPointerOut={() => setHovered(false)}
        >
            {/* Glass Card Body */}
            <mesh>
                <boxGeometry args={[1.4, 2, 0.05]} />
                <meshPhysicalMaterial
                    color={isActive ? "#00f3ff" : "#2a2a2a"}
                    transparent
                    opacity={isActive ? 0.2 : 0.6}
                    roughness={0.2}
                    metalness={0.8}
                    transmission={0.5}
                    thickness={0.5}
                    emissive={isActive ? "#00f3ff" : "#000000"}
                    emissiveIntensity={isActive ? 0.2 : 0}
                />
            </mesh>

            {/* Content */}
            <Text
                position={[-0.6, 0.8, 0.06]}
                anchorX="left"
                anchorY="top"
                maxWidth={1.2}
                fontSize={0.12}
                color={isActive ? "white" : "#aaaaaa"}
            >
                {title}
            </Text>

            <Text
                position={[-0.6, 0.6, 0.06]}
                anchorX="left"
                fontSize={0.08}
                color="#00f3ff"
            >
                {type.toUpperCase()}
            </Text>

            {/* Glow Border (Active/Hover) */}
            {(isActive || hovered) && (
                <mesh position={[0, 0, 0.01]}>
                    <boxGeometry args={[1.42, 2.02, 0.04]} />
                    <meshBasicMaterial color="#00f3ff" wireframe transparent opacity={0.3} />
                </mesh>
            )}
        </group>
    );
}
